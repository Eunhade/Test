// static/gamepage.js
// Game page: connects Socket.IO, queues for matchmaking, waits, and plays.

let socket = null;
let currentRoom = null;
let currentUserId = null;
let isPlayerOne = null; // boolean

let presenceInterval = null;
let youName = "You";
let oppName = "Opponent";

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

function setNameLabels(you, opp) {
  youName = you || "You";
  oppName = opp || "Opponent";

  const youEl = document.getElementById("youLabel");
  const oppEl = document.getElementById("oppLabel");
  if (youEl) youEl.textContent = youName;
  if (oppEl) oppEl.textContent = oppName;
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
  document.getElementById("surrenderBtn").disabled = false;
}

function disablePlayControls() {
  document.getElementById("guessInput").disabled = true;
  document.getElementById("submitGuess").disabled = true;
  document.getElementById("surrenderBtn").disabled = true;
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

async function updateNamesForRoom(room) {
  const info = await api(`/match_info?room=${encodeURIComponent(room)}`);
  if (info && !info.error) {
    setNameLabels(info.you_username || "You", info.opponent_username || "Opponent");
  }
}

function startPresenceHeartbeat() {
  if (!socket) return;

  if (presenceInterval) clearInterval(presenceInterval);
  // Ping right away, then every ~20s (online TTL is 60s server-side).
  try { socket.emit("presence"); } catch (_) {}
  presenceInterval = setInterval(() => {
    if (socket && socket.connected) socket.emit("presence");
  }, 20000);
}

async function startRoom(room, isP1) {
  currentRoom = room;
  isPlayerOne = Boolean(isP1);

  // Join server-side Socket.IO room so we receive room broadcasts
  socket.emit("join_room", { room: currentRoom });

  // Fetch and display usernames
  await updateNamesForRoom(currentRoom);

  showStatus("Match found! Starting game...", "success");
  showGame();
  resetGameUI();
}

function initSocket() {
  if (socket) socket.disconnect();
  if (presenceInterval) clearInterval(presenceInterval);

  // Uses cookies/session from Flask-Login
  socket = io();

  socket.on("not_authenticated", () => {
    showStatus("Please log in first", "error");
    setTimeout(() => (window.location = "/"), 800);
  });

  socket.on("disconnect", () => {
    if (presenceInterval) clearInterval(presenceInterval);
    presenceInterval = null;
  });

  socket.on("connected", async (data) => {
    currentUserId = data.user_id;
    document.getElementById("identity").textContent = `Logged in as ${data.username}`;

    startPresenceHeartbeat();

    // First: see if we were already assigned a room (prevents missed match_found)
    const active = await api("/active_match");
    if (active && active.active) {
      await startRoom(active.room, active.is_p1);
      return;
    }

    // Otherwise: queue now and wait
    showWaiting();
    await joinQueue();
  });

  socket.on("match_found", async (data) => {
    if (currentRoom) return;
    await startRoom(data.room, data.is_p1);
  });

  socket.on("timer_update", (data) => {
    const timerEl = document.getElementById("timer");
    timerEl.textContent = formatTime(Number(data.time_left || 0));

    if (data.time_left <= 30) timerEl.style.color = "#d32f2f";
    else if (data.time_left <= 60) timerEl.style.color = "#f57c00";
    else timerEl.style.color = "#667eea";
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

  socket.on("guess_feedback", (data) => displayGuessFeedback(data));
  socket.on("guess_error", (data) => showStatus(data.error || "Guess error", "error"));

  socket.on("new_word", (data) => {
    showStatus(data.message || "Correct!", "success");
    setTimeout(hideStatus, 1500);
  });

  socket.on("game_over", (data) => handleGameOver(data));
}

function submitGuess() {
  if (!socket || !currentRoom) return;

  const input = document.getElementById("guessInput");
  const guess = input.value.trim().toUpperCase();

  if (guess.length !== 5) return showStatus("Guess must be 5 letters", "error");
  if (!guess.match(/^[A-Z]+$/)) return showStatus("Guess must contain only letters", "error");

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

  feedbackEl.insertBefore(row, feedbackEl.firstChild);

  while (feedbackEl.children.length > 6) {
    feedbackEl.removeChild(feedbackEl.lastChild);
  }

  if (data.solved) {
    showStatus("🎉 Correct! +1 point", "success");
    setTimeout(hideStatus, 1200);
  }
}

function surrender() {
  if (!socket || !currentRoom) return showStatus("You're not in a match yet.", "error");

  const ok = window.confirm("Surrender? You will lose and your opponent will win.");
  if (!ok) return;

  disablePlayControls();
  showStatus("You surrendered. Ending match...", "info");
  socket.emit("surrender", { room: currentRoom });
}

function handleGameOver(data) {
  disablePlayControls();

  const p1Score = data.final_scores?.p1 || 0;
  const p2Score = data.final_scores?.p2 || 0;

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

  const myIdNum = currentUserId == null ? null : Number(currentUserId);
  const winnerNum = data.winner_id == null ? null : Number(data.winner_id);

  let message = "Game over.";
  let type = "info";

  if (data.reason === "surrender") {
    const sBy = data.surrendered_by == null ? null : Number(data.surrendered_by);
    if (myIdNum != null && sBy != null && myIdNum === sBy) {
      message = `You surrendered. ${oppName} wins.`;
      type = "info";
    } else {
      message = `${oppName} surrendered. You win!`;
      type = "success";
    }
  } else if (winnerNum == null) {
    message = "It’s a tie!";
  } else if (myIdNum != null && winnerNum === myIdNum) {
    message = "You won! Great job!";
    type = "success";
  } else {
    message = "You lost. Better luck next time!";
  }

  showStatus(message, type);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("backToLobby").onclick = () => (window.location = "/lobby");
  document.getElementById("backToLobby2").onclick = () => (window.location = "/lobby");

  document.getElementById("submitGuess").onclick = submitGuess;
  document.getElementById("guessInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") submitGuess();
  });

  document.getElementById("surrenderBtn").onclick = surrender;

  document.getElementById("playAgain").onclick = async () => {
    currentRoom = null;
    isPlayerOne = null;
    setNameLabels("You", "Opponent");
    showWaiting();
    await joinQueue();
  };

  window.addEventListener("beforeunload", () => {
    if (presenceInterval) clearInterval(presenceInterval);
  });

  showWaiting();
  initSocket();
});
