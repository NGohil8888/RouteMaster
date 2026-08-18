let pgMessages = [];
let pgModel = null;
let pgSending = false;

function playgroundContentHtml() {
  return `
    <div class="playground-layout">
      <div class="playground-toolbar">
        <select id="pg-model-select"></select>
        <span class="text-dim" id="pg-model-hint" style="font-size:11.5px;"></span>
        <div style="flex:1"></div>
        <button class="btn btn-sm" id="pg-clear">Clear chat</button>
      </div>
      <div class="chat-window" id="pg-window">
        <div class="chat-msg system">
          <div class="chat-bubble">Pick a model above and send a message. This talks to your own gateway at <span class="mono">/v1/chat/completions</span> with streaming enabled - no separate API key needed.</div>
        </div>
      </div>
      <div class="chat-input-row">
        <textarea id="pg-input" placeholder="Send a message… (Enter to send, Shift+Enter for a new line)" rows="1"></textarea>
        <button class="btn btn-primary" id="pg-send">Send</button>
      </div>
    </div>
  `;
}

function appendMessage(role, text, meta) {
  const win = document.getElementById('pg-window');
  const el = document.createElement('div');
  el.className = `chat-msg ${role}`;
  el.innerHTML = `
    <div class="chat-bubble"></div>
    ${meta ? `<div class="chat-meta">${escapeHtml(meta)}</div>` : ''}
  `;
  el.querySelector('.chat-bubble').textContent = text;
  win.appendChild(el);
  win.scrollTop = win.scrollHeight;
  return el;
}

function appendTypingBubble() {
  const win = document.getElementById('pg-window');
  const el = document.createElement('div');
  el.className = 'chat-msg assistant';
  el.innerHTML = `<div class="chat-bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>`;
  win.appendChild(el);
  win.scrollTop = win.scrollHeight;
  return el;
}

async function sendPlaygroundMessage() {
  if (pgSending) return;
  const input = document.getElementById('pg-input');
  const text = input.value.trim();
  if (!text) return;
  if (!pgModel) {
    toast('Pick a model first', 'error');
    return;
  }

  pgSending = true;
  document.getElementById('pg-send').disabled = true;
  input.value = '';
  input.style.height = 'auto';

  pgMessages.push({ role: 'user', content: text });
  appendMessage('user', text);

  const assistantEl = appendTypingBubble();
  const bubble = assistantEl.querySelector('.chat-bubble');
  const win = document.getElementById('pg-window');
  const start = performance.now();

  try {
    const res = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: pgModel, messages: pgMessages, stream: true }),
    });

    if (!res.ok || !res.body) {
      let msg = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        msg = (errBody.error && errBody.error.message) || errBody.error || msg;
      } catch (e) {
        /* ignore */
      }
      bubble.textContent = '';
      assistantEl.className = 'chat-msg system';
      bubble.textContent = `Error: ${msg}`;
      pgSending = false;
      document.getElementById('pg-send').disabled = false;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let accumulated = '';
    let first = true;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep the last (possibly incomplete) line in the buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data:')) continue;
        const payload = trimmed.slice(5).trim();
        if (payload === '[DONE]') continue;
        try {
          const parsed = JSON.parse(payload);
          const delta = parsed.choices && parsed.choices[0] && parsed.choices[0].delta;
          const chunk = (delta && delta.content) || '';
          if (chunk) {
            if (first) {
              bubble.innerHTML = '';
              first = false;
            }
            accumulated += chunk;
            bubble.textContent = accumulated;
            win.scrollTop = win.scrollHeight;
          }
        } catch (e) {
          /* skip malformed SSE line */
        }
      }
    }

    if (!accumulated) {
      bubble.textContent = '(empty response)';
    }

    const latencyMs = Math.round(performance.now() - start);
    const metaEl = document.createElement('div');
    metaEl.className = 'chat-meta';
    metaEl.textContent = `${pgModel} · ${latencyMs}ms`;
    assistantEl.appendChild(metaEl);

    pgMessages.push({ role: 'assistant', content: accumulated });
  } catch (e) {
    bubble.textContent = `Connection error: ${e.message}`;
    assistantEl.className = 'chat-msg system';
  } finally {
    pgSending = false;
    document.getElementById('pg-send').disabled = false;
    win.scrollTop = win.scrollHeight;
  }
}

function clearPlaygroundChat() {
  pgMessages = [];
  const win = document.getElementById('pg-window');
  win.innerHTML = `
    <div class="chat-msg system">
      <div class="chat-bubble">Chat cleared. Pick a model and send a message to start a new conversation.</div>
    </div>`;
}

async function initModelSelect() {
  const select = document.getElementById('pg-model-select');
  const hint = document.getElementById('pg-model-hint');
  const { models, live } = await fetchLiveModels();

  const params = new URLSearchParams(window.location.search);
  const preselect = params.get('model');

  select.innerHTML = models
    .map((m) => `<option value="${escapeHtml(m)}" ${m === preselect ? 'selected' : ''}>${escapeHtml(m)}</option>`)
    .join('');

  pgModel = preselect && models.includes(preselect) ? preselect : models[0];
  select.value = pgModel;

  hint.textContent = live ? '' : 'Gateway unreachable - showing fallback model names';

  select.addEventListener('change', () => {
    pgModel = select.value;
  });
}

function initPlaygroundPage() {
  document.getElementById('page-content').innerHTML = playgroundContentHtml();
  initModelSelect();

  const input = document.getElementById('pg-input');
  document.getElementById('pg-send').addEventListener('click', sendPlaygroundMessage);
  document.getElementById('pg-clear').addEventListener('click', clearPlaygroundChat);

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendPlaygroundMessage();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  });
}
