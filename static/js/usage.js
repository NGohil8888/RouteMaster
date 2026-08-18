function usageContentHtml() {
  return `
    <div class="stat-grid" id="usage-stats"></div>
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Per-account usage</div>
      </div>
      <div class="panel-body" id="usage-table"></div>
    </div>
    <div class="field-hint" style="margin-top: 10px;">
      Token counts are read from each response's <span class="mono">usage</span> field and only
      captured for non-streaming requests. Streaming responses aren't counted here yet.
    </div>
  `;
}

function usageRow(acc, maxTokens) {
  const pct = maxTokens > 0 ? Math.round((acc.total_tokens / maxTokens) * 100) : 0;
  const bars = Array.from({ length: 20 }, (_, i) => {
    const filled = i < Math.round((pct / 100) * 20);
    return `<div class="sparkline-bar ${filled ? 'filled' : ''}" style="height:${6 + (i % 4) * 3}px"></div>`;
  }).join('');

  return `
    <tr>
      <td>${escapeHtml(acc.label || `Account ${acc.index + 1}`)}</td>
      <td class="mono">${fmtNumber(acc.total_prompt_tokens)}</td>
      <td class="mono">${fmtNumber(acc.total_completion_tokens)}</td>
      <td class="mono accent" style="color: var(--accent)">${fmtNumber(acc.total_tokens)}</td>
      <td><div class="sparkline">${bars}</div></td>
    </tr>
  `;
}

async function renderUsage() {
  const statsEl = document.getElementById('usage-stats');
  const tableEl = document.getElementById('usage-table');
  if (!statsEl) return;

  try {
    const usage = await API.usage();

    statsEl.innerHTML =
      `<div class="stat-card"><div class="stat-label">Total tokens</div><div class="stat-value accent">${fmtNumber(usage.total_tokens)}</div></div>` +
      `<div class="stat-card"><div class="stat-label">Prompt tokens</div><div class="stat-value">${fmtNumber(usage.total_prompt_tokens)}</div></div>` +
      `<div class="stat-card"><div class="stat-label">Completion tokens</div><div class="stat-value">${fmtNumber(usage.total_completion_tokens)}</div></div>` +
      `<div class="stat-card"><div class="stat-label">Requests served</div><div class="stat-value">${fmtNumber(usage.successful_requests)}</div></div>`;

    if (usage.accounts.length === 0) {
      tableEl.innerHTML = `<div class="empty-state">No accounts configured yet.</div>`;
      return;
    }

    const maxTokens = Math.max(1, ...usage.accounts.map((a) => a.total_tokens || 0));
    tableEl.innerHTML = `
      <table>
        <thead><tr><th>Account</th><th>Prompt</th><th>Completion</th><th>Total</th><th>Share</th></tr></thead>
        <tbody>${usage.accounts.map((a) => usageRow(a, maxTokens)).join('')}</tbody>
      </table>`;
  } catch (e) {
    tableEl.innerHTML = `<div class="empty-state">Could not load usage: ${escapeHtml(e.message)}</div>`;
  }
}

function initUsagePage() {
  document.getElementById('page-content').innerHTML = usageContentHtml();
  renderUsage();
  setInterval(renderUsage, 8000);
}
