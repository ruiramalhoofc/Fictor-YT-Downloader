// Popup da extensão (abre ao clicar no ícone): mesmas abas e opções do menu anterior.
// O progresso vem do service worker via chrome.storage.session, por isso os downloads
// continuam mesmo que o popup seja fechado.
(() => {
  "use strict";

  const OFFLINE = "SERVER_OFFLINE";
  const RECENT_MS = 5 * 60 * 1000; // quanto tempo um resultado antigo continua visível
  const $ = (sel) => document.querySelector(sel);
  const state = { url: null, info: null, job: null, starting: false, noSubs: false, audioLossy: {} };

  const send = (msg) =>
    new Promise((resolve) => {
      const dead = { ok: false, error: "The extension background is not responding. Reload the extension." };
      try {
        chrome.runtime.sendMessage(msg, (res) =>
          resolve(chrome.runtime.lastError || !res ? dead : res)
        );
      } catch {
        resolve(dead);
      }
    });

  const friendly = (e) =>
    e === OFFLINE
      ? "Can't reach the local server. Start the yt-dlp server (see README), then press Retry."
      : e;

  // Converte o URL do separador (watch, shorts, youtu.be) no URL canónico do vídeo.
  function videoUrl(raw) {
    try {
      const u = new URL(raw);
      let id = null;
      if (u.hostname === "youtu.be") id = u.pathname.slice(1);
      else if (u.hostname === "youtube.com" || u.hostname.endsWith(".youtube.com")) {
        if (u.pathname === "/watch") id = u.searchParams.get("v");
        else if (u.pathname.startsWith("/shorts/")) id = u.pathname.split("/")[2];
      }
      return id ? `https://www.youtube.com/watch?v=${id}` : null;
    } catch {
      return null;
    }
  }

  // ------------------------------------------------------------------- UI
  function selectTab(name) {
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
    document.querySelectorAll(".pane").forEach((p) => (p.hidden = p.dataset.pane !== name));
  }

  function showMsg(text, err = false) {
    const m = $(".msg");
    m.hidden = !text;
    m.textContent = text || "";
    m.classList.toggle("err", err);
    $(".retry").hidden = true;
  }

  function showProgress(pct, text) {
    $(".bar").hidden = false;
    $(".bar i").style.width = `${pct}%`;
    showMsg(text);
  }

  const isRunning = () => state.job && state.job.status === "running";

  function refreshButtons() {
    const busy = state.starting || isRunning();
    document.querySelectorAll("[data-dl]").forEach((b) => {
      b.disabled = busy || !state.info || (b.dataset.dl === "subtitles" && state.noSubs);
    });
  }

  function setOptions(select, items) {
    select.replaceChildren(...items.map((i) => new Option(i.label, i.value)));
  }

  // A qualidade (bitrate) só se aplica a formatos de áudio com perdas.
  function syncAudio() {
    $("#a-q").disabled = !state.audioLossy[$("#a-f").value];
  }

  function fillInfo(info) {
    $(".title").textContent = info.title || "Download";
    $(".thumb").src = info.thumbnail || "";
    setOptions($("#v-q"), info.videos);
    setOptions($("#v-f"), info.video_formats);
    setOptions($("#a-f"), info.audio_formats);
    setOptions($("#a-q"), info.audio_qualities);
    state.audioLossy = Object.fromEntries(info.audio_formats.map((f) => [f.value, f.lossy]));
    syncAudio();
    setOptions($("#s-f"), info.sub_formats.map((f) => ({ value: f, label: f.toUpperCase() })));

    const sel = $("#s-l");
    sel.replaceChildren();
    const groups = [
      ["Subtitles", "manual"],
      ["Auto-generated", "auto"],
      ["Auto-translated (often blocked by YouTube)", "translated"],
    ];
    for (const [label, track] of groups) {
      const items = info.subtitles.filter((s) => s.track === track);
      if (!items.length) continue;
      const group = document.createElement("optgroup");
      group.label = label;
      group.append(...items.map((s) => new Option(`${s.name} (${s.code})`, `${track}:${s.code}`)));
      sel.append(group);
    }
    state.noSubs = !info.subtitles.length;
    if (state.noSubs) sel.append(new Option("No subtitles available", ""));
    sel.disabled = $("#s-f").disabled = state.noSubs;
  }

  // Mostra o estado do download mais recente deste vídeo (vem do service worker).
  function renderJob() {
    const job = state.job;
    if (job && (job.status === "running" || Date.now() - job.updated < RECENT_MS)) {
      if (job.status === "error") {
        $(".bar").hidden = true;
        showMsg(friendly(job.message), true);
      } else {
        showProgress(job.percent || 0, job.message);
      }
    }
    refreshButtons();
  }

  const pickJob = (jobs) =>
    Object.values(jobs || {})
      .filter((j) => j.url === state.url)
      .sort((a, b) => b.created - a.created)[0] || null;

  async function loadInfo(refresh = false) {
    state.info = null;
    refreshButtons();
    showMsg("Loading video info…");
    const r = await send({ type: "info", url: state.url, refresh });
    if (!r.ok) {
      showMsg(friendly(r.error), true);
      $(".retry").hidden = false;
      return;
    }
    state.info = r.data;
    fillInfo(r.data);
    showMsg(r.data.notice || "");
    renderJob();
  }

  async function startDownload(kind) {
    if (!state.info || state.starting || isRunning()) return;
    const payload = { url: state.info.url, type: kind };
    if (kind === "video") {
      payload.quality = $("#v-q").value;
      payload.format = $("#v-f").value;
    }
    if (kind === "audio") {
      payload.format = $("#a-f").value;
      payload.quality = $("#a-q").value;
    }
    if (kind === "subtitles") {
      const [track, ...code] = $("#s-l").value.split(":");
      payload.track = track;
      payload.lang = code.join(":");
      payload.format = $("#s-f").value;
    }
    state.starting = true;
    refreshButtons();
    showProgress(0, "Starting…");
    const r = await send({ type: "download", payload });
    state.starting = false;
    if (!r.ok) {
      $(".bar").hidden = true;
      showMsg(friendly(r.error), true);
    }
    refreshButtons(); // o progresso seguinte chega por chrome.storage.onChanged
  }

  // ----------------------------------------------------------------- arranque
  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => selectTab(t.dataset.tab))
  );
  document.querySelectorAll("[data-dl]").forEach((b) =>
    b.addEventListener("click", () => startDownload(b.dataset.dl))
  );
  $(".retry").addEventListener("click", () => loadInfo(true));
  $("#a-f").addEventListener("change", syncAudio);

  async function init() {
    send({ type: "ack" });
    let tab;
    try {
      [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    } catch {
      /* sem acesso ao separador */
    }
    state.url = videoUrl(tab && tab.url);
    if (!state.url) {
      $("#empty").hidden = false;
      return;
    }
    $("#app").hidden = false;

    const { jobs } = await chrome.storage.session.get("jobs");
    state.job = pickJob(jobs);
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "session" || !changes.jobs) return;
      state.job = pickJob(changes.jobs.newValue);
      renderJob();
    });
    loadInfo();
  }

  init();
})();
