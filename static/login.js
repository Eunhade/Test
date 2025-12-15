// static/login.js

function showStatus(message, type = "info") {
  const el = document.getElementById("status");
  el.textContent = message;
  el.className = `status ${type}`;
  el.classList.remove("hidden");
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
    // ignore
  }
  data._status = res.status;
  return data;
}

document.addEventListener("DOMContentLoaded", () => {
  const usernameEl = document.getElementById("username");
  const passwordEl = document.getElementById("password");

  document.getElementById("register").onclick = async () => {
    const username = usernameEl.value.trim();
    const password = passwordEl.value;

    if (!username || !password) {
      showStatus("Please enter username and password", "error");
      return;
    }

    const res = await api("/register", "POST", { username, password });
    if (res.success) {
      showStatus("Account created! Please log in.", "success");
      return;
    }
    showStatus(res.error || "Registration failed", "error");
  };

  async function doLogin() {
    const username = usernameEl.value.trim();
    const password = passwordEl.value;

    if (!username || !password) {
      showStatus("Please enter username and password", "error");
      return;
    }

    const res = await api("/login", "POST", { username, password });
    if (res.success) {
      window.location = "/lobby";
      return;
    }
    showStatus(res.error || "Login failed", "error");
  }

  document.getElementById("login").onclick = doLogin;
  passwordEl.addEventListener("keypress", (e) => {
    if (e.key === "Enter") doLogin();
  });
});
