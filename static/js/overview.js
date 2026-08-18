function overviewContentHtml() {
  return `
    <div class="stat-grid" id="ov-stats"></div>
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Account Health</div>
        <a class="btn btn-sm" href="/dashboard/keys.html">Manage keys</a>
      </div>
      <div class="panel-body" id="ov-accounts"></div>
    </div>
  `;
}

function statCard(label, value, cls = '') {
  return `
    <div class="stat-card">
      <div class="stat-label">${label}</div>
      <div class="stat-value ${cls}">${value}</div>
    </div>
  `;
}

function accountRow(acc) {
  const state = acc.state || 'unknown';
  return `
    <tr>
      <td>${escapeHtml(acc.label || `Account ${acc.index + 1}`)}</td>
      <td><span class="badge ${state}"><span class="badge-dot"></span>${stateLabel(state)}</span></td>
      <td class="key-preview">${escapeHtml(acc.key_preview || '')}</td>
      <td class="mono">${fmtNumber(acc.success_count)}</td>
      <td class="mono">${fmtNumber(acc.failure_count)}</td>
      <td class="text-muted">${fmtRelativeTime(acc.last_used)}</td>
    </tr>
  `;
}

async function renderOverview() {
  const statsEl = document.getElementById('ov-stats');
  const accountsEl = document.getElementById('ov-accounts');
  if (!statsEl) return;

  try {
    const [ov, usage] = await Promise.all([API.overview(), API.usage()]);

    statsEl.innerHTML =
      statCard('Accounts', `${ov.accounts.available}/${ov.accounts.total}`, ov.accounts.available > 0 ? 'success' : 'danger') +
      statCard('Requests', fmtNumber(ov.requests.total)) +
      statCard('Successful', fmtNumber(ov.requests.successful), 'success') +
      statCard('Failed', fmtNumber(ov.requests.failed), ov.requests.failed > 0 ? 'danger' : '') +
      statCard('Total Tokens', fmtNumber(usage.total_tokens), 'accent') +
      statCard('Uptime', `${Math.round(ov.uptime_seconds)}s`);

    if (usage.accounts.length === 0) {
      accountsEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">NO ACCOUNTS CONFIGURED</div>
          <div>Add an Ollama Cloud API key to get started.</div>
          <div style="margin-top: 14px;"><a class="btn btn-primary" href="/dashboard/keys.html">Add a key</a></div>
        </div>`;
    } else {
      accountsEl.innerHTML = `
        <table>
          <thead>
            <tr>
              <th>Account</th><th>State</th><th>Key</th><th>Success</th><th>Failures</th><th>Last used</th>
            </tr>
          </thead>
          <tbody>${usage.accounts.map(accountRow).join('')}</tbody>
        </table>`;
    }
  } catch (e) {
    accountsEl.innerHTML = `<div class="empty-state">Could not reach the gateway: ${escapeHtml(e.message)}</div>`;
  }
}

function initOverviewPage() {
  document.getElementById('page-content').innerHTML = overviewContentHtml();
  renderOverview();
  setInterval(renderOverview, 6000);
}
