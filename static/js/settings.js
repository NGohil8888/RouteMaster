const SETTINGS_FIELDS = [
  { key: 'max_retries', label: 'Max retries', hint: 'Accounts to try per request before giving up', unit: '' },
  { key: 'account_cooldown_seconds', label: 'Account cooldown', hint: 'Base cooldown after a failure (grows with backoff)', unit: 'sec' },
  { key: 'health_check_interval_seconds', label: 'Health check interval', hint: 'How often the background monitor checks accounts', unit: 'sec' },
  { key: 'request_timeout_seconds', label: 'Request timeout', hint: 'Timeout for non-streaming requests', unit: 'sec' },
  { key: 'stream_timeout_seconds', label: 'Stream timeout', hint: 'Timeout for streaming requests', unit: 'sec' },
  { key: 'max_concurrent_requests_per_account', label: 'Max concurrent / account', hint: 'Concurrency cap per account', unit: '' },
];

// String-typed fields shown separately because they don't take a number input.
const STRING_FIELDS = [
  {
    key: 'gateway_admin_token',
    label: 'Admin token',
    hint: 'When set, dashboard /api/* endpoints require this token (sent as X-Gateway-Token). Leave blank to keep the current token; type a new value to replace it; set to empty + save to clear.',
    isPassword: true,
  },
];

function settingsContentHtml() {
  const numericFields = SETTINGS_FIELDS.map(
    (f) => `
      <div class="field">
        <label for="set-${f.key}">${f.label}${f.unit ? ` <span class="text-dim">(${f.unit})</span>` : ''}</label>
        <input id="set-${f.key}" type="number" step="any" />
        <div class="field-hint">${f.hint}</div>
      </div>`
  ).join('');

  const stringFields = STRING_FIELDS.map(
    (f) => `
      <div class="field">
        <label for="set-${f.key}">${f.label} <span class="text-dim" id="set-${f.key}-status"></span></label>
        <input id="set-${f.key}" type="${f.isPassword ? 'password' : 'text'}" autocomplete="off" placeholder="(unchanged)" />
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
        ${numericFields}
      </div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Access control</div>
      </div>
      <div class="panel-body" style="padding: 20px 18px;">
        ${stringFields}
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
    STRING_FIELDS.forEach((f) => {
      const status = document.getElementById(`set-${f.key}-status`);
      if (status) status.textContent = current[f.key] ? '(set)' : '(not set)';
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

  // For each string field, only send the value if the user typed something
  // non-empty (an empty typed value is the "clear" signal). We never read
  // the current value back from the server (it's never returned), so "leave
  // blank to keep current" is implemented by sending nothing.
  STRING_FIELDS.forEach((f) => {
    const input = document.getElementById(`set-${f.key}`);
    if (!input) return;
    const value = input.value;
    if (value === '') {
      // Send a sentinel "clear" value - empty string after trim. This wipes
      // the stored token. Distinguish from "unchanged" by the user actually
      // touching the field: rely on the user being deliberate.
      patch[f.key] = '';
    } else {
      patch[f.key] = value;
    }
  });

  btn.disabled = true;
  try {
    await API.updateSettings(patch);
    toast('Settings saved and applied', 'success');
    // Refresh "set / not set" labels without re-rendering the form so the
    // password field is cleared from view after submit.
    STRING_FIELDS.forEach((f) => {
      const input = document.getElementById(`set-${f.key}`);
      if (input) input.value = '';
    });
    loadSettings();
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
