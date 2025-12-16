import time
import uuid
from wordle_logic import random_word

# TTL for Redis keys to prevent memory leaks
GAME_TTL = 60 * 60  # 1 hour
DEFAULT_DURATION = 300  # 5 minutes

def create_game(r, p1_id, p2_id, duration=DEFAULT_DURATION) -> str:
    """Initialize a new game in Redis with two players."""
    room = str(uuid.uuid4())

    gkey = f"game:{room}:meta"
    timer_key = f"game:{room}:timer"

    # Store meta and timer
    r.hset(gkey, mapping={
        "p1": str(p1_id),
        "p2": str(p2_id),
        "score_p1": 0,
        "score_p2": 0,
        "duration": int(duration),
        "started_at": int(time.time()),
    })
    r.set(timer_key, int(duration))

    # Assign initial secret words per player
    set_player_word(r, room, p1_id, random_word())
    set_player_word(r, room, p2_id, random_word())

    # TTLs
    r.expire(gkey, GAME_TTL)
    r.expire(timer_key, GAME_TTL)
    r.expire(f"game:{room}:player:{p1_id}:word", GAME_TTL)
    r.expire(f"game:{room}:player:{p2_id}:word", GAME_TTL)

    return room


def get_player_word(r, room: str, player_id) -> str | None:
    key = f"game:{room}:player:{player_id}:word"
    word = r.get(key)
    return word


def set_player_word(r, room: str, player_id, word: str):
    key = f"game:{room}:player:{player_id}:word"
    r.set(key, word)
    r.expire(key, GAME_TTL)


def increment_score(r, room: str, player_id):
    gkey = f"game:{room}:meta"
    p1 = r.hget(gkey, "p1")
    p1_str = p1.decode() if isinstance(p1, bytes) else str(p1)
    player_str = str(player_id)

    if player_str == p1_str:
        r.hincrby(gkey, "score_p1", 1)
    else:
        r.hincrby(gkey, "score_p2", 1)


def get_scores(r, room: str) -> dict:
    gkey = f"game:{room}:meta"
    score_p1 = r.hget(gkey, "score_p1")
    score_p2 = r.hget(gkey, "score_p2")
    return {"p1": int(score_p1 or 0), "p2": int(score_p2 or 0)}


def get_game_meta(r, room: str) -> dict:
    gkey = f"game:{room}:meta"
    return r.hgetall(gkey)


def end_game_cleanup(r, room: str):
    """Remove Redis keys for this room and clear active match assignments."""
    meta = get_game_meta(r, room) or {}
    p1 = meta.get("p1")
    p2 = meta.get("p2")

    # Delete game keys
    r.delete(f"game:{room}:meta")
    r.delete(f"game:{room}:timer")

    if p1:
        r.delete(f"game:{room}:player:{p1}:word")
        r.delete(f"user:{p1}:active_room")
        r.delete(f"user:{p1}:active_is_p1")
    if p2:
        r.delete(f"game:{room}:player:{p2}:word")
        r.delete(f"user:{p2}:active_room")
        r.delete(f"user:{p2}:active_is_p1")
