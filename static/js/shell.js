/* Renders the shared sidebar/topbar shell into #app-shell on every page.
   Call initShell({ title, subtitle, active }) after DOM is ready. */

function shellHtml(active) {
  const items = [
    { key: 'overview', href: '/dashboard/index.html', label: 'Overview' },
    { key: 'keys', href: '/dashboard/keys.html', label: 'API Keys' },
    { key: 'playground', href: '/dashboard/playground.html', label: 'Playground' },
    { key: 'models', href: '/dashboard/models.html', label: 'Models' },
    { key: 'docs', href: '/dashboard/docs.html', label: 'Quickstart' },
    { key: 'usage', href: '/dashboard/usage.html', label: 'Usage' },
    { key: 'settings', href: '/dashboard/settings.html', label: 'Settings' },
  ];

  const navHtml = items
    .map(
      (it) => `
      <a class="nav-item ${it.key === active ? 'active' : ''}" href="${it.href}">
        <span class="nav-dot"></span>${it.label}
      </a>`
    )
    .join('');

  return `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">ROUTE<span>MASTER</span></div>
        <div class="brand-tag">gateway console</div>
      </div>
      <nav class="nav">${navHtml}</nav>
      <div class="sidebar-footer">Ollama Cloud Failover Gateway</div>
    </aside>
    <div class="main">
      <div class="topbar">
        <div>
          <div class="topbar-title" id="shell-title"></div>
          <div class="topbar-sub" id="shell-subtitle"></div>
        </div>
        <div class="status-pill" id="shell-status">
          <span class="pulse-dot" id="shell-status-dot"></span>
          <span id="shell-status-text">loading…</span>
        </div>
      </div>
      <div class="content" id="page-content"></div>
    </div>
    <div class="toast-stack"></div>
  `;
}

function initShell({ title, subtitle, active }) {
  const root = document.getElementById('app-shell');
  root.innerHTML = shellHtml(active);
  document.getElementById('shell-title').textContent = title;
  document.getElementById('shell-subtitle').textContent = subtitle || '';
  installAuthGate();
  refreshShellStatus();
  setInterval(refreshShellStatus, 8000);
}

// --- admin token gate ------------------------------------------------------
// If the server has GATEWAY_ADMIN_TOKEN set, the dashboard shows an unlock
// overlay until the user enters the token. The token is stored in
// sessionStorage (cleared on tab close) and attached to every subsequent
// /api/* request via X-Gateway-Token.

let authOverlayInstalled = false;

function installAuthGate() {
  if (authOverlayInstalled) return;
  authOverlayInstalled = true;

  const overlay = document.createElement('div');
  overlay.className = 'auth-overlay hidden';
  overlay.id = 'auth-overlay';
  overlay.innerHTML = `
    <div class="auth-modal">
      <div class="auth-modal-title">Admin token required</div>
      <div class="auth-modal-desc">This RouteMaster gateway is locked. Enter the admin token configured via GATEWAY_ADMIN_TOKEN or the Settings page.</div>
      <div class="field">
        <input id="auth-token-input" type="password" autocomplete="off" placeholder="Admin token" />
      </div>
      <div class="auth-modal-error" id="auth-modal-error"></div>
      <div class="auth-modal-actions">
        <button class="btn btn-primary btn-sm" id="auth-token-submit">Unlock</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const submit = () => {
    const input = document.getElementById('auth-token-input');
    const token = input.value.trim();
    if (!token) return;
    setAdminToken(token);
    // Verify by hitting a cheap endpoint. On success, hide overlay and
    // refresh the page content; on failure, clear the token and show error.
    API.authStatus()
      .then((st) => {
        if (st.ok) {
          overlay.classList.add('hidden');
          document.getElementById('auth-modal-error').textContent = '';
          window.location.reload();
        } else {
          setAdminToken('');
          document.getElementById('auth-modal-error').textContent = 'Wrong token.';
        }
      })
      .catch(() => {
        setAdminToken('');
        document.getElementById('auth-modal-error').textContent = 'Could not reach the gateway.';
      });
  };

  document.getElementById('auth-token-submit').addEventListener('click', submit);
  document.getElementById('auth-token-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submit();
  });
}

async function checkAuthBeforeApiCalls() {
  try {
    const st = await API.authStatus();
    if (st.required && !st.ok) {
      const overlay = document.getElementById('auth-overlay');
      if (overlay) overlay.classList.remove('hidden');
      return false;
    }
  } catch (e) {
    /* gateway unreachable - page-level error handlers will surface it */
  }
  return true;
}

async function refreshShellStatus() {
  const dot = document.getElementById('shell-status-dot');
  const text = document.getElementById('shell-status-text');
  if (!dot || !text) return;
  try {
    const ov = await API.overview();
    const { total, healthy, available } = ov.accounts;
    if (total === 0) {
      dot.className = 'pulse-dot warn';
      text.textContent = 'no accounts configured';
    } else if (available === 0) {
      dot.className = 'pulse-dot down';
      text.textContent = `0/${total} available`;
    } else if (available < total) {
      dot.className = 'pulse-dot warn';
      text.textContent = `${available}/${total} available`;
    } else {
      dot.className = 'pulse-dot';
      text.textContent = `${healthy}/${total} healthy`;
    }
  } catch (e) {
    if (e && e.code === 'AUTH_REQUIRED') {
      // The unlock overlay is already showing - don't compete with it
      // for the status pill.
      dot.className = 'pulse-dot warn';
      text.textContent = 'locked - enter admin token';
      return;
    }
    dot.className = 'pulse-dot down';
    text.textContent = 'gateway unreachable';
  }
}
