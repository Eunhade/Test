import os
import json
import threading
from flask import Flask, render_template, request, jsonify
from flask_session import Session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
from db import db
from models import User, Match
import redis
import game as game_module
from wordle_logic import evaluate_guess, random_word, is_valid_word


# Flask app setup
def create_app():
    """Factory function to create and configure Flask app."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,  # Verify connections before using
        "pool_recycle": 300,    # Recycle connections after 5 minutes
    }

    # Redis-backed server-side sessions
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis.from_url(redis_url)
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True

    db.init_app(app)
    Session(app)
    return app

app = create_app()


# SocketIO with Redis message queue for multi-process scaling
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    message_queue=os.environ.get("REDIS_URL")
)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "index"

# Redis connection for game state and pubsub
r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
QUEUE_KEY = "matchmaking_queue"
EVENT_CHANNEL = "events"

# Track if pubsub listener has been started
pubsub_listener_started = False

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))


# --------------------
# Basic routes
# --------------------
@app.route("/")
def index():
    """Serve the main single-page app."""
    return render_template("index2.html")


@app.route("/register", methods=["POST"])
def register():
    """Create new user account."""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken"}), 400
    
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    
    try:
        db.session.commit()
        return jsonify({"success": True, "message": "Account created successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500
    
@app.route("/login", methods=["POST"])
def login():
    """Authenticate user and create session."""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")

    print(f"\n\nUsername trying to connect is {username}\n\n")
    
    user = User.query.filter_by(username=username).first()
    
    if user and user.check_password(password):
        login_user(user)
        return jsonify({
            "success": True, 
            "user_id": user.id,
            "username": user.username
        })
    
    print("\n\nError\n\n")
    
    return jsonify({"error": "Invalid username or password"}), 401


@app.route("/logout")
@login_required
def logout():
    """End user session."""
    logout_user()
    return jsonify({"success": True})


@app.route("/queue", methods=["POST"])
@login_required
def join_queue():
    """Add authenticated user to matchmaking queue."""
    # Check if already in queue
    queue_list = r.lrange(QUEUE_KEY, 0, -1)
    if str(current_user.id) in queue_list:
        return jsonify({"error": "Already in queue"}), 400
    
    r.lpush(QUEUE_KEY, current_user.id)
    return jsonify({"queued": True, "user_id": current_user.id})


@app.route("/stats")
@login_required
def get_stats():
    """Get current user's statistics."""
    return jsonify({
        "username": current_user.username,
        "total_games": current_user.total_games,
        "total_wins": current_user.total_wins,
        "win_rate": round(current_user.win_rate, 1)
    })

@app.route("/leaderboard")
def leaderboard():
    """Get top players by total wins."""
    top_players = User.query.filter(User.total_games >= 1).order_by(User.total_wins.desc()).limit(10).all()
    
    return jsonify([{
        "username": u.username,
        "total_games": u.total_games,
        "total_wins": u.total_wins,
        "win_rate": round(u.win_rate, 1)
    } for u in top_players])



@socketio.on("connect")
def on_connect():
    """Handle new WebSocket connection."""
    global pubsub_listener_started
    
    if not current_user.is_authenticated:
        emit("not_authenticated")
        return False
    
    # Join private room for this user
    join_room(f"user:{current_user.id}")
    emit("connected", {"user_id": current_user.id, "username": current_user.username})
    
    # Start Redis pubsub listener (only once)
    if not pubsub_listener_started:
        t = threading.Thread(target=start_redis_listener, daemon=True)
        t.start()
        pubsub_listener_started = True

@socketio.on("join_room")
def on_join_room(data):
    """Player joins game room after match found."""
    room = data.get("room")
    if not room:
        return
    
    join_room(room)
    emit("player_joined", {
        "user_id": current_user.id,
        "username": current_user.username
    }, room=room)

@socketio.on("submit_guess")
def on_submit_guess(data):
    """Process player's word guess."""
    room = data.get("room")
    guess = data.get("guess", "").strip().upper()
    player_id = current_user.id
    
    # Validate guess
    if len(guess) != 5:
        emit("guess_error", {"error": "Guess must be 5 letters"})
        return
    
    if not guess.isalpha():
        emit("guess_error", {"error": "Guess must contain only letters"})
        return
    
    # Validate word is in dictionary
    if not is_valid_word(guess):
        emit("guess_error", {"error": "Not a valid word"})
        return
    
    # Get player's secret word (scoped to room)
    secret = game_module.get_player_word(r, room, player_id)
    if not secret:
        emit("guess_error", {"error": "Game not started properly"})
        return
    
    # Evaluate guess
    result = evaluate_guess(secret, guess)
    emit("guess_feedback", {
        "guess": guess,
        "colors": result["colors"],
        "solved": result["solved"]
    })
    
    # If solved, increment score and assign new word
    if result["solved"]:
        game_module.increment_score(r, room, player_id)
        scores = game_module.get_scores(r, room)
        
        socketio.emit("score_update", scores, room=room)
        
        # Assign new word for this player
        new_word = random_word()
        game_module.set_player_word(r, room, player_id, new_word)
        emit("new_word", {"word_length": len(new_word), "message": "Correct! New word assigned"})

@socketio.on("disconnect")
def on_disconnect():
    """Handle WebSocket disconnection."""
    print(f"User {current_user.id if current_user.is_authenticated else 'unknown'} disconnected")

# ===== Redis Pubsub Listener =====

def start_redis_listener():
    """
    Background thread listening to Redis pubsub events.
    Re-emits events to appropriate SocketIO rooms.
    """
    pubsub = r.pubsub()
    pubsub.subscribe(EVENT_CHANNEL)
    
    print("Redis pubsub listener started")
    
    for msg in pubsub.listen():
        if msg is None or msg.get("type") != "message":
            continue
        
        try:
            data = json.loads(msg["data"])
            event_type = data.get("type")
            
            if event_type == "match_found":
                # Notify each player in their private room
                players = data.get("players", [])
                room = data.get("room")
                for uid in players:
                    socketio.emit("match_found", {"room": room}, room=f"user:{uid}")
            
            elif event_type == "timer_update":
                room = data.get("room")
                time_left = data.get("time_left")
                socketio.emit("timer_update", {"time_left": time_left}, room=room)
            
            elif event_type == "game_over":
                room = data.get("room")
                socketio.emit("game_over", {
                    "room": room,
                    "final_scores": data.get("final_scores", {})
                }, room=room)
            
            elif event_type == "match_result_saved":
                room = data.get("room")
                socketio.emit("match_saved", {
                    "winner_id": data.get("winner_id"),
                    "scores": data.get("scores")
                }, room=room)
                
        except json.JSONDecodeError:
            print(f"Invalid JSON in pubsub message: {msg.get('data')}")
        except Exception as e:
            print(f"Error processing pubsub message: {e}")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("Database tables created")
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)