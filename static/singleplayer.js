let currentRow = 0;
const maxRows = 6;

const grid = document.getElementById("wordGrid");
const input = document.getElementById("guessInput");
const submitBtn = document.getElementById("submitBtn");
const errorBox = document.getElementById("errorMessage");

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
  setTimeout(() => errorBox.classList.add("hidden"), 3000);
}

function initGrid() {
  grid.innerHTML = "";
  currentRow = 0;

  for (let r = 0; r < maxRows; r++) {
    const row = document.createElement("div");
    row.className = "word-row";
    for (let c = 0; c < 5; c++) {
      const cell = document.createElement("div");
      cell.className = "word-cell";
      cell.id = `cell-${r}-${c}`;
      row.appendChild(cell);
    }
    grid.appendChild(row);
  }
}

function updateRow(row, guess, colors) {
  for (let i = 0; i < 5; i++) {
    const cell = document.getElementById(`cell-${row}-${i}`);
    cell.textContent = guess[i];
    cell.classList.add(
      colors[i] === "green" ? "correct" :
      colors[i] === "yellow" ? "present" : "absent"
    );
  }
}

async function startGame() {
  const res = await fetch("/singleplayer/start", { method: "POST" });
  if (!res.ok) showError("Failed to start new game");
}

submitBtn.onclick = async () => {
  const guess = input.value.trim().toUpperCase();
  if (guess.length !== 5) return showError("Guess must be 5 letters");

  const res = await fetch("/singleplayer/guess", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ guess })
  });

  const data = await res.json();
  if (!res.ok) return showError(data.error);

  updateRow(currentRow, guess, data.colors);
  currentRow++;

  if (data.solved || currentRow >= maxRows) {
    initGrid();
  }

  input.value = "";
};

initGrid();
startGame();
