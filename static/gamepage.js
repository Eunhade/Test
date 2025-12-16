// gamepage.js - Multiplayer game client with active match restore + name display + surrender
// UPDATED: auto-join matchmaking queue on /game load + cancel queue button

const socket = io();

let currentRoom = null;
let isPlayer1 = null;
let currentUserId = null;
let currentUsername = null;

let matchStarted = false;
let matchEnded = false;

let currentWordRow = 0;
let currentGuesses = [];
const maxRows = 6;

let heartbeatInterval = null;

// DOM elements
const waitingArea = document.getElementById("waitingArea");
const gameArea = document.getElementById("gameArea");
const waitingStatus = document.getElementById("waitingStatus");
const opponentStatus = document.getElementById("opponentStatus");
const timerElement = document.getElementById("timer");
const myScoreElement = document.getElementById("myScore");
const oppScoreElement = document.getElementById("oppScore");
const youLabel = document.getElementById("youLabel");
const oppLabel = document.getElementById("oppLabel");
const gameMessage = document.getElementById("gameMessage");
const wordGrid = document.getElementById("wordGrid");
const guessInput = document.getElementById("guessInput");
const submitBtn = document.getElementById("submitBtn");
const surrenderBtn = document.getElementById("surrenderBtn");
const cancelQueueBtn = document.getElementById("cancelQueueBtn");
const backToLobbyBtn = document.getElementById("backToLobbyBtn");
const errorMessage = document.getElementById("errorMessage");
const gameResults = document.getElementById("gameResults");
const resultMessage = document.getElementById("resultMessage");
const finalScores = document.getElementById("finalScores");
const playAgainBtn = document.getElementById("playAgainBtn");
const connectionStatus = document.getElementById("connectionStatus");

function startHeartbeat() {
  if (heartbeatInterval) clearInterval(heartbeatInterval);
  heartbeatInterval = setInterval(() => {
    try {
      if (socket && socket.connected) socket.emit("presence");
    } catch (_) {}
  }, 20000);
}

function stopHeartbeat() {
  if (heartbeatInterval) clearInterval(heartbeatInterval);
  heartbeatInterval = null;
}

async function postJson(path, body = null) {
  const opts = { method: "POST", headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (_) { data = {}; }
  data._status = res.status;
  return data;
}

async function queueForMatch() {
  try {
    waitingStatus.textContent = "Joining matchmaking queue...";
    const res = await postJson("/queue");
    if (res.queued) {
      waitingStatus.textContent = "Searching for a match...";
      return true;
    }
    if (res._status === 400 && (res.error || "").toLowerCase().includes("already")) {
      waitingStatus.textContent = "Searching for a match...";
      return true;
    }
    waitingStatus.textContent = res.error || "Failed to join queue";
    return false;
  } catch (_) {
    waitingStatus.textContent = "Failed to join queue";
    return false;
  }
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.classList.remove("hidden");
  setTimeout(() => errorMessage.classList.add("hidden"), 3000);
}

function hideError() {
  errorMessage.classList.add("hidden");
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function initGrid() {
  wordGrid.innerHTML = "";
  currentWordRow = 0;
  currentGuesses = [];

  for (let row = 0; row < maxRows; row++) {
    const rowDiv = document.createElement("div");
    rowDiv.className = "word-row";

    for (let col = 0; col < 5; col++) {
      const cell = document.createElement("div");
      cell.className = "word-cell";
      cell.id = `cell-${row}-${col}`;
      rowDiv.appendChild(cell);
    }
    wordGrid.appendChild(rowDiv);
  }
}

function updateRowWithGuess(row, guess, colors) {
  for (let col = 0; col < 5; col++) {
    const cell = document.getElementById(`cell-${row}-${col}`);
    if (!cell) continue;
    cell.textContent = guess[col] || "";
    cell.classList.remove("correct", "present", "absent");
    if (colors[col] === "green") cell.classList.add("correct");
    else if (colors[col] === "yellow") cell.classList.add("present");
    else if (colors[col] === "gray") cell.classList.add("absent");
  }
}

function getMeAndOpponentScores(scores) {
  const p1 = Number(scores?.p1 ?? 0);
  const p2 = Number(scores?.p2 ?? 0);
  return isPlayer1 ? { me: p1, opp: p2 } : { me: p2, opp: p1 };
}

async function updateNamesForRoom(room) {
  if (!room) return;
  try {
    const res = await fetch(`/match_info?room=${encodeURIComponent(room)}`);
    if (!res.ok) return;
    const data = await res.json();

    if (youLabel) youLabel.textContent = data.you_username || "You";
    if (oppLabel) oppLabel.textContent = data.opponent_username || "Opponent";

    if (opponentStatus && data.opponent_username) {
      opponentStatus.textContent = `Opponent: ${data.opponent_username}`;
    }
  } catch (_) {}
}

function setWaitingUI() {
  waitingArea.classList.remove("hidden");
  gameArea.classList.add("hidden");
  waitingStatus.textContent = "Searching for a match...";
  opponentStatus.textContent = "";
  connectionStatus.textContent = socket.connected ? "Connected" : "Connecting...";
}

function setGameUI() {
  waitingArea.classList.add("hidden");
  gameArea.classList.remove("hidden");
  connectionStatus.textContent = "In Game";
}

function disableInputs(disabled) {
  guessInput.disabled = disabled;
  submitBtn.disabled = disabled;
  if (surrenderBtn) surrenderBtn.disabled = disabled;
}

function handleGameOver(data) {
  matchEnded = true;
  disableInputs(true);
  stopHeartbeat();

  gameResults.classList.remove("hidden");

  const final = data?.final_scores || {};
  const scores = getMeAndOpponentScores(final);

  const winnerId = data?.winner_id ?? null;
  const reason = data?.reason || "time";
  const surrenderedBy = data?.surrendered_by ?? null;

  let msg = "";
  if (reason === "surrender") {
    if (surrenderedBy && currentUserId && Number(surrenderedBy) === Number(currentUserId)) {
      msg = "You surrendered. You lose.";
    } else {
      msg = "Your opponent surrendered. You win!";
    }
  } else {
    if (winnerId === null || winnerId === undefined) {
      msg = "It's a tie!";
    } else if (currentUserId && Number(winnerId) === Number(currentUserId)) {
      msg = "You win!";
    } else {
      msg = "You lose!";
    }
  }

  resultMessage.textContent = msg;
  finalScores.innerHTML = `
        <p><strong>${youLabel ? youLabel.textContent : "You"}:</strong> ${scores.me}</p>
        <p><strong>${oppLabel ? oppLabel.textContent : "Opponent"}:</strong> ${scores.opp}</p>
    `;

  connectionStatus.textContent = "Game Over";
}

async function tryRestoreActiveMatch() {
  try {
    const res = await fetch("/active_match");
    if (!res.ok) return false;
    const data = await res.json();

    if (!data.active) return false;

    currentRoom = data.room;
    isPlayer1 = !!data.is_p1;
    matchStarted = true;
    matchEnded = false;

    setGameUI();
    initGrid();
    disableInputs(false);

    socket.emit("join_room", { room: currentRoom });
    updateNamesForRoom(currentRoom);

    if (opponentStatus) opponentStatus.textContent = "Match restored. Rejoining...";
    return true;
  } catch (_) {
    return false;
  }
}

// --------------------
// Socket.IO handlers
// --------------------
socket.on("connect", () => {
  connectionStatus.textContent = "Connected";
  startHeartbeat();
});

socket.on("disconnect", () => {
  connectionStatus.textContent = "Disconnected";
});

socket.on("connected", (data) => {
  currentUserId = data.user_id;
  currentUsername = data.username;

  tryRestoreActiveMatch().then(async (restored) => {
    if (!restored) {
      setWaitingUI();
      await queueForMatch(); // ✅ THIS WAS MISSING IN YOUR ZIP
    }
  });
});

socket.on("match_found", (data) => {
  if (matchStarted && currentRoom) return;
  matchStarted = true;
  matchEnded = false;

  currentRoom = data.room;
  isPlayer1 = !!data.is_p1;

  waitingStatus.textContent = "Match found! Preparing game...";
  opponentStatus.textContent = "Starting soon...";

  setGameUI();
  initGrid();
  disableInputs(false);

  if (surrenderBtn) {
    surrenderBtn.disabled = false;
    surrenderBtn.textContent = "Surrender";
  }

  setTimeout(() => {
    socket.emit("join_room", { room: currentRoom });
  }, 150);

  updateNamesForRoom(currentRoom);
});

socket.on("timer_update", (data) => {
  if (matchEnded) return;
  const t = Number(data.time_left ?? 0);
  timerElement.textContent = formatTime(Math.max(0, t));
});

socket.on("score_update", (scores) => {
  if (matchEnded) return;
  const s = getMeAndOpponentScores(scores);
  myScoreElement.textContent = String(s.me);
  oppScoreElement.textContent = String(s.opp);
});

socket.on("guess_feedback", (data) => {
  hideError();

  const guess = data.guess || "";
  const colors = data.colors || [];
  const solved = !!data.solved;

  currentGuesses.push(guess);
  updateRowWithGuess(currentWordRow, guess, colors);
  currentWordRow++;

  if (solved) guessInput.value = "";

  if (currentWordRow >= maxRows) initGrid();
});

socket.on("new_word", (data) => {
  if (data?.message) {
    gameMessage.textContent = data.message;
    setTimeout(() => (gameMessage.textContent = "Guess the 5-letter word!"), 1500);
  }
});

socket.on("guess_error", (data) => {
  showError(data.error || "Error");
});

socket.on("game_over", (data) => {
  handleGameOver(data);
});

// --------------------
// UI events
// --------------------
submitBtn.addEventListener("click", () => {
  if (matchEnded) return;
  if (!currentRoom) return;

  const guess = (guessInput.value || "").trim().toUpperCase();

  if (guess.length !== 5) {
    showError("Guess must be 5 letters");
    return;
  }

  socket.emit("submit_guess", { room: currentRoom, guess });
  guessInput.value = "";
});

guessInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitBtn.click();
});

if (surrenderBtn) {
  surrenderBtn.addEventListener("click", () => {
    if (matchEnded) return;
    if (!currentRoom) return;

    const ok = confirm("Are you sure you want to surrender? You will lose this match.");
    if (!ok) return;

    surrenderBtn.disabled = true;
    surrenderBtn.textContent = "Surrendering...";
    disableInputs(true);

    socket.emit("surrender", { room: currentRoom });
  });
}

if (cancelQueueBtn) {
  cancelQueueBtn.addEventListener("click", async () => {
    try {
      cancelQueueBtn.disabled = true;
      waitingStatus.textContent = "Canceling queue...";
      await postJson("/queue/cancel");
      stopHeartbeat();
      window.location.href = "/lobby";
    } catch (_) {
      cancelQueueBtn.disabled = false;
      waitingStatus.textContent = "Failed to cancel queue";
    }
  });
}

if (backToLobbyBtn) {
  backToLobbyBtn.addEventListener("click", async () => {
    try { await postJson("/queue/cancel"); } catch (_) {}
    stopHeartbeat();
    window.location.href = "/lobby";
  });
}

playAgainBtn.addEventListener("click", () => {
  window.location.href = "/lobby";
});

// Initial UI
setWaitingUI();
