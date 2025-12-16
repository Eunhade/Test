const guessContainer = document.getElementById("guessContainer");
const input = document.getElementById("guessInput");
const submitBtn = document.getElementById("submitBtn");
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

async function startGame() {
  await fetch("/singleplayer/start", { method: "POST" });
}

submitBtn.onclick = async () => {
  const guess = input.value.toUpperCase();
  if (guess.length !== 5) return showError("Guess must be 5 letters");

  const res = await fetch("/singleplayer/guess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ guess })
  });

  const data = await res.json();
  if (!res.ok) return showError(data.error);

  renderGuessRow(guess, data.colors);
  input.value = "";

  if (data.solved) {
    guessContainer.innerHTML = "";
  }
};

startGame();
