const SETTINGS_FIELDS = [
  { key: 'max_retries', label: 'Max retries', hint: 'Accounts to try per request before giving up', unit: '' },
  { key: 'account_cooldown_seconds', label: 'Account cooldown', hint: 'Base cooldown after a failure (grows with backoff)', unit: 'sec' },
  { key: 'health_check_interval_seconds', label: 'Health check interval', hint: 'How often the background monitor checks accounts', unit: 'sec' },
  { key: 'request_timeout_seconds', label: 'Request timeout', hint: 'Timeout for non-streaming requests', unit: 'sec' },
  { key: 'stream_timeout_seconds', label: 'Stream timeout', hint: 'Timeout for streaming requests', unit: 'sec' },
  { key: 'max_concurrent_requests_per_account', label: 'Max concurrent / account', hint: 'Concurrency cap per account', unit: '' },
];

function settingsContentHtml() {
  const fields = SETTINGS_FIELDS.map(
    (f) => `
      <div class="field">
        <label for="set-${f.key}">${f.label}${f.unit ? ` <span class="text-dim">(${f.unit})</span>` : ''}</label>
        <input id="set-${f.key}" type="number" step="any" />
        <div class="field-hint">${f.hint}</div>
      </div>`
  ).join('');

  return `
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Gateway configuration</div>
        <button class="btn btn-primary btn-sm" id="btn-save-settings">Save changes</button>
      </div>
      <div class="panel-body" style="padding: 20px 18px;">
        ${fields}
      </div>
    </div>
  `;
}

async function loadSettings() {
  try {
    const current = await API.settings();
    SETTINGS_FIELDS.forEach((f) => {
      const input = document.getElementById(`set-${f.key}`);
      if (input) input.value = current[f.key];
    });
  } catch (e) {
    toast(`Could not load settings: ${e.message}`, 'error');
  }
}

async function saveSettings() {
  const btn = document.getElementById('btn-save-settings');
  const patch = {};
  SETTINGS_FIELDS.forEach((f) => {
    const input = document.getElementById(`set-${f.key}`);
    if (input && input.value !== '') patch[f.key] = Number(input.value);
  });

  btn.disabled = true;
  try {
    await API.updateSettings(patch);
    toast('Settings saved and applied', 'success');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
  }
}

function initSettingsPage() {
  document.getElementById('page-content').innerHTML = settingsContentHtml();
  loadSettings();
  document.getElementById('btn-save-settings').addEventListener('click', saveSettings);
}
