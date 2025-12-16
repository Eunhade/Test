const socket = io();
let currentRoom = null;
let isPlayer1 = false;

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
  if (!currentRoom) return;
  socket.emit("surrender", { room: currentRoom });
};

socket.on("match_found", data => {
  currentRoom = data.room;
  isPlayer1 = data.is_p1;
  document.getElementById("waitingArea").classList.add("hidden");
  document.getElementById("gameArea").classList.remove("hidden");
});

socket.on("guess_feedback", data => {
  renderGuessRow(data.guess, data.colors);
});

socket.on("guess_error", data => showError(data.error));
