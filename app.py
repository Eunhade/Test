import os
import json
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for
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

# Presence tracking to prevent matching with offline/stale queue entries
ONLINE_TTL = 60  # seconds


def touch_online(user_id: int):
    """Mark user as online with a short TTL (refreshed by heartbeats)."""
    try:
        r.setex(f"user:{user_id}:online", ONLINE_TTL, "1")
    except Exception:
        pass


# Track if pubsub listener has been started
pubsub_listener_started = False


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))


# --------------------
# Page routes
# --------------------
@app.route("/")
def index():
    """Serve login page (or redirect to lobby if already authenticated)."""
    if current_user.is_authenticated:
        return redirect(url_for("lobby"))
    return render_template("login.html")


@app.route("/lobby")
@login_required
def lobby():
    """Lobby page after login."""
    return render_template("lobby.html")


@app.route("/game")
@login_required
def game_page():
    """Game page: waiting room + gameplay."""
    return render_template("game.html")


@app.route("/active_match")
@login_required
def active_match():
    """Return current user's active match assignment (prevents missed socket events)."""
    room = r.get(f"user:{current_user.id}:active_room")
    if not room:
        return jsonify({"active": False})

    # Validate the room still exists; if not, clear stale assignment
    if not r.exists(f"game:{room}:meta"):
        r.delete(f"user:{current_user.id}:active_room")
        r.delete(f"user:{current_user.id}:active_is_p1")
        return jsonify({"active": False})

    is_p1_str = r.get(f"user:{current_user.id}:active_is_p1")
    is_p1 = True if str(is_p1_str) == "1" else False
    return jsonify({"active": True, "room": room, "is_p1": is_p1})


# --------------------
# Auth + API routes
# --------------------
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
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Database error"}), 500


@app.route("/login", methods=["POST"])
def login():
    """Authenticate user and create session."""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        login_user(user)
        return jsonify({
            "success": True,
            "user_id": user.id,
            "username": user.username
        })

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
    total_games = int(current_user.total_games or 0)
    total_wins = int(current_user.total_wins or 0)
    total_losses = max(0, total_games - total_wins)

    return jsonify({
        "username": current_user.username,
        "total_games": total_games,
        "total_wins": total_wins,
        "total_losses": total_losses,
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

@app.route("/match_info")
@login_required
def match_info():
    """Return usernames for both players in a room (and who is you/opponent)."""
    room = (request.args.get("room") or "").strip()
    if not room:
        return jsonify({"error": "room required"}), 400

    meta = r.hgetall(f"game:{room}:meta")
    if not meta:
        return jsonify({"error": "match not found"}), 404

    try:
        p1_id = int(meta.get("p1"))
        p2_id = int(meta.get("p2"))
    except Exception:
        return jsonify({"error": "corrupt match data"}), 500

    if current_user.id not in (p1_id, p2_id):
        return jsonify({"error": "not a player in this match"}), 403

    p1 = User.query.get(p1_id)
    p2 = User.query.get(p2_id)

    you_is_p1 = (current_user.id == p1_id)

    return jsonify({
        "room": room,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "p1_username": p1.username if p1 else None,
        "p2_username": p2.username if p2 else None,
        "you_id": current_user.id,
        "you_username": (p1.username if you_is_p1 else p2.username) if (p1 and p2) else current_user.username,
        "opponent_id": (p2_id if you_is_p1 else p1_id),
        "opponent_username": (p2.username if you_is_p1 else p1.username) if (p1 and p2) else "Opponent",
    })
# --------------------
# Socket.IO events
# --------------------
@socketio.on("connect")
def on_connect():
    """Handle new WebSocket connection."""
    global pubsub_listener_started

    if not current_user.is_authenticated:
        emit("not_authenticated")
        return False

    # Mark presence
    touch_online(current_user.id)

    # Join private room for this user
    join_room(f"user:{current_user.id}")
    emit("connected", {"user_id": current_user.id, "username": current_user.username})

    # Start Redis pubsub listener (only once)
    if not pubsub_listener_started:
        t = threading.Thread(target=start_redis_listener, daemon=True)
        t.start()
        pubsub_listener_started = True


@socketio.on("presence")
def on_presence():
    """Heartbeat from client to keep online status fresh."""
    if current_user.is_authenticated:
        touch_online(current_user.id)


@socketio.on("join_room")
def on_join_room(data):
    """Player joins game room after match found."""
    touch_online(current_user.id)

    room = data.get("room")
    if not room:
        return

    join_room(room)
    emit("player_joined", {
        "user_id": current_user.id,
        "username": current_user.username
    }, room=room)

@socketio.on("surrender")
def on_surrender(data):
    """End the game immediately: surrendering player loses, opponent wins."""
    room = (data or {}).get("room")
    if not room:
        emit("guess_error", {"error": "Missing room"})
        return

    gkey = f"game:{room}:meta"
    meta = r.hgetall(gkey)
    if not meta:
        emit("guess_error", {"error": "Match not found or already ended"})
        return

    try:
        p1_id = int(meta.get("p1"))
        p2_id = int(meta.get("p2"))
    except Exception:
        emit("guess_error", {"error": "Corrupt match data"})
        return

    if current_user.id not in (p1_id, p2_id):
        emit("guess_error", {"error": "You are not in this match"})
        return

    # Idempotency guard so two surrenders / timer don't double-save
    end_key = f"game:{room}:ended"
    if not r.set(end_key, "1", nx=True, ex=3600):
        return  # already ended elsewhere

    winner_id = (p2_id if current_user.id == p1_id else p1_id)

    scores = game_module.get_scores(r, room)
    score_p1 = int(scores.get("p1", 0))
    score_p2 = int(scores.get("p2", 0))
    duration = int(meta.get("duration", 300))

    # Persist match + update stats (same behavior as game_worker)
    try:
        match = Match(
            room=room,
            p1_id=p1_id,
            p2_id=p2_id,
            score_p1=score_p1,
            score_p2=score_p2,
            winner_id=winner_id,
            duration=duration
        )
        db.session.add(match)

        user1 = User.query.get(p1_id)
        user2 = User.query.get(p2_id)

        if user1:
            user1.total_games = (user1.total_games or 0) + 1
            if winner_id == user1.id:
                user1.total_wins = (user1.total_wins or 0) + 1

        if user2:
            user2.total_games = (user2.total_games or 0) + 1
            if winner_id == user2.id:
                user2.total_wins = (user2.total_wins or 0) + 1

        db.session.commit()
    except Exception:
        db.session.rollback()
        r.delete(end_key)  # allow retry if DB write failed
        emit("guess_error", {"error": "Failed to save surrender result"})
        return

    # Notify both clients (SocketIO message_queue will broadcast cross-process)
    socketio.emit("match_saved", {
        "winner_id": winner_id,
        "scores": {"p1": score_p1, "p2": score_p2}
    }, room=room)

    socketio.emit("game_over", {
        "room": room,
        "final_scores": {"p1": score_p1, "p2": score_p2},
        "winner_id": winner_id,
        "reason": "surrender",
        "surrendered_by": current_user.id
    }, room=room)

    # Stop timer thread + cleanup Redis keys so game_worker won't double-end it
    try:
        r.delete(f"game:{room}:time_left")
    except Exception:
        pass
    game_module.end_game_cleanup(r, room)

@socketio.on("submit_guess")
def on_submit_guess(data):
    """Process player's word guess."""
    touch_online(current_user.id)

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
    try:
        if current_user.is_authenticated:
            # Remove from matchmaking queue to avoid stale matches
            r.lrem(QUEUE_KEY, 0, str(current_user.id))
            r.delete(f"user:{current_user.id}:online")
    except Exception:
        pass
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
                # Notify each player and tell them if they are player 1 or 2
                players = data.get("players", [])
                room = data.get("room")
                if room and len(players) == 2:
                    p1, p2 = players

                    socketio.emit(
                        "match_found",
                        {"room": room, "is_p1": True},
                        room=f"user:{p1}",
                    )

                    socketio.emit(
                        "match_found",
                        {"room": room, "is_p1": False},
                        room=f"user:{p2}",
                    )

            elif event_type == "timer_update":
                room = data.get("room")
                time_left = data.get("time_left")
                socketio.emit("timer_update", {"time_left": time_left}, room=room)

            elif event_type == "game_over":
                room = data.get("room")
                socketio.emit(
                    "game_over",
                    {
                        "room": room,
                        "final_scores": data.get("final_scores", {}),
                        "winner_id": data.get("winner_id"),
                    },
                    room=room,
                )

            elif event_type == "match_result_saved":
                room = data.get("room")
                socketio.emit(
                    "match_saved",
                    {
                        "winner_id": data.get("winner_id"),
                        "scores": data.get("scores"),
                    },
                    room=room,
                )

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
