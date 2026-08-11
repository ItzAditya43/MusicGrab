import { THEMES, getTheme, getSavedThemeId, setActiveTheme, applyTheme, initTheme } from "./themes.js";
import { ANIMATIONS, animationManager } from "./bg-animations.js";

(() => {
  "use strict";

  const state = {
    view: "home",
    library: [],
    searchResults: [],
    jobs: [],
    queue: [],      // active playback queue (array of tracks)
    queueIndex: -1,
    jobPollTimer: null,
    lyrics: null,       // { found, plain, synced } for the current track
    lyricsTrackId: null,
    lyricsOpen: false,
  };

  const el = (id) => document.getElementById(id);
  const audio = el("audio");

  // The Android build has no local HTTP backend at all — it downloads
  // on-device via a Tauri plugin (musicgrab-ytdl, backed by
  // youtubedl-android) instead of the FastAPI server the desktop app
  // spawns as a sidecar. window.__TAURI__ is only injected on that build
  // (withGlobalTauri is enabled solely in tauri.android.conf.json), so its
  // presence reliably distinguishes "running as the Android app" from
  // "running in a normal browser or the desktop app's window".
  const IS_ANDROID_APP = typeof window !== "undefined" && !!window.__TAURI__;
  const invoke = (cmd, payload) =>
    IS_ANDROID_APP ? window.__TAURI__.core.invoke(cmd, { payload }) : Promise.reject(new Error("not running as the Android app"));

  const ICONS = {
    play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
    pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>',
    download: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4v11" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M5 19h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  };

  // ---------------- API helpers ----------------

  async function api(path, opts) {
    const res = await fetch(path, opts);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status} ${res.statusText}`);
    }
    return res.status === 204 ? null : res.json();
  }

  // ---------------- Views ----------------

  const VIEW_TITLES = {
    home: "Home",
    search: "Search",
    library: "Your Library",
    downloads: "Downloads",
    settings: "Settings",
  };

  function showView(view) {
    state.view = view;
    document.querySelectorAll(".view").forEach((v) => (v.hidden = true));
    el(`view-${view}`).hidden = false;
    el("view-title").textContent = VIEW_TITLES[view];
    document.querySelectorAll(".nav-link").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === view);
    });
    if (view === "library") loadLibrary();
    if (view === "downloads") renderJobs();
    if (view === "settings") {
      loadSettings();
      initAppearanceSettings();
    }
  }

  document.querySelectorAll(".nav-link").forEach((btn) => {
    btn.addEventListener("click", () => {
      location.hash = btn.dataset.view;
      showView(btn.dataset.view);
    });
  });

  // ---------------- Track list rendering ----------------

  function formatDuration(seconds) {
    seconds = Math.floor(seconds || 0);
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function trackRow(track, { queue, index, showDownload }) {
    const row = document.createElement("div");
    row.className = "track-row";
    if (state.queue[state.queueIndex] && state.queue[state.queueIndex].id === track.id) {
      row.classList.add("playing");
    }

    const playBtn = document.createElement("button");
    playBtn.className = "track-play";
    playBtn.innerHTML = ICONS.play;
    if (track.has_audio && track.id && !IS_ANDROID_APP) {
      playBtn.style.backgroundImage = `url(/api/artwork/${track.id})`;
    }
    playBtn.addEventListener("click", () => {
      if (!track.has_audio) return;
      playQueue(queue, index);
    });
    if (!track.has_audio) {
      playBtn.disabled = true;
      playBtn.style.opacity = 0.4;
    }

    const info = document.createElement("div");
    info.className = "track-info";
    const title = document.createElement("div");
    title.className = "track-title";
    title.textContent = track.title || "Unknown";
    const artist = document.createElement("div");
    artist.className = "track-artist";
    artist.textContent = track.artist || "Unknown artist";
    info.append(title, artist);

    const duration = document.createElement("div");
    duration.className = "track-duration";
    duration.textContent = formatDuration(track.duration);

    row.append(playBtn, info, duration);

    if (showDownload) {
      const action = document.createElement("button");
      action.className = "track-action";
      action.innerHTML = `${ICONS.download}<span>Download</span>`;
      action.addEventListener("click", () => startDownload(track.source_url));
      row.append(action);
    } else {
      row.append(document.createElement("span"));
    }

    return row;
  }

  function renderTrackList(container, tracks, opts = {}) {
    container.innerHTML = "";
    if (!tracks.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = opts.emptyText || "Nothing here yet.";
      container.appendChild(empty);
      return;
    }
    tracks.forEach((t, i) => {
      container.appendChild(trackRow(t, { queue: tracks, index: i, showDownload: opts.showDownload }));
    });
  }

  // ---------------- Library ----------------

  async function loadLibrary() {
    if (IS_ANDROID_APP) {
      const res = await invoke("plugin:musicgrab-ytdl|list_downloads");
      state.library = res.files.map((f) => ({
        id: f.path,
        title: f.name,
        artist: "",
        duration: 0,
        has_audio: true,
        source_url: f.path,
      }));
    } else {
      const data = await api("/api/library");
      state.library = data.tracks;
    }
    renderTrackList(el("library-list"), state.library, { emptyText: "No downloaded tracks yet." });
    loadLibStats();
  }

  async function loadLibStats() {
    if (IS_ANDROID_APP) {
      el("lib-stats").textContent = `Library: ${state.library.length} tracks`;
      return;
    }
    const stats = await api("/api/library/stats");
    el("lib-stats").textContent = `Library: ${stats.total_tracks} tracks`;
  }

  el("scan-btn").addEventListener("click", async () => {
    el("scan-btn").disabled = true;
    el("scan-btn").textContent = "Scanning…";
    try {
      if (!IS_ANDROID_APP) await api("/api/library/scan", { method: "POST" });
      await loadLibrary();
    } finally {
      el("scan-btn").disabled = false;
      el("scan-btn").textContent = "Rescan library";
    }
  });

  // ---------------- Search ----------------

  el("search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = el("search-input").value.trim();
    if (!q) return;
    el("search-results").innerHTML = "<p class=\"muted\">Searching…</p>";
    try {
      if (IS_ANDROID_APP) {
        const res = await invoke("plugin:musicgrab-ytdl|search", { query: q, limit: 15 });
        state.searchResults = res.results.map((r) => ({
          id: r.webpageUrl,
          title: r.title,
          artist: r.uploader || "YouTube",
          duration: r.duration || 0,
          source_url: r.webpageUrl,
          has_audio: false,
        }));
      } else {
        const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
        state.searchResults = data.results;
      }
      renderTrackList(el("search-results"), state.searchResults, {
        emptyText: "No results.",
        showDownload: true,
      });
    } catch (err) {
      el("search-results").innerHTML = `<p class="muted">${err.message || err}</p>`;
    }
  });

  // ---------------- Downloads ----------------

  el("add-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = el("add-url");
    const url = input.value.trim();
    if (!url) return;
    input.value = "";
    startDownload(url);
  });

  async function startDownload(url) {
    if (IS_ANDROID_APP) {
      // No job queue on Android — download() blocks until yt-dlp finishes
      // (it runs on a background thread on the Kotlin side, so this await
      // doesn't block the UI thread there, just this JS call).
      showView("library");
      const prevText = el("view-title").textContent;
      el("view-title").textContent = "Downloading…";
      try {
        await invoke("plugin:musicgrab-ytdl|download", { url });
        await loadLibrary();
      } catch (err) {
        alert(err.message || String(err));
      } finally {
        el("view-title").textContent = prevText;
      }
      return;
    }

    showView("downloads");
    try {
      await api("/api/downloads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
    } catch (err) {
      alert(err.message);
    }
    pollJobs();
  }

  function renderJobs() {
    const container = el("job-list");
    container.innerHTML = "";
    if (!state.jobs.length) {
      container.innerHTML = '<p class="muted">No downloads yet. Paste a link on the left to get started.</p>';
      return;
    }
    state.jobs.forEach((job) => {
      const card = document.createElement("div");
      card.className = "job-card";

      const url = document.createElement("div");
      url.className = "job-url";
      url.textContent = job.url;

      const msg = document.createElement("div");
      msg.className = "job-message";
      msg.textContent = job.message || "";

      const bar = document.createElement("div");
      bar.className = "job-bar";
      const fill = document.createElement("div");
      fill.className = "job-bar-fill";
      const pct = job.total ? Math.round((job.done / job.total) * 100) : job.status === "completed" ? 100 : 0;
      fill.style.width = `${pct}%`;
      bar.appendChild(fill);

      const status = document.createElement("span");
      status.className = `job-status ${job.status}`;
      status.textContent = job.status;

      card.append(url, msg, bar, status);
      container.appendChild(card);
    });
  }

  async function pollJobs() {
    try {
      state.jobs = await api("/api/downloads");
    } catch {
      return;
    }
    if (state.view === "downloads") renderJobs();

    const active = state.jobs.filter((j) => j.status === "queued" || j.status === "running");
    el("downloads-badge").hidden = active.length === 0;
    el("downloads-badge").textContent = active.length || "";

    const anyCompletedRecently = state.jobs.some((j) => j.status === "completed");
    if (anyCompletedRecently && state.view === "library") loadLibrary();

    clearTimeout(state.jobPollTimer);
    if (active.length > 0) {
      state.jobPollTimer = setTimeout(pollJobs, 1500);
    } else {
      // slow background poll in case user starts nothing else
      state.jobPollTimer = setTimeout(pollJobs, 8000);
      if (anyCompletedRecently) loadLibStats();
    }
  }

  // ---------------- Settings ----------------

  async function loadSettings() {
    // No config server on Android — audio format is fixed (mp3) in the
    // Kotlin plugin for now; General settings are a desktop/web-app-only
    // panel until that's wired up too.
    if (IS_ANDROID_APP) return;
    const cfg = await api("/api/config");
    el("s-format").value = cfg.audio_format;
    el("s-quality").value = cfg.audio_quality;
    el("s-metadata").checked = cfg.embed_metadata;
    el("s-artwork").checked = cfg.save_artwork;
  }

  el("settings-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (IS_ANDROID_APP) return;
    await api("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        audio_format: el("s-format").value,
        audio_quality: el("s-quality").value,
        embed_metadata: el("s-metadata").checked,
        save_artwork: el("s-artwork").checked,
        spotify_client_id: el("s-spotify-id").value || undefined,
        spotify_client_secret: el("s-spotify-secret").value || undefined,
      }),
    });
    const note = el("settings-saved");
    note.hidden = false;
    setTimeout(() => (note.hidden = true), 2000);
  });

  // ---------------- Settings tabs ----------------

  document.querySelectorAll(".settings-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".settings-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      el("settings-panel-general").hidden = tab.dataset.tab !== "general";
      el("settings-panel-appearance").hidden = tab.dataset.tab !== "appearance";
    });
  });

  // ---------------- Appearance: color themes ----------------

  function renderThemeGrid() {
    const grid = el("theme-grid");
    grid.innerHTML = "";
    const activeId = getSavedThemeId();
    THEMES.forEach((theme) => {
      const btn = document.createElement("button");
      btn.className = "theme-swatch" + (theme.id === activeId ? " active" : "");
      btn.dataset.themeId = theme.id;

      const colors = document.createElement("div");
      colors.className = "theme-swatch-colors";
      [theme.bg, theme.surface2, theme.accent, theme.accent2].forEach((c) => {
        const sw = document.createElement("span");
        sw.style.background = c;
        colors.appendChild(sw);
      });

      const name = document.createElement("div");
      name.className = "theme-swatch-name";
      name.textContent = theme.name;

      btn.append(colors, name);
      btn.addEventListener("mouseenter", () => previewTheme(theme));
      btn.addEventListener("mouseleave", () => previewTheme(getTheme(getSavedThemeId())));
      btn.addEventListener("click", () => {
        setActiveTheme(theme.id);
        animationManager.refreshForThemeChange();
        renderThemeGrid();
      });
      grid.appendChild(btn);
    });
  }

  function previewTheme(theme) {
    // Live-preview on hover without persisting; setActiveTheme() (on
    // click) is what actually saves the choice.
    applyTheme(theme);
  }

  // ---------------- Appearance: background animations ----------------

  function renderAnimationGrid() {
    const grid = el("animation-grid");
    grid.innerHTML = "";
    const activeId = animationManager.getSavedId();
    ANIMATIONS.forEach((anim) => {
      const btn = document.createElement("button");
      btn.className = "animation-swatch" + (anim.id === activeId ? " active" : "");
      btn.textContent = anim.name;
      btn.addEventListener("click", async () => {
        el("animations-enabled").checked = anim.id !== "none";
        animationManager.setEnabled(anim.id !== "none");
        await animationManager.setAnimation(anim.id);
        renderAnimationGrid();
      });
      grid.appendChild(btn);
    });
  }

  function renderIntensityButtons() {
    document.querySelectorAll("#intensity-buttons button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.level === animationManager.intensity);
      btn.addEventListener("click", () => {
        animationManager.setIntensity(btn.dataset.level);
        renderIntensityButtons();
      });
    });
  }

  el("animations-enabled").addEventListener("change", async (e) => {
    animationManager.setEnabled(e.target.checked);
    // Flipping this on with no animation ever picked would otherwise do
    // nothing visible — default to the first real option so "enable"
    // actually shows something instead of silently staying on "none".
    if (e.target.checked && animationManager.getSavedId() === "none") {
      await animationManager.setAnimation(ANIMATIONS[1].id);
    }
    renderAnimationGrid();
  });

  el("reset-appearance").addEventListener("click", () => {
    setActiveTheme("cyber-neon");
    animationManager.setEnabled(false);
    animationManager.setAnimation("none");
    el("animations-enabled").checked = false;
    renderThemeGrid();
    renderAnimationGrid();
    renderIntensityButtons();
  });

  function initAppearanceSettings() {
    el("animations-enabled").checked = animationManager.enabled && animationManager.getSavedId() !== "none";
    renderThemeGrid();
    renderAnimationGrid();
    renderIntensityButtons();
  }

  // ---------------- Player ----------------

  function playQueue(queue, index) {
    state.queue = queue;
    state.queueIndex = index;
    playCurrent();
  }

  function playCurrent() {
    const track = state.queue[state.queueIndex];
    if (!track) return;
    if (IS_ANDROID_APP) {
      // track.id is a real on-device file path (see loadLibrary); Tauri's
      // asset protocol is what's allowed to serve arbitrary local files
      // into the webview, not a plain file:// URL.
      audio.src = window.__TAURI__.core.convertFileSrc(track.id);
      el("player-art").src = "";
    } else {
      audio.src = `/api/stream/${track.id}`;
      el("player-art").src = `/api/artwork/${track.id}`;
      el("player-art").onerror = () => (el("player-art").src = "");
    }
    audio.play().catch(() => {});
    el("player-title").textContent = track.title || "Unknown";
    el("player-artist").textContent = track.artist || "Unknown artist";
    refreshPlayingHighlight();
    loadLyrics(track);
  }

  // ---------------- Lyrics ----------------

  async function loadLyrics(track) {
    state.lyrics = null;
    state.lyricsTrackId = track.id;
    if (state.lyricsOpen) renderLyrics();

    // No backend to ask on Android — lyrics aren't available in the
    // standalone build yet.
    if (IS_ANDROID_APP) {
      state.lyrics = { found: false, plain: null, synced: null };
      if (state.lyricsOpen) renderLyrics();
      return;
    }

    try {
      const data = await api(`/api/lyrics/${track.id}`);
      if (state.lyricsTrackId !== track.id) return; // track changed while fetching
      state.lyrics = data;
    } catch {
      if (state.lyricsTrackId !== track.id) return;
      state.lyrics = { found: false, plain: null, synced: null };
    }
    if (state.lyricsOpen) renderLyrics();
  }

  function renderLyrics() {
    const body = el("lyrics-body");
    body.innerHTML = "";

    if (!state.queue[state.queueIndex]) {
      body.innerHTML = '<p class="muted">Play a track to see its lyrics.</p>';
      return;
    }
    if (state.lyrics === null) {
      body.innerHTML = '<p class="muted">Loading lyrics…</p>';
      return;
    }
    if (!state.lyrics.found) {
      body.innerHTML = '<p class="muted">No lyrics found for this track.</p>';
      return;
    }
    if (state.lyrics.synced) {
      const list = document.createElement("div");
      list.className = "lyrics-synced";
      state.lyrics.synced.forEach((line, i) => {
        const p = document.createElement("p");
        p.className = "lyrics-line";
        p.dataset.time = line.time;
        p.dataset.index = i;
        p.textContent = line.text;
        list.appendChild(p);
      });
      body.appendChild(list);
    } else {
      const pre = document.createElement("pre");
      pre.className = "lyrics-plain";
      pre.textContent = state.lyrics.plain;
      body.appendChild(pre);
    }
  }

  function updateLyricsHighlight() {
    if (!state.lyricsOpen || !state.lyrics || !state.lyrics.synced) return;
    const lines = el("lyrics-body").querySelectorAll(".lyrics-line");
    if (!lines.length) return;
    let activeIndex = -1;
    lines.forEach((line, i) => {
      if (parseFloat(line.dataset.time) <= audio.currentTime) activeIndex = i;
    });
    lines.forEach((line, i) => line.classList.toggle("active", i === activeIndex));
    if (activeIndex >= 0) {
      lines[activeIndex].scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  el("lyrics-btn").addEventListener("click", () => {
    state.lyricsOpen = !state.lyricsOpen;
    el("lyrics-panel").hidden = !state.lyricsOpen;
    el("lyrics-btn").classList.toggle("active", state.lyricsOpen);
    if (state.lyricsOpen) renderLyrics();
  });

  el("lyrics-close").addEventListener("click", () => {
    state.lyricsOpen = false;
    el("lyrics-panel").hidden = true;
    el("lyrics-btn").classList.remove("active");
  });

  el("lyrics-body").addEventListener("click", (e) => {
    const line = e.target.closest(".lyrics-line");
    if (!line || !audio.duration) return;
    audio.currentTime = parseFloat(line.dataset.time);
  });

  function refreshPlayingHighlight() {
    [el("library-list"), el("search-results")].forEach((container) => {
      container.querySelectorAll(".track-row").forEach((r) => r.classList.remove("playing"));
    });
  }

  el("play-btn").addEventListener("click", () => {
    if (!audio.src) return;
    if (audio.paused) {
      audio.play();
    } else {
      audio.pause();
    }
  });

  audio.addEventListener("play", () => (el("play-icon").outerHTML = ICONS.pause.replace("<svg", '<svg id="play-icon"')));
  audio.addEventListener("pause", () => (el("play-icon").outerHTML = ICONS.play.replace("<svg", '<svg id="play-icon"')));

  el("next-btn").addEventListener("click", () => {
    if (state.queueIndex + 1 < state.queue.length) {
      state.queueIndex += 1;
      playCurrent();
    }
  });

  el("prev-btn").addEventListener("click", () => {
    if (state.queueIndex > 0) {
      state.queueIndex -= 1;
      playCurrent();
    }
  });

  audio.addEventListener("ended", () => el("next-btn").click());

  audio.addEventListener("timeupdate", () => {
    if (!audio.duration) return;
    el("seek").value = (audio.currentTime / audio.duration) * 100;
    el("time-current").textContent = formatDuration(audio.currentTime);
    el("time-total").textContent = formatDuration(audio.duration);
    updateLyricsHighlight();
  });

  el("seek").addEventListener("input", () => {
    if (!audio.duration) return;
    audio.currentTime = (el("seek").value / 100) * audio.duration;
  });

  el("volume").addEventListener("input", () => {
    audio.volume = parseFloat(el("volume").value);
  });

  // ---------------- Init ----------------

  initTheme();
  animationManager.init();

  const initialView = (location.hash || "").replace("#", "");
  showView(VIEW_TITLES[initialView] ? initialView : "home");

  if (IS_ANDROID_APP) {
    // No job queue / no service worker registration path on Android —
    // pollJobs() and sw.js registration are web-app/desktop concerns.
    loadLibrary();
    document.querySelector('.nav-link[data-view="downloads"]')?.remove();
  } else {
    loadLibStats();
    pollJobs();
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }
})();
