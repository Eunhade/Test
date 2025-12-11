import time
import uuid
from wordle_logic import random_word

# TTL for Redis keys to prevent memory leaks
GAME_TTL = 60 * 60  # 1 hour
DEFAULT_DURATION = 300  # 5 minutes

def create_game(r, p1_id, p2_id, duration=DEFAULT_DURATION) -> str:
    """
    Initialize a new game in Redis with two players.
    
    Creates:
    - Game metadata (players, scores, timing)
    - Player-specific word assignments
    - Timer state
    
    Args:
        r: Redis connection
        p1_id: Player 1 user ID
        p2_id: Player 2 user ID
        duration: Game length in seconds
        
    Returns:
        Unique room identifier
    """
    room = uuid.uuid4().hex
    gkey = f"game:{room}:meta"
    now = int(time.time())
    
    # Store game metadata
    r.hset(gkey, mapping={
        "p1": str(p1_id),
        "p2": str(p2_id),
        "score_p1": 0,
        "score_p2": 0,
        "start_time": now,
        "state": "active",
        "duration": duration
    })
    r.expire(gkey, GAME_TTL)

    # Initialize timer
    r.set(f"game:{room}:time_left", duration)
    r.expire(f"game:{room}:time_left", GAME_TTL)
    
    # Assign random words to each player (scoped to room AND player)
    word1 = random_word()
    word2 = random_word()
    r.set(f"game:{room}:player:{p1_id}:word", word1)
    r.set(f"game:{room}:player:{p2_id}:word", word2)
    r.expire(f"game:{room}:player:{p1_id}:word", GAME_TTL)
    r.expire(f"game:{room}:player:{p2_id}:word", GAME_TTL)
    
    return room

def get_player_word(r, room: str, player_id) -> str:
    """Retrieve the current word for a player in a specific room."""
    word = r.get(f"game:{room}:player:{player_id}:word")
    return word.decode() if isinstance(word, bytes) else word

def set_player_word(r, room: str, player_id, word: str):
    """Assign a new word to a player in a specific room."""
    r.set(f"game:{room}:player:{player_id}:word", word)
    r.expire(f"game:{room}:player:{player_id}:word", GAME_TTL)

def increment_score(r, room: str, player_id):
    """
    Increment score for a player who solved a word.
    
    Args:
        r: Redis connection
        room: Game room identifier
        player_id: ID of player who scored
    """
    gkey = f"game:{room}:meta"
    p1 = r.hget(gkey, "p1")
    
    # Convert to string for comparison (Redis returns bytes or strings)
    p1_str = p1.decode() if isinstance(p1, bytes) else str(p1)
    player_str = str(player_id)
    
    if player_str == p1_str:
        r.hincrby(gkey, "score_p1", 1)
    else:
        r.hincrby(gkey, "score_p2", 1)

def get_scores(r, room: str) -> dict:
    """
    Retrieve current scores for both players.
    
    Returns:
        dict with 'p1' and 'p2' scores
    """
    gkey = f"game:{room}:meta"
    score_p1 = r.hget(gkey, "score_p1")
    score_p2 = r.hget(gkey, "score_p2")
    
    return {
        "p1": int(score_p1 or 0),
        "p2": int(score_p2 or 0)
    }

def get_game_meta(r, room: str) -> dict:
    """Retrieve all game metadata."""
    gkey = f"game:{room}:meta"
    return r.hgetall(gkey)

def end_game_cleanup(r, room: str):
    """
    Remove Redis keys for a completed game.
    
    Called after match data is persisted to database.
    """
    gkey = f"game:{room}:meta"
    game_meta = r.hgetall(gkey)
    
    # Clean up game metadata and timer
    r.delete(f"game:{room}:meta")
    r.delete(f"game:{room}:time_left")
    
    # Clean up player words if we have player IDs
    if game_meta:
        p1 = game_meta.get("p1")
        p2 = game_meta.get("p2")
        if p1:
            r.delete(f"game:{room}:player:{p1}:word")
        if p2:
            r.delete(f"game:{room}:player:{p2}:word")