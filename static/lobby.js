// static/lobby.js

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
    data = {};
  }
  data._status = res.status;
  return data;
}

async function loadStatsIntoPanel() {
  const stats = await api("/stats");

  // If session expired, /stats will likely redirect to HTML; json parse would fail => {}
  if (!stats || !stats.username) {
    window.location = "/";
    return;
  }

  document.getElementById("usernameDisplay").textContent = stats.username;

  const games = Number(stats.total_games || 0);
  const wins = Number(stats.total_wins || 0);
  const losses = Math.max(0, games - wins);

  document.getElementById("statGames").textContent = String(games);
  document.getElementById("statWins").textContent = String(wins);
  document.getElementById("statLosses").textContent = String(losses);
  document.getElementById("statWinRate").textContent = `${stats.win_rate ?? 0}%`;
}

function renderLeaderboard(list) {
  const el = document.getElementById("leaderboard");
  if (!Array.isArray(list) || list.length === 0) {
    el.innerHTML = `<div style="color: var(--muted);">No players yet.</div>`;
    return;
  }

  const rows = list.map((u, idx) => {
    const winRate = (u.win_rate ?? 0);
    return `
      <tr>
        <td style="padding:10px; font-weight:700;">${idx + 1}</td>
        <td style="padding:10px;">${u.username ?? "—"}</td>
        <td style="padding:10px; text-align:right;">${u.total_wins ?? 0}</td>
        <td style="padding:10px; text-align:right;">${u.total_games ?? 0}</td>
        <td style="padding:10px; text-align:right;">${winRate}%</td>
      </tr>
    `;
  }).join("");

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

async function loadLeaderboard() {
  const list = await api("/leaderboard");
  // /leaderboard returns a JSON array on success
  renderLeaderboard(list);
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await loadStatsIntoPanel();
    await loadLeaderboard();
  } catch (e) {
    console.error(e);
    showStatus("Could not load lobby data", "error");
  }

  document.getElementById("toggleStats").onclick = async () => {
    const panel = document.getElementById("statsPanel");
    const isHidden = panel.classList.contains("hidden");

    if (isHidden) {
      try {
        await loadStatsIntoPanel();
      } catch (_) {}
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  };

  document.getElementById("findMatch").onclick = () => {
    hideStatus();
    window.location = "/game";
  };

  document.getElementById("singlePlayer").onclick = () => {
    hideStatus();
    window.location = "/singleplayer";
  };

  document.getElementById("logout").onclick = async () => {
    const res = await api("/logout");
    if (res && res.success) {
      window.location = "/";
    } else {
      showStatus("Logout failed", "error");
    }
  };
});
