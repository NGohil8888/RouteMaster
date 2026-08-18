function modelsContentHtml() {
  return `
    <div class="callout">
      <strong>About "free" vs "needs upgrade":</strong> Ollama Cloud doesn't publish a per-model
      free/paid flag through its API - every model in your account's list is technically callable
      on any plan. What actually varies by plan (Free / Pro / Max) is your <em>weekly usage quota</em>,
      measured in GPU time, not a fixed model paywall. Heavier models simply burn through that quota
      faster. The "Est. resource tier" column below is a size-based estimate to help you guess which
      models are quota-friendly on the Free plan - it is <strong>not</strong> an official designation.
      Check <a href="https://ollama.com/pricing" target="_blank" rel="noopener">ollama.com/pricing</a>
      for actual plan limits.
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
  return `
    <tr>
      <td class="mono">${escapeHtml(id)}</td>
      <td><span class="tier-badge ${tier.cls}">${tier.label}</span></td>
      <td>
        <a class="btn btn-sm" href="/dashboard/playground.html?model=${encodeURIComponent(id)}">Try in Playground</a>
      </td>
    </tr>
  `;
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
      <thead><tr><th>Model</th><th>Est. resource tier</th><th></th></tr></thead>
      <tbody>${models.map(modelRow).join('')}</tbody>
    </table>`;
}

function initModelsPage() {
  document.getElementById('page-content').innerHTML = modelsContentHtml();
  renderModels();
}
