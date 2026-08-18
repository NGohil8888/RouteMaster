function modelsContentHtml() {
  return `
    <div class="callout">
      <strong>About "free" vs "needs upgrade":</strong> Ollama Cloud's model list itself doesn't carry
      a free/paid flag - every model shows up regardless of plan. But some models genuinely are
      plan-gated: requesting one you don't have access to returns a specific error
      ("this model requires a subscription, upgrade for access"). The "Est. resource tier" column is
      just a size-based guess to help prioritize what to check. Click <strong>Check access</strong> on
      any model for a real, live answer instead of a guess - it sends a minimal request through your
      own gateway and reports exactly what Ollama Cloud says.
    </div>
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Available models</div>
        <span class="text-dim" id="models-source-hint" style="font-size:11.5px;"></span>
      </div>
      <div class="panel-body" id="models-list"></div>
    </div>
  `;
}

function modelRow(id) {
  const tier = estimateTier(id);
  const rowId = `model-row-${id.replace(/[^a-zA-Z0-9]/g, '-')}`;
  return `
    <tr id="${rowId}" data-model="${escapeHtml(id)}">
      <td class="mono">${escapeHtml(id)}</td>
      <td><span class="tier-badge ${tier.cls}">${tier.label}</span></td>
      <td class="access-result text-dim">—</td>
      <td>
        <button class="btn btn-sm btn-check">Check access</button>
        <a class="btn btn-sm" href="/dashboard/playground.html?model=${encodeURIComponent(id)}">Try in Playground</a>
      </td>
    </tr>
  `;
}

async function checkModelAccess(id, row) {
  const cell = row.querySelector('.access-result');
  const btn = row.querySelector('.btn-check');
  btn.disabled = true;
  cell.textContent = 'checking…';
  cell.className = 'access-result text-muted';

  try {
    const res = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: id,
        messages: [{ role: 'user', content: 'hi' }],
        max_tokens: 1,
      }),
    });

    if (res.ok) {
      cell.textContent = 'available';
      cell.className = 'access-result';
      cell.style.color = 'var(--success)';
    } else {
      let msg = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        msg = (body.error && (body.error.message || body.error)) || msg;
      } catch (e) {
        /* ignore */
      }
      const needsUpgrade = /subscription|upgrade for access/i.test(String(msg));
      cell.textContent = needsUpgrade ? 'needs upgrade' : `error (${res.status})`;
      cell.className = 'access-result';
      cell.style.color = needsUpgrade ? 'var(--warning)' : 'var(--danger)';
      cell.title = String(msg);
    }
  } catch (e) {
    cell.textContent = 'error';
    cell.className = 'access-result';
    cell.style.color = 'var(--danger)';
    cell.title = e.message;
  } finally {
    btn.disabled = false;
  }
}

async function renderModels() {
  const listEl = document.getElementById('models-list');
  const hintEl = document.getElementById('models-source-hint');

  const { models, live } = await fetchLiveModels();
  hintEl.textContent = live
    ? `${models.length} model(s) from your account`
    : 'Gateway unreachable - showing common Ollama Cloud models as a fallback';

  if (models.length === 0) {
    listEl.innerHTML = `<div class="empty-state">No models returned. Check that at least one API key is configured and healthy.</div>`;
    return;
  }

  listEl.innerHTML = `
    <table>
      <thead><tr><th>Model</th><th>Est. resource tier</th><th>Access</th><th></th></tr></thead>
      <tbody>${models.map(modelRow).join('')}</tbody>
    </table>`;

  listEl.querySelectorAll('tr[data-model]').forEach((row) => {
    row.querySelector('.btn-check').addEventListener('click', () => checkModelAccess(row.dataset.model, row));
  });
}

function initModelsPage() {
  document.getElementById('page-content').innerHTML = modelsContentHtml();
  renderModels();
}
