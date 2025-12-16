const socket = io();

let currentRoom = null;
let isPlayer1 = false;

const waitingArea = document.getElementById("waitingArea");
const gameArea = document.getElementById("gameArea");
const waitingStatus = document.getElementById("waitingStatus");
const cancelQueueBtn = document.getElementById("cancelQueueBtn");

const guessContainer = document.getElementById("guessContainer");
const input = document.getElementById("guessInput");
const submitBtn = document.getElementById("submitBtn");
const surrenderBtn = document.getElementById("surrenderBtn");
const errorBox = document.getElementById("errorMessage");

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
  setTimeout(() => errorBox.classList.add("hidden"), 3000);
}

/* ======================
   TILE UI
====================== */
function renderGuessRow(guess, colors) {
  const row = document.createElement("div");
  row.className = "guess-row";

  for (let i = 0; i < 5; i++) {
    const tile = document.createElement("div");
    tile.className = "letter-tile";
    tile.textContent = guess[i];

    if (colors[i] === "green") tile.classList.add("correct");
    else if (colors[i] === "yellow") tile.classList.add("present");
    else tile.classList.add("absent");

    row.appendChild(tile);
  }
  guessContainer.appendChild(row);
}

/* ======================
   MATCHMAKING
====================== */
async function joinQueue() {
  waitingStatus.textContent = "Joining queue…";
  const res = await fetch("/queue", { method: "POST" });
  const data = await res.json();

  if (!res.ok && !data.error?.includes("Already")) {
    waitingStatus.textContent = "Failed to queue";
  } else {
    waitingStatus.textContent = "Searching for a match…";
  }
}

cancelQueueBtn.onclick = async () => {
  await fetch("/queue/cancel", { method: "POST" });
  window.location.href = "/lobby";
};

/* ======================
   SOCKET EVENTS
====================== */
socket.on("connect", async () => {
  await joinQueue();   // 🔥 THIS WAS MISSING
});

socket.on("match_found", data => {
  currentRoom = data.room;
  isPlayer1 = data.is_p1;

  waitingArea.classList.add("hidden");
  gameArea.classList.remove("hidden");

  socket.emit("join_room", { room: currentRoom });
});

socket.on("guess_feedback", data => {
  renderGuessRow(data.guess, data.colors);
});

socket.on("guess_error", data => showError(data.error));

socket.on("timer_update", data => {
  document.getElementById("timer").textContent =
    Math.floor(data.time_left / 60) + ":" +
    String(data.time_left % 60).padStart(2, "0");
});

/* ======================
   INPUT
====================== */
submitBtn.onclick = () => {
  const guess = input.value.toUpperCase();
  if (guess.length !== 5) return showError("Guess must be 5 letters");

  socket.emit("submit_guess", {
    room: currentRoom,
    guess
  });
  input.value = "";
};

surrenderBtn.onclick = () => {
  if (currentRoom) socket.emit("surrender", { room: currentRoom });
};
