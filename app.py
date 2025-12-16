import os
import json
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from jinja2 import TemplateNotFound
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

    db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
    # Railway/Heroku sometimes provide postgres:// (SQLAlchemy wants postgresql://)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url

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

# Use the same Redis URL everywhere (sessions, Socket.IO message queue, game state)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# SocketIO with Redis message queue for multi-process scaling
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    message_queue=REDIS_URL,
)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "index"

# Redis connection for game state and pubsub
r = redis.from_url(REDIS_URL, decode_responses=True)

QUEUE_KEY = "matchmaking_queue"
EVENT_CHANNEL = "events"
ONLINE_KEY_FMT = "user:{uid}:online"
ONLINE_TTL = int(os.environ.get("ONLINE_TTL", "180"))


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
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    existing = User.query.filter_by(username=username).first()
    if existing:
        return j
