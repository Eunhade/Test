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
  } catch (_) {}
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

document.addEventListener("DOMContentLoaded", async () => {
  // Preload username/stats (panel still hidden until user clicks)
  try {
    await loadStatsIntoPanel();
  } catch (e) {
    console.error(e);
    showStatus("Could not load stats", "error");
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

  document.getElementById("logout").onclick = async () => {
    const res = await api("/logout");
    if (res && res.success) {
      window.location = "/";
    } else {
      showStatus("Logout failed", "error");
    }
  };
});
