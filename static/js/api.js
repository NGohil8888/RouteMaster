/* Shared helpers for the dashboard: API calls, formatting, toasts. */

const API = {
  async _req(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      /* no body */
    }
    if (!res.ok) {
      const msg = (data && (data.detail || (data.error && data.error.message))) || `HTTP ${res.status}`;
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return data;
  },
  get(path) { return this._req('GET', path); },
  post(path, body) { return this._req('POST', path, body); },
  put(path, body) { return this._req('PUT', path, body); },
  del(path) { return this._req('DELETE', path); },

  overview() { return this.get('/api/overview'); },
  keys() { return this.get('/api/keys'); },
  createKey(label, api_key) { return this.post('/api/keys', { label, api_key }); },
  updateKey(id, patch) { return this.put(`/api/keys/${id}`, patch); },
  deleteKey(id) { return this.del(`/api/keys/${id}`); },
  testKey(id) { return this.post(`/api/keys/${id}/test`); },
  usage() { return this.get('/api/usage'); },
  settings() { return this.get('/api/settings'); },
  updateSettings(patch) { return this.put('/api/settings', patch); },
};

function fmtNumber(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString();
}

function fmtRelativeTime(iso) {
  if (!iso) return 'never';
  const then = new Date(iso).getTime();
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
}

function stateLabel(state) {
  return (state || 'unknown').replace(/_/g, ' ');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str ?? '';
  return div.innerHTML;
}

function toast(message, type = 'success') {
  let stack = document.querySelector('.toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}
