// Service worker: faz os pedidos HTTP ao servidor local (sem problemas de CORS) e gere os
// downloads. Como o popup fecha sempre que se clica fora dele, é aqui que se acompanha cada
// job até ao fim e se entrega o ficheiro ao gestor de downloads do browser.
// Se mudares a porta, altera aqui, no manifest.json (host_permissions) e em YTDLP_PORT.
const SERVER = "http://127.0.0.1:9614";
const INFO_TTL = 30 * 60 * 1000; // reaproveita a info de um vídeo durante 30 min

const jobs = {}; // estado dos downloads (espelhado em chrome.storage.session para o popup)
const tracking = new Set();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, options) {
  let res;
  try {
    res = await fetch(SERVER + path, options);
  } catch {
    throw new Error("SERVER_OFFLINE");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Server error (${res.status})`);
  return data;
}

// ---------------------------------------------------------------- estado/badge
function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) chrome.action.setBadgeBackgroundColor({ color });
}

function updateBadge() {
  const list = Object.values(jobs);
  const running = list
    .filter((j) => j.status === "running")
    .sort((a, b) => b.created - a.created)[0];
  if (running) setBadge(`${Math.round(running.percent || 0)}%`, "#065fd4");
  else if (list.some((j) => j.status === "error" && !j.seen)) setBadge("!", "#cc0000");
  else setBadge("");
}

// Cada gravação é uma chamada à API de extensões: também mantém o service worker vivo.
async function persist() {
  await chrome.storage.session.set({ jobs });
  updateBadge();
}

// ------------------------------------------------------------- acompanhar jobs
async function track(id) {
  if (tracking.has(id) || !jobs[id]) return;
  tracking.add(id);
  const job = jobs[id];
  try {
    for (;;) {
      await sleep(700);
      const s = await api(`/status/${encodeURIComponent(id)}`);
      if (s.status === "running") {
        Object.assign(job, { percent: s.percent, message: s.message, updated: Date.now() });
        await persist();
        continue;
      }
      if (s.status === "error") throw new Error(s.message);
      await chrome.downloads.download({
        url: `${SERVER}/file/${encodeURIComponent(id)}`,
        saveAs: false,
      });
      Object.assign(job, {
        status: "done",
        percent: 100,
        file: s.file,
        message: `Saved to your downloads: ${s.file}`,
        updated: Date.now(),
      });
      break;
    }
  } catch (err) {
    Object.assign(job, { status: "error", message: err.message, updated: Date.now() });
  } finally {
    tracking.delete(id);
  }
  await persist();
}

// Se o service worker for reiniciado a meio de um download, retoma o acompanhamento.
const ready = chrome.storage.session
  .get("jobs")
  .then(({ jobs: saved }) => {
    Object.assign(jobs, saved || {});
    for (const j of Object.values(jobs)) if (j.status === "running") track(j.id);
    updateBadge();
  })
  .catch(() => {});

// ------------------------------------------------------------------- mensagens
const handlers = {
  info: async (m) => {
    if (!m.refresh) {
      const { lastInfo } = await chrome.storage.session.get("lastInfo");
      if (lastInfo && lastInfo.url === m.url && Date.now() - lastInfo.ts < INFO_TTL) {
        return lastInfo.data;
      }
    }
    const data = await api(`/info?url=${encodeURIComponent(m.url)}`);
    await chrome.storage.session.set({ lastInfo: { url: m.url, data, ts: Date.now() } });
    return data;
  },

  download: async (m) => {
    await ready;
    const { id } = await api("/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(m.payload),
    });
    const now = Date.now();
    for (const [key, j] of Object.entries(jobs)) {
      if (j.status !== "running" && now - j.updated > 3600 * 1000) delete jobs[key];
    }
    jobs[id] = {
      id,
      url: m.payload.url,
      kind: m.payload.type,
      status: "running",
      percent: 0,
      message: "Starting…",
      created: now,
      updated: now,
    };
    await persist();
    track(id);
    return { id };
  },

  // O popup foi aberto: o aviso de erro no ícone já foi visto.
  ack: async () => {
    await ready;
    for (const j of Object.values(jobs)) if (j.status === "error") j.seen = true;
    await persist();
    return {};
  },
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const handler = handlers[msg && msg.type];
  if (!handler) return false;
  handler(msg).then(
    (data) => sendResponse({ ok: true, data }),
    (err) => sendResponse({ ok: false, error: err.message })
  );
  return true; // resposta assíncrona
});
