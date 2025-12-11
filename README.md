# Wordle Battle -CSE 108 Final Project- Multiplayer Word Game

A real-time multiplayer competitive Wordle game where two players race to solve as many 5-letter words as possible within a 5-minute time limit.

### Components

1. **Flask App** (`app.py`)
   - Handles user authentication (Flask-Login)
   - Manages WebSocket connections (SocketIO)
   - Serves the web interface
   - Processes game actions (guesses, scores)

2. **Matchmaker Worker** (`matchmaker_worker.py`)
   - Monitors the matchmaking queue
   - Pairs players together
   - Creates new game rooms
   - Publishes match events

3. **Game Worker** (`game_worker.py`)
   - Runs countdown timers for active games
   - Publishes timer updates every second
   - Handles game completion
   - Persists match results to database
   - Updates player statistics

4. **Redis**
   - Stores game state (scores, timers, player words)
   - Manages matchmaking queue
   - Pub/sub for inter-process communication
   - Session storage

5. **PostgreSQL/SQLite**
   - User accounts and authentication
   - Match history
   - Player statistics (wins, games played, win rate)

## Setup & Installation

### Prerequisites

- Python 3.8+
- Redis server
- PostgreSQL (production) or SQLite (development)

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd FinalProject
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your-secret-key-here-change-in-production
   PORT=5000
   DATABASE_URL=sqlite:///local.db
   REDIS_URL=redis://localhost:6379/0
   ```

5. **Start Redis server**
   ```bash
   redis-server
   ```

6. **Initialize database**
   ```bash
   python app.py
   # This will create the database tables on first run
   # Then stop it (Ctrl+C) to run the full system
   ```

## Running the Application

You need to run **THREE separate processes** for the full system:

### Terminal 1: Flask App
```bash
python app.py
```
Runs on `http://localhost:5000`

### Terminal 2: Matchmaker Worker
```bash
python matchmaker_worker.py
```
Handles player matchmaking

### Terminal 3: Game Worker
```bash
python game_worker.py
```
Manages game timers and match completion

### Access the Game
Open your browser and navigate to:
```
http://localhost:5000
```