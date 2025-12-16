// static/singleplayer.js

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
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(path, opts);
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  data._status = res.status;
  return data;
}

function setGameMessage(text) {
  document.getElementById("gameMessage").textContent = text || "";
}

function setInputEnabled(enabled) {
  const input = document.getElementById("guessInput");
  const btn = document.getElementById("guessBtn");
  input.disabled = !enabled;
  btn.disabled = !enabled;
  if (enabled) input.focus();
}

function renderGuesses(guesses) {
  const el = document.getElementById("guesses");
  el.innerHTML = "";

  if (!Array.isArray(guesses) || guesses.length === 0) return;

  guesses.forEach((g) => {
    const row = document.createElement("div");
    row.className = "sp-row";

    const guess = String(g.guess || "");
    const colors = Array.isArray(g.colors) ? g.colors : [];

    for (let i = 0; i < 5; i++) {
      const tile = document.createElement("div");
      tile.className = `sp-tile ${colors[i] || "gray"}`;
      tile.textContent = guess[i] || "";
      row.appendChild(tile);
    }

    el.appendChild(row);
  });
}

async function startNewGame() {
  const res = await api("/api/new-game", "POST");
  if (!res || !res.success) {
    showStatus(res.error || "Failed to start new game", "error");
    return;
  }
  hideStatus();
  document.getElementById("guesses").innerHTML = "";
  setGameMessage("New game started! Start guessing.");
  document.getElementById("guessInput").value = "";
  setInputEnabled(true);
}

async function submitGuess() {
  const input = document.getElementById("guessInput");
  const raw = input.value.trim();
  if (!raw) return;

  const res = await api("/api/guess", "POST", { guess: raw });

  if (!res || !res.success) {
    setGameMessage(res.error || "Guess failed");
    return;
  }

  renderGuesses(res.guesses || []);

  if (res.status === "won") {
    setGameMessage(`You won! The word was ${res.target}.`);
    showStatus("🎉 Win recorded!", "success");
    setInputEnabled(false);
    await loadStatsPanel();
    await loadLeaderboardPanel();
  } else if (res.status === "lost") {
    setGameMessage(`You lost! The word was ${res.target}.`);
    showStatus("Match recorded.", "warning");
    setInputEnabled(false);
    await loadStatsPanel();
    await loadLeaderboardPanel();
  } else {
    setGameMessage("Keep guessing...");
  }

  input.value = "";
}

function renderStats(stats) {
  const panel = document.getElementById("statsPanel");
  const games = Number(stats.total_games || 0);
  const wins = Number(stats.total_wins || 0);
  const losses = Math.max(0, games - wins);

  panel.innerHTML = `
    <div class="stat">
      <div class="stat-value">${games}</div>
      <div class="stat-label">Games</div>
    </div>
    <div class="stat">
      <div class="stat-value">${wins}</div>
      <div class="stat-label">Wins</div>
    </div>
    <div class="stat">
      <div class="stat-value">${losses}</div>
      <div class="stat-label">Losses</div>
    </div>
    <div class="stat">
      <div class="stat-value">${stats.win_rate ?? 0}%</div>
      <div class="stat-label">Win Rate</div>
    </div>
  `;
}

async function loadStatsPanel() {
  const stats = await api("/stats");
  if (!stats || !stats.username) {
    window.location = "/";
    return;
  }
  renderStats(stats);
}

function renderLeaderboard(list) {
  const el = document.getElementById("leaderboardPanel");
  if (!Array.isArray(list) || list.length === 0) {
    el.innerHTML = `<div style="color: var(--muted);">No players yet.</div>`;
    return;
  }

  const rows = list.map((u, idx) => `
    <tr>
      <td style="padding:10px; font-weight:700;">${idx + 1}</td>
      <td style="padding:10px;">${u.username ?? "—"}</td>
      <td style="padding:10px; text-align:right;">${u.total_wins ?? 0}</td>
      <td style="padding:10px; text-align:right;">${u.total_games ?? 0}</td>
      <td style="padding:10px; text-align:right;">${(u.win_rate ?? 0)}%</td>
    </tr>
  `).join("");

  el.innerHTML = `
    <table style="width:100%; border-collapse:collapse;">
      <thead>
        <tr style="color: var(--muted); text-transform: uppercase; font-size: 12px;">
          <th style="text-align:left; padding:10px;">#</th>
          <th style="text-align:left; padding:10px;">Player</th>
          <th style="text-align:right; padding:10px;">Wins</th>
          <th style="text-align:right; padding:10px;">Games</th>
          <th style="text-align:right; padding:10px;">Win%</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

async function loadLeaderboardPanel() {
  const list = await api("/leaderboard");
  renderLeaderboard(list);
}

document.addEventListener("DOMContentLoaded", async () => {
  // Basic auth check
  try {
    await loadStatsPanel();
    await loadLeaderboardPanel();
  } catch (e) {
    console.error(e);
    showStatus("Could not load data", "error");
  }

  document.getElementById("backToLobby").onclick = () => (window.location = "/lobby");
  document.getElementById("logout").onclick = async () => {
    const res = await api("/logout");
    if (res && res.success) window.location = "/";
    else showStatus("Logout failed", "error");
  };

  document.getElementById("newGame").onclick = startNewGame;

  document.getElementById("guessBtn").onclick = submitGuess;
  document.getElementById("guessInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      submitGuess();
    }
  });

  document.getElementById("toggleStats").onclick = async () => {
    const panel = document.getElementById("statsPanel");
    const isHidden = panel.classList.contains("hidden");
    if (isHidden) {
      await loadStatsPanel();
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  };

  document.getElementById("toggleLeaderboard").onclick = async () => {
    const panel = document.getElementById("leaderboardPanel");
    const isHidden = panel.classList.contains("hidden");
    if (isHidden) {
      await loadLeaderboardPanel();
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  };

  // Start first game automatically
  await startNewGame();
});
