import os
import time
import redis
import json
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

QUEUE_KEY = "matchmaking_queue"
EVENT_CHANNEL = "events"
START_GAME_CHANNEL = "start_game"

# Store active match assignment per user (avoids missing match_found when page reloads)
ACTIVE_MATCH_TTL = 60 * 60  # 1 hour

# Online presence key written by the web server on Socket.IO connect + heartbeat
ONLINE_KEY_FMT = "user:{uid}:online"
ACTIVE_ROOM_FMT = "user:{uid}:active_room"

def is_online(uid: str) -> bool:
    try:
        return bool(r.exists(ONLINE_KEY_FMT.format(uid=uid)))
    except Exception:
        return False

def has_active_match(uid: str) -> bool:
    try:
        return bool(r.exists(ACTIVE_ROOM_FMT.format(uid=uid)))
    except Exception:
        return False

def pop_valid_player(timeout: int):
    """Pop a player from the queue who is online and not already in an active match."""
    while True:
        result = r.brpop(QUEUE_KEY, timeout=timeout)
        if not result:
            return None

        _, uid = result
        uid = str(uid)

        if not is_online(uid):
            print(f"Discarding offline queued user {uid}")
            continue
        if has_active_match(uid):
            print(f"Discarding already-matched queued user {uid}")
            continue

        return uid


def start_matchmaker():
    """
    Main matchmaking loop.

    Blocks waiting for players in queue, pairs them, creates games,
    and publishes match_found events.
    """
    print("Matchmaker worker started")
    print(f"Watching queue: {QUEUE_KEY}")
    print(f"Publishing to: {EVENT_CHANNEL}, {START_GAME_CHANNEL}")

    while True:
        try:
            p1 = pop_valid_player(timeout=0)
            if not p1:
                continue
            print(f"Player {p1} pulled from queue")

            p2 = pop_valid_player(timeout=2)
            if not p2:
                # Only one player available, push back and wait longer
                print(f"No second valid player found, pushing {p1} back to queue")
                r.lpush(QUEUE_KEY, p1)
                time.sleep(1)
                continue

            print(f"Player {p2} pulled from queue")

            # Ensure we don't match a player with themselves
            if str(p1) == str(p2):
                print(f"Same player ID detected ({p1}), pushing back")
                r.lpush(QUEUE_KEY, p1)
                continue

            # Import here to avoid circular dependencies
            from game import create_game

            # Create game in Redis
            room = create_game(r, p1, p2)
            TTL = 60 * 60

            # Persist match assignment for each user so the web UI can recover
            # even if the SocketIO event is missed (navigation / refresh).
            r.setex(f"user:{p1}:active_room", ACTIVE_MATCH_TTL, room)
            r.setex(f"user:{p1}:active_is_p1", ACTIVE_MATCH_TTL, "1")
            r.setex(f"user:{p2}:active_room", ACTIVE_MATCH_TTL, room)
            r.setex(f"user:{p2}:active_is_p1", ACTIVE_MATCH_TTL, "0")

            print(f"Matched: Player {p1} vs Player {p2} in room {room}")

            # Notify web server via pubsub that match was found
            match_found_payload = {
                "type": "match_found",
                "room": room,
                "players": [str(p1), str(p2)]
            }
            r.publish(EVENT_CHANNEL, json.dumps(match_found_payload))

            # Signal game_worker to start timer for this room
            start_game_payload = {
                "room": room,
                "players": [str(p1), str(p2)]
            }
            r.publish(START_GAME_CHANNEL, json.dumps(start_game_payload))

        except redis.RedisError as e:
            print(f"Redis error in matchmaker: {e}")
            time.sleep(1)
        except Exception as e:
            print(f"Unexpected error in matchmaker: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(1)


if __name__ == "__main__":
    print("=" * 60)
    print("WORDLE BATTLE - MATCHMAKER WORKER")
    print("=" * 60)
    start_matchmaker()
