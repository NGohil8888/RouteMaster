/* Renders the shared sidebar/topbar shell into #app-shell on every page.
   Call initShell({ title, subtitle, active }) after DOM is ready. */

function shellHtml(active) {
  const items = [
    { key: 'overview', href: '/dashboard/index.html', label: 'Overview' },
    { key: 'keys', href: '/dashboard/keys.html', label: 'API Keys' },
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
  refreshShellStatus();
  setInterval(refreshShellStatus, 8000);
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
    dot.className = 'pulse-dot down';
    text.textContent = 'gateway unreachable';
  }
}
