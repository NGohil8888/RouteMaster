let selectedModel = 'gpt-oss:20b-cloud';
let baseUrl = window.location.origin;

function codeBlock(label, code) {
  const id = `code-${Math.random().toString(36).slice(2, 9)}`;
  return `
    <div class="code-block">
      <div class="code-block-header">
        <span class="code-block-label">${label}</span>
        <button class="copy-btn" data-target="${id}">Copy</button>
      </div>
      <pre id="${id}">${escapeHtml(code)}</pre>
    </div>
  `;
}

function docSection(title, desc, blocksHtml) {
  return `
    <div class="doc-section">
      <div class="doc-section-title">${title}</div>
      <div class="doc-section-desc">${desc}</div>
      ${blocksHtml}
    </div>
  `;
}

function buildExamples() {
  const url = `${baseUrl}/v1/chat/completions`;
  const model = selectedModel;

  const curlBash = `curl ${url} \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`;

  const curlWindows = `curl.exe ${url} -H "Content-Type: application/json" -d '{"model": "${model}", "messages": [{"role": "user", "content": "Hello!"}]}'`;

  const powershell = `Invoke-RestMethod -Uri "${url}" \`
  -Method POST \`
  -ContentType "application/json" \`
  -Body '{"model": "${model}", "messages": [{"role": "user", "content": "Hello!"}]}'`;

  const pythonOpenaiSdk = `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="not-needed",  # the gateway injects real Ollama Cloud keys for you
)

response = client.chat.completions.create(
    model="${model}",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)`;

  const pythonRequests = `import requests

response = requests.post(
    "${url}",
    json={
        "model": "${model}",
        "messages": [{"role": "user", "content": "Hello!"}],
    },
)
print(response.json()["choices"][0]["message"]["content"])`;

  const nodeOpenaiSdk = `import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${baseUrl}/v1",
  apiKey: "not-needed", // the gateway injects real Ollama Cloud keys for you
});

const response = await client.chat.completions.create({
  model: "${model}",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(response.choices[0].message.content);`;

  const streamingCurl = `curl ${url} \\
  -H "Content-Type: application/json" \\
  -N \\
  -d '{
    "model": "${model}",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'`;

  const continueConfig = `{
  "models": [
    {
      "title": "RouteMaster (${model})",
      "provider": "openai",
      "model": "${model}",
      "apiBase": "${baseUrl}/v1",
      "apiKey": "not-needed"
    }
  ]
}`;

  const openWebUiEnv = `# Point Open WebUI / LibreChat / any OpenAI-compatible client here:
OPENAI_API_BASE_URL=${baseUrl}/v1
OPENAI_API_KEY=not-needed`;

  const langchain = `from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="${baseUrl}/v1",
    api_key="not-needed",
    model="${model}",
)
print(llm.invoke("Hello!").content)`;

  return `
    <div class="callout">
      <strong>No client-side API key required.</strong> The gateway injects one of your configured
      Ollama Cloud accounts automatically and handles failover between them. Any string works as a
      placeholder API key in the examples below — most SDKs require one to be present, but the
      gateway ignores it.
    </div>

    ${docSection('cURL (Mac/Linux)', 'Basic chat completion.', codeBlock('bash', curlBash))}
    ${docSection('cURL (Windows / PowerShell)', 'PowerShell aliases <code>curl</code> to <code>Invoke-WebRequest</code>, which parses flags differently - use <code>curl.exe</code> or native <code>Invoke-RestMethod</code> instead.',
      codeBlock('curl.exe', curlWindows) + codeBlock('powershell', powershell))}
    ${docSection('Python - openai SDK', 'Recommended if you already use <code>pip install openai</code>. Just point <code>base_url</code> here.', codeBlock('python', pythonOpenaiSdk))}
    ${docSection('Python - raw requests', 'No dependency beyond <code>requests</code>.', codeBlock('python', pythonRequests))}
    ${docSection('Node.js - openai SDK', 'Recommended if you already use <code>npm install openai</code>.', codeBlock('javascript', nodeOpenaiSdk))}
    ${docSection('Streaming', 'Add <code>"stream": true</code> and (for curl) <code>-N</code> to disable output buffering.', codeBlock('bash', streamingCurl))}
    ${docSection('Continue.dev (VS Code)', 'Add this to your Continue <code>config.json</code> under <code>models</code>.', codeBlock('json', continueConfig))}
    ${docSection('Open WebUI / LibreChat / generic env-based tools', 'Most self-hosted chat UIs read these two env vars.', codeBlock('.env', openWebUiEnv))}
    ${docSection('LangChain', 'Works with any LangChain <code>ChatOpenAI</code>-based integration.', codeBlock('python', langchain))}
  `;
}

function docsContentHtml() {
  return `
    <div class="model-picker">
      <label class="text-muted" style="font-size:12.5px;" for="model-select">Model used in examples:</label>
      <select id="model-select"></select>
      <span class="text-dim" id="model-picker-hint" style="font-size:11.5px;"></span>
    </div>
    <div id="docs-body"></div>
  `;
}

function renderExamples() {
  document.getElementById('docs-body').innerHTML = buildExamples();
  document.querySelectorAll('.copy-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.target);
      const text = target.textContent;
      navigator.clipboard
        .writeText(text)
        .then(() => {
          btn.textContent = 'Copied';
          btn.classList.add('copied');
          setTimeout(() => {
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
          }, 1500);
        })
        .catch(() => toast('Could not copy - select and copy manually', 'error'));
    });
  });
}

async function loadModelOptions() {
  const select = document.getElementById('model-select');
  const hint = document.getElementById('model-picker-hint');
  const fallback = ['gpt-oss:20b-cloud', 'qwen3-coder:480b-cloud', 'gemma4:cloud'];

  let models = [];
  try {
    const res = await fetch('/v1/models');
    if (res.ok) {
      const data = await res.json();
      models = (data.data || []).map((m) => m.id).filter(Boolean);
    }
  } catch (e) {
    /* ignore, use fallback */
  }

  const options = models.length > 0 ? models : fallback;
  select.innerHTML = options.map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
  selectedModel = options[0];

  hint.textContent =
    models.length > 0
      ? `${models.length} model(s) live from your account`
      : 'Could not reach /v1/models - showing common Ollama Cloud model names as a fallback';

  select.addEventListener('change', () => {
    selectedModel = select.value;
    renderExamples();
  });

  renderExamples();
}

function initDocsPage() {
  document.getElementById('page-content').innerHTML = docsContentHtml();
  loadModelOptions();
}
