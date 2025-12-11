#!/bin/bash
# Start all services in one container

echo "Starting Wordle Battle services..."

# Start matchmaker worker in background
python matchmaker_worker.py &
MATCHMAKER_PID=$!
echo "Matchmaker worker started (PID: $MATCHMAKER_PID)"

# Start game worker in background
python game_worker.py &
GAME_WORKER_PID=$!
echo "Game worker started (PID: $GAME_WORKER_PID)"

# Start web server in foreground
echo "Starting web server on port $PORT"
gunicorn --worker-class eventlet -w 1 app:app --bind 0.0.0.0:$PORT

# If gunicorn exits, kill background workers
kill $MATCHMAKER_PID $GAME_WORKER_PID 2>/dev/null