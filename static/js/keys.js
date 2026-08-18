function keysContentHtml() {
  return `
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Accounts</div>
        <button class="btn btn-primary btn-sm" id="btn-add-key">+ Add key</button>
      </div>
      <div class="panel-body" id="keys-list"></div>
    </div>

    <div class="modal-overlay hidden" id="key-modal">
      <div class="modal">
        <div class="modal-title" id="key-modal-title">Add API key</div>
        <div class="field">
          <label for="key-label-input">Label</label>
          <input id="key-label-input" placeholder="e.g. Personal account" />
        </div>
        <div class="field">
          <label for="key-value-input">API key</label>
          <input id="key-value-input" placeholder="sk-..." autocomplete="off" />
          <div class="field-hint" id="key-value-hint"></div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-sm" id="key-modal-cancel">Cancel</button>
          <button class="btn btn-primary btn-sm" id="key-modal-save">Save</button>
        </div>
      </div>
    </div>
  `;
}

let editingKeyId = null;

function keyRow(k) {
  const st = k.status;
  const state = st ? st.state : 'unknown';
  const successCount = st ? st.success_count : 0;
  const failureCount = st ? st.failure_count : 0;
  const tokens = st ? st.total_tokens : 0;

  return `
    <tr data-id="${k.id}">
      <td>${escapeHtml(k.label)}</td>
      <td><span class="badge ${state}"><span class="badge-dot"></span>${stateLabel(state)}</span></td>
      <td class="key-preview">${escapeHtml(k.key_preview)}</td>
      <td class="mono text-muted">${fmtNumber(successCount)} / ${fmtNumber(failureCount)}</td>
      <td class="mono text-muted">${fmtNumber(tokens)}</td>
      <td class="test-result text-dim">—</td>
      <td>
        <button class="btn btn-sm btn-test">Test</button>
        <button class="btn btn-sm btn-edit">Edit</button>
        <button class="btn btn-sm btn-danger btn-delete">Delete</button>
      </td>
    </tr>
  `;
}

async function loadKeys() {
  const listEl = document.getElementById('keys-list');
  try {
    const keys = await API.keys();
    if (keys.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">NO KEYS YET</div>
          <div>Add your first Ollama Cloud API key to start routing requests.</div>
        </div>`;
      return;
    }
    listEl.innerHTML = `
      <table>
        <thead>
          <tr><th>Label</th><th>State</th><th>Key</th><th>Success/Fail</th><th>Tokens</th><th>Last test</th><th></th></tr>
        </thead>
        <tbody>${keys.map(keyRow).join('')}</tbody>
      </table>`;

    listEl.querySelectorAll('tr[data-id]').forEach((row) => {
      const id = row.dataset.id;
      const key = keys.find((k) => k.id === id);
      row.querySelector('.btn-test').addEventListener('click', () => testKey(id, row));
      row.querySelector('.btn-edit').addEventListener('click', () => openEditModal(key));
      row.querySelector('.btn-delete').addEventListener('click', () => deleteKey(id, key.label));
    });
  } catch (e) {
    listEl.innerHTML = `<div class="empty-state">Could not load keys: ${escapeHtml(e.message)}</div>`;
  }
}

async function testKey(id, row) {
  const cell = row.querySelector('.test-result');
  const btn = row.querySelector('.btn-test');
  btn.disabled = true;
  cell.textContent = 'testing…';
  cell.className = 'test-result text-muted';
  try {
    const result = await API.testKey(id);
    if (result.success) {
      cell.textContent = `ok · ${result.latency_ms}ms`;
      cell.className = 'test-result mono';
      cell.style.color = 'var(--success)';
      toast(`Key works (${result.latency_ms}ms)`, 'success');
    } else {
      cell.textContent = `failed · ${result.status_code || 'error'}`;
      cell.className = 'test-result mono';
      cell.style.color = 'var(--danger)';
      toast(result.error || 'Key test failed', 'error');
    }
  } catch (e) {
    cell.textContent = 'error';
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

async function deleteKey(id, label) {
  if (!confirm(`Remove "${label}"? This cannot be undone.`)) return;
  try {
    await API.deleteKey(id);
    toast(`Removed "${label}"`, 'success');
    loadKeys();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function openAddModal() {
  editingKeyId = null;
  document.getElementById('key-modal-title').textContent = 'Add API key';
  document.getElementById('key-label-input').value = '';
  document.getElementById('key-value-input').value = '';
  document.getElementById('key-value-input').placeholder = 'sk-...';
  document.getElementById('key-value-hint').textContent = '';
  document.getElementById('key-modal').classList.remove('hidden');
}

function openEditModal(key) {
  editingKeyId = key.id;
  document.getElementById('key-modal-title').textContent = 'Edit API key';
  document.getElementById('key-label-input').value = key.label;
  document.getElementById('key-value-input').value = '';
  document.getElementById('key-value-input').placeholder = key.key_preview;
  document.getElementById('key-value-hint').textContent = 'Leave blank to keep the current key.';
  document.getElementById('key-modal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('key-modal').classList.add('hidden');
}

async function saveModal() {
  const label = document.getElementById('key-label-input').value.trim();
  const apiKey = document.getElementById('key-value-input').value.trim();
  const saveBtn = document.getElementById('key-modal-save');

  if (!editingKeyId && !apiKey) {
    toast('API key is required', 'error');
    return;
  }

  saveBtn.disabled = true;
  try {
    if (editingKeyId) {
      const patch = {};
      if (label) patch.label = label;
      if (apiKey) patch.api_key = apiKey;
      await API.updateKey(editingKeyId, patch);
      toast('Key updated', 'success');
    } else {
      await API.createKey(label, apiKey);
      toast('Key added', 'success');
    }
    closeModal();
    loadKeys();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    saveBtn.disabled = false;
  }
}

function initKeysPage() {
  document.getElementById('page-content').innerHTML = keysContentHtml();
  loadKeys();
  setInterval(loadKeys, 8000);

  document.getElementById('btn-add-key').addEventListener('click', openAddModal);
  document.getElementById('key-modal-cancel').addEventListener('click', closeModal);
  document.getElementById('key-modal-save').addEventListener('click', saveModal);
  document.getElementById('key-modal').addEventListener('click', (e) => {
    if (e.target.id === 'key-modal') closeModal();
  });
}
