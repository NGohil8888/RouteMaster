/* Shared model utilities: fetch the live model list from the gateway, and
   estimate a rough "resource tier" from the model's parameter size in its
   name. Ollama Cloud does NOT publish an official per-model free/paid flag
   via the API - access is governed by weekly usage quota (GPU time) that
   varies by plan, not a hard per-model paywall. This is a best-effort
   estimate, not an authoritative answer, and is labeled as such in the UI. */

const FALLBACK_MODELS = [
  'gpt-oss:20b-cloud',
  'gpt-oss:120b-cloud',
  'qwen3-coder:480b-cloud',
  'deepseek-v3.1:671b-cloud',
  'gemma4:cloud',
];

async function fetchLiveModels() {
  try {
    const res = await fetch('/v1/models');
    if (!res.ok) return { models: FALLBACK_MODELS, live: false };
    const data = await res.json();
    const ids = (data.data || []).map((m) => m.id).filter(Boolean);
    return { models: ids.length > 0 ? ids : FALLBACK_MODELS, live: ids.length > 0 };
  } catch (e) {
    return { models: FALLBACK_MODELS, live: false };
  }
}

function estimateTier(modelId) {
  // Look for a parameter-count hint like "20b", "480b", "1t" anywhere in the id.
  const match = modelId.toLowerCase().match(/(\d+(?:\.\d+)?)\s*([bt])(?!\w)/);
  if (!match) {
    return { key: 'unknown', label: 'Unknown size', cls: 'unknown' };
  }
  const value = parseFloat(match[1]);
  const unit = match[2];
  const billions = unit === 't' ? value * 1000 : value;

  if (billions <= 25) return { key: 'light', label: 'Light', cls: 'light' };
  if (billions <= 150) return { key: 'medium', label: 'Medium', cls: 'medium' };
  if (billions <= 500) return { key: 'heavy', label: 'Heavy', cls: 'heavy' };
  return { key: 'xheavy', label: 'Extra Heavy', cls: 'xheavy' };
}
