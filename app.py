import os
import json
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_session import Session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
import redis

from db import db
from models import User, Match
import game as game_module
from wordle_logic import evaluate_guess, random_word, is_valid_word


# --------------------
# Flask app setup
# --------------------
def create_app():
    """Factory function to create and configure Flask app."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Redis-backed server-side sessions (helps with scaling / multiple workers)
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
    message_queue=os.environ.get("REDIS_URL"),
)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "index"

# Redis connection for game state and pubsub
r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

QUEUE_KEY = "matchmaking_queue"
EVENT_CHANNEL = "events"

# Track if pubsub listener has been started (per web process)
pubsub_listener_started = False


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None


# --------------------
# Page routes
# --------------------
@app.route("/")
def index():
    # Login page (v2 art style)
    if current_user.is_authenticated:
        return redirect(url_for("lobby"))
    return render_template("login.html")


@app.route("/lobby")
@login_required
def lobby():
    return render_template("lobby.html")


@app.route("/game")
@login_required
def game_page():
    return render_template("game.html")


@app.route("/singleplayer")
@login_required
def singleplayer_page():
    return render_template("singleplayer.html")


# --------------------
# Auth + API routes
# --------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

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
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        return jsonify({"success": True, "user_id": user.id, "username": user.username})
    return jsonify({"error": "Invalid username or password"}), 401


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"success": True})


@app.route("/queue", methods=["POST"])
@login_required
def join_queue():
    # prevent duplicates
    queue_list = r.lrange(QUEUE_KEY, 0, -1)
    if str(current_user.id) in queue_list:
        return jsonify({"error": "Already in queue"}), 400

    r.lpush(QUEUE_KEY, current_user.id)
    return jsonify({"queued": True, "user_id": current_user.id})


@app.route("/stats")
@login_required
def get_stats():
    return jsonify({
        "username": current_user.username,
        "total_games": current_user.total_games,
        "total_wins": current_user.total_wins,
        "win_rate": round(current_user.win_rate, 1),
    })


@app.route("/leaderboard")
def leaderboard():
    top_players = (
        User.query.filter(User.total_games >= 1)
        .order_by(User.total_wins.desc())
        .limit(10)
        .all()
    )
    return jsonify([{
        "username": u.username,
        "total_games": u.total_games,
        "total_wins": u.total_wins,
        "win_rate": round(u.win_rate, 1),
    } for u in top_players])


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
        return jsonify({"error": "invalid match metadata"}), 500

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
# Singleplayer API (session-based)
# --------------------
MAX_ATTEMPTS = 6

@app.route("/api/new-game", methods=["POST"])
@login_required
def sp_new_game():
    target = random_word()
    session["sp_target"] = target
    session["sp_guesses"] = []
    session["sp_done"] = False
    return jsonify({"success": True})


@app.route("/api/guess", methods=["POST"])
@login_required
def sp_guess():
    if session.get("sp_done"):
        return jsonify({"success": False, "error": "Game is over. Start a new game."}), 400

    target = session.get("sp_target")
    if not target:
        return jsonify({"success": False, "error": "No active game. Start a new game."}), 400

    data = request.json or {}
    guess = (data.get("guess") or "").strip().upper()

    if len(guess) != 5:
        return jsonify({"success": False, "error": "Guess must be 5 letters"}), 400
    if not guess.isalpha():
        return jsonify({"success": False, "error": "Guess must contain only letters"}), 400
    if not is_valid_word(guess):
        return jsonify({"success": False, "error": "Not a valid word"}), 400

    result = evaluate_guess(target, guess)
    guesses = session.get("sp_guesses") or []
    guesses.append({"guess": guess, "colors": result.get("colors", [])})
    session["sp_guesses"] = guesses

    status = "playing"
    reveal = None

    if result.get("solved"):
        status = "won"
        reveal = target
        session["sp_done"] = True
        _record_singleplayer_result(win=True)
    elif len(guesses) >= MAX_ATTEMPTS:
        status = "lost"
        reveal = target
        session["sp_done"] = True
        _record_singleplayer_result(win=False)

    return jsonify({
        "success": True,
        "guesses": guesses,
        "status": status,
        "target": reveal,
    })


def _record_singleplayer_result(win: bool):
    """Update user stats for singleplayer results."""
    try:
        user = User.query.get(current_user.id)
        if not user:
            return
        user.total_games = (user.total_games or 0) + 1
        if win:
            user.total_wins = (user.total_wins or 0) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()


# --------------------
# Socket.IO events
# --------------------
@socketio.on("connect")
def on_connect():
    global pubsub_listener_started

    if not current_user.is_authenticated:
        emit("not_authenticated")
        return False

    # Join private room for this user
    join_room(f"user:{current_user.id}")
    emit("connected", {"user_id": current_user.id, "username": current_user.username})

    # Start Redis pubsub listener (only once per web process)
    if not pubsub_listener_started:
        t = threading.Thread(target=start_redis_listener, daemon=True)
        t.start()
        pubsub_listener_started = True


@socketio.on("join_room")
def on_join_room(data):
    room = (data or {}).get("room")
    if not room:
        return
    join_room(room)
    emit("player_joined", {"user_id": current_user.id, "username": current_user.username}, room=room)


@socketio.on("submit_guess")
def on_submit_guess(data):
    room = (data or {}).get("room")
    guess = ((data or {}).get("guess") or "").strip().upper()
    player_id = current_user.id

    if not room:
        emit("guess_error", {"error": "Missing room"})
        return

    if len(guess) != 5:
        emit("guess_error", {"error": "Guess must be 5 letters"})
        return

    if not guess.isalpha():
        emit("guess_error", {"error": "Guess must contain only letters"})
        return

    if not is_valid_word(guess):
        emit("guess_error", {"error": "Not a valid word"})
        return

    secret = game_module.get_player_word(r, room, player_id)
    if not secret:
        emit("guess_error", {"error": "Game not started properly"})
        return

    result = evaluate_guess(secret, guess)

    emit("guess_feedback", {
        "guess": guess,
        "colors": result.get("colors", []),
        "solved": bool(result.get("solved")),
    })

    if result.get("solved"):
        game_module.increment_score(r, room, player_id)
        scores = game_module.get_scores(r, room)
        socketio.emit("score_update", scores, room=room)

        new_word = random_word()
        game_module.set_player_word(r, room, player_id, new_word)
        emit("new_word", {"word_length": len(new_word), "message": "Correct! New word assigned"})


@socketio.on("disconnect")
def on_disconnect():
    # Presence tracking could be added here if you want
    pass


# --------------------
# Redis Pubsub Listener
# --------------------
def start_redis_listener():
    pubsub = r.pubsub()
    pubsub.subscribe(EVENT_CHANNEL)

    for msg in pubsub.listen():
        if msg is None or msg.get("type") != "message":
            continue

        try:
            data = json.loads(msg["data"])
            event_type = data.get("type")

            if event_type == "match_found":
                players = data.get("players", [])
                room = data.get("room")
                if room and len(players) == 2:
                    p1, p2 = players

                    socketio.emit("match_found", {"room": room, "is_p1": True}, room=f"user:{p1}")
                    socketio.emit("match_found", {"room": room, "is_p1": False}, room=f"user:{p2}")

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
                    {"winner_id": data.get("winner_id"), "scores": data.get("scores")},
                    room=room,
                )

        except json.JSONDecodeError:
            print(f"Invalid JSON in pubsub message: {msg.get('data')}")
        except Exception as e:
            print(f"Error processing pubsub message: {e}")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
