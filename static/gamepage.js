// static/gamepage.js
// Game page: connects Socket.IO, queues for matchmaking, waits, and plays.

let socket = null;
let currentRoom = null;
let currentUserId = null;
let isPlayerOne = null; // boolean

function showStatus(message, type = "info") {
  const el = document.getElementById("status");
  el.textContent = message;
  el.className = `status ${type}`;
  el.classList.remove("hidden");
}

function hideStatus() {
  document.getElementById("status").classList.add("hidden");
}

async function api(path, method = "GET", body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(path, opts);
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    // If we got HTML, the session probably expired
    data = {};
  }
  data._status = res.status;
  return data;
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function showWaiting() {
  document.getElementById("waiting").classList.remove("hidden");
  document.getElementById("game").classList.add("hidden");
}

function showGame() {
  document.getElementById("waiting").classList.add("hidden");
  document.getElementById("game").classList.remove("hidden");
}

function resetGameUI() {
  document.getElementById("scoreP1").textContent = "0";
  document.getElementById("scoreP2").textContent = "0";
  const timerEl = document.getElementById("timer");
  timerEl.textContent = "5:00";
  timerEl.style.color = "";

  document.getElementById("feedback").innerHTML = "";
  const input = document.getElementById("guessInput");
  input.value = "";
  input.disabled = false;
  document.getElementById("submitGuess").disabled = false;
}

async function joinQueue() {
  const res = await api("/queue", "POST");
  if (res.queued) {
    showStatus("Searching for opponent...", "info");
    return;
  }
  if (res.error === "Already in queue") {
    showStatus("Already searching for an opponent...", "info");
    return;
  }
  showStatus(res.error || "Failed to join queue", "error");
}

async function startRoom(room, isP1) {
  currentRoom = room;
  isPlayerOne = Boolean(isP1);

  socket.emit("join_room", { room: currentRoom });

  // show the game immediately, then fetch names
  showStatus("Match found! Starting game...", "success");
  showGame();
  resetGameUI();

  await updateNamesForRoom(currentRoom);
}
function initSocket() {
  if (socket) socket.disconnect();

  // Uses cookies/session from Flask-Login
  socket = io();

  socket.on("not_authenticated", () => {
    showStatus("Please log in first", "error");
    setTimeout(() => (window.location = "/"), 800);
  });

  socket.on("disconnect", () => {
    if (window.__hbInterval) {
      clearInterval(window.__hbInterval);
      window.__hbInterval = null;
    }
  });

  socket.on("connected", async (data) => {
    currentUserId = data.user_id;
    document.getElementById("identity").textContent = `Logged in as ${data.username}`;

    // Keep online presence fresh for the matchmaker (TTL-based)
    if (window.__hbInterval) clearInterval(window.__hbInterval);
    window.__hbInterval = setInterval(() => {
      try {
        if (socket && socket.connected) socket.emit("heartbeat");
      } catch (_) {}
    }, 25000);

    // First: see if we were already assigned a room (prevents missed match_found)
    const active = await api("/active_match");
    if (active && active.active) {
      startRoom(active.room, active.is_p1);
      return;
    }

    // Otherwise: queue now and wait
    showWaiting();
    await joinQueue();
  });

  socket.on("match_found", (data) => {
    // If we were already in a room (refresh), ignore duplicates
    if (currentRoom) return;
    startRoom(data.room, data.is_p1);
  });

  socket.on("timer_update", (data) => {
    const timerEl = document.getElementById("timer");
    timerEl.textContent = formatTime(Number(data.time_left || 0));

    if (data.time_left <= 30) {
      timerEl.style.color = "#d32f2f";
    } else if (data.time_left <= 60) {
      timerEl.style.color = "#f57c00";
    } else {
      timerEl.style.color = "#667eea";
    }
  });

  socket.on("score_update", (data) => {
    let myScore, oppScore;

    if (isPlayerOne) {
      myScore = data.p1;
      oppScore = data.p2;
    } else {
      myScore = data.p2;
      oppScore = data.p1;
    }

    document.getElementById("scoreP1").textContent = String(myScore ?? 0);
    document.getElementById("scoreP2").textContent = String(oppScore ?? 0);
  });

  socket.on("guess_feedback", (data) => {
    displayGuessFeedback(data);
  });

  socket.on("guess_error", (data) => {
    showStatus(data.error || "Guess error", "error");
  });

  socket.on("new_word", (data) => {
    showStatus(data.message || "Correct!", "success");
    setTimeout(hideStatus, 1500);
  });

  socket.on("game_over", (data) => {
    handleGameOver(data);
  });
}

function submitGuess() {
  if (!socket || !currentRoom) return;

  const input = document.getElementById("guessInput");
  const guess = input.value.trim().toUpperCase();

  if (guess.length !== 5) {
    showStatus("Guess must be 5 letters", "error");
    return;
  }

  if (!guess.match(/^[A-Z]+$/)) {
    showStatus("Guess must contain only letters", "error");
    return;
  }

  socket.emit("submit_guess", { room: currentRoom, guess });
  input.value = "";
}

function displayGuessFeedback(data) {
  const feedbackEl = document.getElementById("feedback");

  const row = document.createElement("div");
  row.className = "feedback-row";

  for (let i = 0; i < data.guess.length; i++) {
    const box = document.createElement("div");
    box.className = `letter-box ${data.colors[i]}`;
    box.textContent = data.guess[i];
    row.appendChild(box);
  }

  // Most recent first
  feedbackEl.insertBefore(row, feedbackEl.firstChild);

  // Keep only last 6
  while (feedbackEl.children.length > 6) {
    feedbackEl.removeChild(feedbackEl.lastChild);
  }

  if (data.solved) {
    showStatus("🎉 Correct! +1 point", "success");
    setTimeout(hideStatus, 1200);
  }
}
async function updateNamesForRoom(room) {
  const info = await api(`/match_info?room=${encodeURIComponent(room)}`);
  if (info && !info.error) {
    document.getElementById("youLabel").textContent = info.you_username || "You";
    document.getElementById("oppLabel").textContent = info.opponent_username || "Opponent";
  }
}
function handleGameOver(data) {
  const input = document.getElementById("guessInput");
  input.disabled = true;
  document.getElementById("submitGuess").disabled = true;

  const p1Score = data.final_scores?.p1 || 0;
  const p2Score = data.final_scores?.p2 || 0;
  const winnerId = data.winner_id;

  let myScore, oppScore;
  if (isPlayerOne) {
    myScore = p1Score;
    oppScore = p2Score;
  } else {
    myScore = p2Score;
    oppScore = p1Score;
  }

  document.getElementById("scoreP1").textContent = String(myScore);
  document.getElementById("scoreP2").textContent = String(oppScore);

  let message;
  if (winnerId == null) {
    message = "It’s a tie!";
  } else if (currentUserId != null && Number(winnerId) === Number(currentUserId)) {
    message = "You won! Great job!";
  } else {
    message = "You lost. Better luck next time!";
  }

  showStatus(message, winnerId === currentUserId ? "success" : "info");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("backToLobby").onclick = () => (window.location = "/lobby");
  document.getElementById("backToLobby2").onclick = () => (window.location = "/lobby");

  document.getElementById("submitGuess").onclick = submitGuess;
  document.getElementById("guessInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") submitGuess();
  });

  document.getElementById("playAgain").onclick = async () => {
    // Reset state and queue again
    currentRoom = null;
    isPlayerOne = null;
    showWaiting();
    await joinQueue();
  };

  showWaiting();
  initSocket();
});
