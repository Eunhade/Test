# game_worker.py
"""
Game timer and match persistence worker.

Manages game timers and persists match results to database.

Responsibilities:
- Run countdown timers for active games
- Publish timer updates via Redis pubsub
- Calculate winners when time expires
- Save match records to PostgreSQL
- Update player statistics

Run as a separate process:
    python game_worker.py
"""
import os
import time
import json
import threading
from dotenv import load_dotenv

load_dotenv()

import redis
from flask import Flask
from db import db
from models import Match, User
import game as game_module

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///local.db")
EVENT_CHANNEL = "events"
START_GAME_CHANNEL = "start_game"

GAME_TTL = 60 * 60

# Redis connection
r = redis.from_url(REDIS_URL, decode_responses=True)

# Minimal Flask app for database access
def make_app_for_db():
    """Create Flask app context for database operations."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    db.init_app(app)
    return app

app = make_app_for_db()

def run_timer_for_room(room: str):
    """
    Run countdown timer for a specific game room.
    
    Publishes timer updates every second.
    When timer expires, triggers game_over handling.
    
    Args:
        room: Game room identifier
    """
    timer_key = f"game:{room}:time_left"
    
    # Ensure timer exists
    if not r.exists(timer_key):
        r.set(timer_key, 300)
        r.expire(timer_key, GAME_TTL)
    
    print(f"Timer started for room {room}")
    
    while True:
        try:
            # Atomic decrement
            time_left = r.decr(timer_key)
            
            if time_left < 0:
                break
            
            # Publish timer update every second
            r.publish(EVENT_CHANNEL, json.dumps({
                "type": "timer_update",
                "room": room,
                "time_left": int(time_left)
            }))
            
            # Check if time expired
            if int(time_left) <= 0:
                print(f"Time's up for room {room}")
                handle_game_over(room)
                break
            
            time.sleep(1)
            
        except redis.RedisError as e:
            print(f"Redis error in timer for {room}: {e}")
            break
        except Exception as e:
            print(f"Error in timer for {room}: {e}")
            break

def handle_game_over(room: str):
    """
    Process game completion.
    
    - Fetch final scores from Redis
    - Determine winner
    - Persist match to database
    - Update player statistics
    - Notify clients via pubsub
    - Clean up Redis keys
    
    Args:
        room: Game room identifier
    """
    print(f"Processing game over for room {room}")
    
    try:
        # Get final scores from Redis
        scores = game_module.get_scores(r, room)
        score_p1 = scores.get("p1", 0)
        score_p2 = scores.get("p2", 0)
        
        gkey = f"game:{room}:meta"
        game_meta = r.hgetall(gkey)
        
        if not game_meta:
            print(f"No game metadata found for room {room}")
            return
        
        p1 = game_meta.get("p1")
        p2 = game_meta.get("p2")
        duration = int(game_meta.get("duration", 300))
        
        if not p1 or not p2:
            print(f"Missing player data for room {room}")
            return
        
        # Determine winner
        winner_id = None
        if score_p1 > score_p2:
            winner_id = int(p1)
            print(f"Player {p1} wins! ({score_p1} - {score_p2})")
        elif score_p2 > score_p1:
            winner_id = int(p2)
            print(f"Player {p2} wins! ({score_p2} - {score_p1})")
        else:
            print(f"Tie game! ({score_p1} - {score_p2})")
        
        # Persist to database
        with app.app_context():
            try:
                # Create match record
                match = Match(
                    room=room,
                    p1_id=int(p1),
                    p2_id=int(p2),
                    score_p1=int(score_p1),
                    score_p2=int(score_p2),
                    winner_id=winner_id,
                    duration=duration
                )
                db.session.add(match)
                
                # Update player statistics
                user1 = User.query.get(int(p1))
                user2 = User.query.get(int(p2))
                
                if user1:
                    user1.total_games = (user1.total_games or 0) + 1
                    if winner_id == user1.id:
                        user1.total_wins = (user1.total_wins or 0) + 1
                
                if user2:
                    user2.total_games = (user2.total_games or 0) + 1
                    if winner_id == user2.id:
                        user2.total_wins = (user2.total_wins or 0) + 1
                
                db.session.commit()
                print(f"Match saved to database (ID: {match.id})")
                
            except Exception as e:
                db.session.rollback()
                print(f"Database error saving match: {e}")
                return
        
        # Publish match result saved event
        r.publish(EVENT_CHANNEL, json.dumps({
            "type": "match_result_saved",
            "room": room,
            "winner_id": winner_id,
            "scores": {
                "p1": score_p1,
                "p2": score_p2
            }
        }))
        
        # Publish game_over event for clients
        r.publish(EVENT_CHANNEL, json.dumps({
            "type": "game_over",
            "room": room,
            "final_scores": {
                "p1": score_p1,
                "p2": score_p2
            },
            "winner_id": winner_id
        }))
        
        # Clean up Redis keys
        game_module.end_game_cleanup(r, room)
        print(f"Cleaned up Redis keys for room {room}")
        
    except Exception as e:
        print(f"Error handling game over for {room}: {e}")

def start_game_worker():
    """
    Main worker loop.
    
    Subscribes to start_game channel and spawns timer threads
    for each new game.
    """
    print("Game worker started")
    print(f"Listening on channel: {START_GAME_CHANNEL}")
    
    pubsub = r.pubsub()
    pubsub.subscribe(START_GAME_CHANNEL)
    
    for msg in pubsub.listen():
        if msg is None or msg.get("type") != "message":
            continue
        
        try:
            data = json.loads(msg["data"])
            room = data.get("room")
            
            if not room:
                continue
            
            print(f"Starting timer for room {room}")
            
            # Spawn timer thread for this room (allows concurrent games)
            timer_thread = threading.Thread(
                target=run_timer_for_room,
                args=(room,),
                daemon=True
            )
            timer_thread.start()
            
        except json.JSONDecodeError:
            print(f"Invalid JSON in start_game message: {msg.get('data')}")
        except Exception as e:
            print(f"Error starting game timer: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("WORDLE BATTLE - GAME WORKER")
    print("=" * 60)
    
    # Create database tables if needed
    with app.app_context():
        db.create_all()
        print("Database tables verified")
    
    start_game_worker()