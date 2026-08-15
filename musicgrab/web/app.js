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
    nowPlayingOpen: false,
    nowPlayingLyricsOpen: false,
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
  // window.__TAURI__ exists on BOTH the Android app and the desktop Tauri
  // shell (this build has withGlobalTauri enabled) — checking for it alone
  // misidentifies desktop as Android, sending it down code paths that call
  // an Android-only plugin command and hang forever (invoke() never
  // resolves or rejects when the target plugin isn't registered). The
  // user agent reliably distinguishes them: only the Android WebView
  // reports "Android".
  const IS_ANDROID_APP =
    typeof window !== "undefined" && !!window.__TAURI__ && /Android/i.test(navigator.userAgent || "");
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
    discover: "Discover",
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
    if (view === "discover") loadDiscover();
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
      state.library = res.files.map((f) => {
        // Downloaded files are named "Artist - Title" (see the Kotlin
        // plugin's download() nameTemplate) — split it back apart so the
        // library list isn't just a wall of blank-artist rows.
        const sep = f.name.indexOf(" - ");
        const artist = sep >= 0 ? f.name.slice(0, sep) : "";
        const title = sep >= 0 ? f.name.slice(sep + 3) : f.name;
        return {
          id: f.path,
          title,
          artist,
          duration: 0,
          has_audio: true,
          source_url: f.path,
          thumbnail: f.thumbnail || "",
        };
      });
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

  // ---------------- Discover ----------------

  async function loadDiscover() {
    if (IS_ANDROID_APP) {
      // No local backend on Android to ask for Spotify-backed recommendations.
      el("discover-recommended").innerHTML = '<p class="muted">Discover isn\'t available in the Android app yet.</p>';
      el("discover-based-on").textContent = "";
      el("followed-artists-list").innerHTML = "";
      return;
    }
    el("discover-recommended").innerHTML = '<p class="muted">Loading recommendations…</p>';
    try {
      const data = await api("/api/discover/recommended");
      renderTrackList(el("discover-recommended"), data.tracks, {
        emptyText: "Download a few tracks first, then recommendations will show up here.",
        showDownload: true,
      });
      el("discover-based-on").textContent = data.based_on.length
        ? `Based on: ${data.based_on.join(", ")}`
        : "";
    } catch (err) {
      el("discover-recommended").innerHTML = `<p class="muted">${err.message || err}</p>`;
    }
    loadFollowedArtists();
  }

  async function loadFollowedArtists() {
    const container = el("followed-artists-list");
    container.innerHTML = '<p class="muted">Loading…</p>';
    try {
      const data = await api("/api/artists/followed");
      renderFollowedArtists(container, data.artists);
    } catch (err) {
      container.innerHTML = `<p class="muted">${err.message || err}</p>`;
    }
  }

  function renderFollowedArtists(container, artists) {
    container.innerHTML = "";
    if (!artists.length) {
      container.innerHTML = '<p class="muted">Not following anyone yet — search an artist name above.</p>';
      return;
    }
    artists.forEach((artist) => {
      const card = document.createElement("div");
      card.className = "artist-card";

      const art = document.createElement("img");
      art.className = "artist-card-art";
      art.src = artist.thumbnail_url || "";
      art.alt = "";

      const info = document.createElement("div");
      info.className = "artist-card-info";
      const name = document.createElement("div");
      name.className = "artist-card-name";
      name.textContent = artist.name;
      const releases = document.createElement("div");
      releases.className = "artist-card-releases";
      releases.textContent = artist.latest_releases.length
        ? `Latest: ${artist.latest_releases.map((r) => r.title).join(" · ")}`
        : "No releases found";
      info.append(name, releases);

      const unfollowBtn = document.createElement("button");
      unfollowBtn.className = "btn-secondary artist-card-unfollow";
      unfollowBtn.textContent = "Unfollow";
      unfollowBtn.addEventListener("click", async () => {
        await api(`/api/artists/${artist.id}/follow`, { method: "DELETE" });
        loadFollowedArtists();
      });

      card.append(art, info, unfollowBtn);
      container.appendChild(card);
    });
  }

  el("follow-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = el("follow-input");
    const query = input.value.trim();
    if (!query) return;
    input.value = "";
    try {
      await api("/api/artists/follow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      loadFollowedArtists();
    } catch (err) {
      alert(err.message || String(err));
    }
  });

  // ---------------- Downloads ----------------

  function wireAddForm(formId, inputId) {
    el(formId).addEventListener("submit", (e) => {
      e.preventDefault();
      const input = el(inputId);
      const url = input.value.trim();
      if (!url) return;
      input.value = "";
      startDownload(url);
    });
  }
  wireAddForm("add-form", "add-url");
  // Narrow-screen (phone) layout hides the sidebar's add-form entirely —
  // see the bottom-tab-bar rules in app.css — so there's a second,
  // separately-visible paste-a-link form at the top of the main view.
  wireAddForm("mobile-add-form", "mobile-add-url");

  async function startDownload(url) {
    if (IS_ANDROID_APP) {
      // No job queue on Android — download() blocks until yt-dlp finishes
      // (it runs on a background thread on the Kotlin side, so this await
      // doesn't block the UI thread there, just this JS call). Show a
      // persistent banner rather than just a view-title flicker, which
      // was easy to miss and left the download with basically no visible
      // in-progress feedback.
      showView("library");
      const banner = el("android-download-banner");
      const bannerText = el("android-download-banner-text");
      bannerText.textContent = `Downloading: ${url}`;
      banner.hidden = false;
      try {
        await invoke("plugin:musicgrab-ytdl|download", { url });
        await loadLibrary();
      } catch (err) {
        alert(err.message || String(err));
      } finally {
        banner.hidden = true;
      }
      return;
    }

    // Playlists/albums get a pick-which-tracks step first; a bare single
    // track just starts immediately, same as before. Preview failures
    // (unrecognized URL, network hiccup) fall through to the old
    // straight-to-download behavior instead of blocking the user.
    try {
      const preview = await api("/api/downloads/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      if (preview.tracks.length > 1) {
        openTrackSelectModal(url, preview);
        return;
      }
    } catch {
      // fall through to a direct download attempt below
    }
    await launchDownload(url);
  }

  async function launchDownload(url, selectedIndices) {
    showView("downloads");
    try {
      await api("/api/downloads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, selected_indices: selectedIndices ?? null }),
      });
    } catch (err) {
      alert(err.message);
    }
    pollJobs();
  }

  // ---------------- Track selection modal ----------------

  function openTrackSelectModal(url, preview) {
    el("track-select-title").textContent = preview.title || "Select tracks";
    const list = el("track-select-list");
    list.innerHTML = "";
    preview.tracks.forEach((t) => {
      const row = document.createElement("label");
      row.className = "track-select-row";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.index = t.index;
      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "track-select-row-title";
      title.textContent = t.title || "Unknown";
      const artist = document.createElement("div");
      artist.className = "track-select-row-artist";
      artist.textContent = t.artist || "";
      info.append(title, artist);
      row.append(checkbox, info);
      checkbox.addEventListener("change", updateTrackSelectCount);
      list.appendChild(row);
    });
    updateTrackSelectCount();
    el("track-select-overlay").hidden = false;

    const confirmBtn = el("track-select-confirm");
    const onConfirm = () => {
      const selected = Array.from(list.querySelectorAll("input:checked")).map((c) => Number(c.dataset.index));
      closeTrackSelectModal();
      if (selected.length) launchDownload(url, selected);
    };
    confirmBtn.onclick = onConfirm;
  }

  function updateTrackSelectCount() {
    const list = el("track-select-list");
    const total = list.querySelectorAll("input").length;
    const checked = list.querySelectorAll("input:checked").length;
    el("track-select-count").textContent = `${checked}/${total} selected`;
  }

  function closeTrackSelectModal() {
    el("track-select-overlay").hidden = true;
  }

  el("track-select-all").addEventListener("click", () => {
    el("track-select-list").querySelectorAll("input").forEach((c) => (c.checked = true));
    updateTrackSelectCount();
  });
  el("track-select-none").addEventListener("click", () => {
    el("track-select-list").querySelectorAll("input").forEach((c) => (c.checked = false));
    updateTrackSelectCount();
  });
  el("track-select-cancel").addEventListener("click", closeTrackSelectModal);
  el("track-select-close").addEventListener("click", closeTrackSelectModal);
  el("track-select-overlay").addEventListener("click", (e) => {
    if (e.target === el("track-select-overlay")) closeTrackSelectModal();
  });

  const STATUS_ICON = {
    queued: "&#9675;",   // hollow circle
    active: "&#9679;",   // filled circle (pulses via CSS)
    done: "&#10003;",    // check
    skipped: "&#8722;",  // minus
    failed: "&#10005;",  // x
  };

  // Job track lists are rebuilt fully on first render, then patched
  // in-place on every subsequent poll (just swapping each row's status
  // class/icon) instead of re-rendering — a 700+ track list rebuilt from
  // scratch every 1.5s poll would be wasteful and cause visible flicker.
  const jobTrackRows = new Map(); // jobId -> HTMLElement[]

  function renderJobs() {
    const container = el("job-list");
    if (!state.jobs.length) {
      container.innerHTML = '<p class="muted">No downloads yet. Paste a link on the left to get started.</p>';
      jobTrackRows.clear();
      return;
    }

    const placeholder = container.querySelector(":scope > p.muted");
    if (placeholder) placeholder.remove();

    const seenJobIds = new Set(state.jobs.map((j) => j.id));
    for (const jobId of jobTrackRows.keys()) {
      if (!seenJobIds.has(jobId)) jobTrackRows.delete(jobId);
    }

    state.jobs.forEach((job) => {
      let card = container.querySelector(`[data-job-id="${job.id}"]`);
      const isNew = !card;
      if (isNew) {
        card = document.createElement("div");
        card.className = "job-card";
        card.dataset.jobId = job.id;
        container.appendChild(card);
      }

      const pct = job.total ? Math.round((job.done / job.total) * 100) : job.status === "completed" ? 100 : 0;
      const tracks = job.track_status || [];
      const counts = tracks.reduce(
        (acc, t) => ((acc[t.status] = (acc[t.status] || 0) + 1), acc),
        { queued: 0, active: 0, done: 0, skipped: 0, failed: 0 }
      );

      if (isNew) {
        card.innerHTML = `
          <div class="job-url"></div>
          <div class="job-message"></div>
          <div class="job-bar"><div class="job-bar-fill"></div></div>
          <div class="job-summary"></div>
          <div class="job-tracks"></div>
          <span class="job-status"></span>
          <div class="job-actions"></div>
        `;
      }

      card.querySelector(".job-url").textContent = job.url;
      card.querySelector(".job-message").textContent = job.message || "";
      card.querySelector(".job-bar-fill").style.width = `${pct}%`;
      const statusEl = card.querySelector(".job-status");
      const displayStatus = job.paused && job.status === "running" ? "paused" : job.status;
      statusEl.className = `job-status ${displayStatus}`;
      statusEl.textContent = displayStatus;

      const actionsEl = card.querySelector(".job-actions");
      const active = job.status === "queued" || job.status === "running";
      const retryable = counts.failed + counts.skipped;
      actionsEl.innerHTML = active
        ? `<button class="btn-secondary job-action-pause">${job.paused ? "Resume" : "Pause"}</button>
           <button class="btn-secondary job-action-delete">Cancel</button>`
        : `${retryable ? `<button class="btn-secondary job-action-retry">Retry ${retryable} failed/skipped</button>` : ""}
           <button class="btn-secondary job-action-delete">Delete</button>`;
      if (active) {
        actionsEl.querySelector(".job-action-pause").addEventListener("click", () => toggleJobPause(job));
      } else if (retryable) {
        actionsEl.querySelector(".job-action-retry").addEventListener("click", () => retryJob(job.id));
      }
      actionsEl.querySelector(".job-action-delete").addEventListener("click", () => deleteJob(job.id));

      card.querySelector(".job-summary").innerHTML = tracks.length
        ? `<span class="job-count done">${counts.done} done</span>` +
          (counts.active ? `<span class="job-count active">${counts.active} active</span>` : "") +
          (counts.failed ? `<span class="job-count failed">${counts.failed} failed</span>` : "") +
          (counts.skipped ? `<span class="job-count skipped">${counts.skipped} skipped</span>` : "") +
          `<span class="job-count queued">${counts.queued} queued</span>`
        : "";

      const tracksEl = card.querySelector(".job-tracks");
      let rows = jobTrackRows.get(job.id);
      if (!rows || rows.length !== tracks.length) {
        // Track count only changes at job start (once total is known), so
        // this full (re)build only happens once per job in practice.
        tracksEl.innerHTML = "";
        rows = tracks.map((t) => {
          const row = document.createElement("div");
          row.className = `job-track-row ${t.status}`;
          row.innerHTML = `<span class="job-track-icon"></span><span class="job-track-label"></span>`;
          tracksEl.appendChild(row);
          return row;
        });
        jobTrackRows.set(job.id, rows);
      }
      tracks.forEach((t, i) => {
        const row = rows[i];
        if (!row.dataset.status || row.dataset.status !== t.status) {
          row.className = `job-track-row ${t.status}`;
          row.dataset.status = t.status;
          row.querySelector(".job-track-icon").innerHTML = STATUS_ICON[t.status] || "";
        }
        const label = `${t.artist ? t.artist + " - " : ""}${t.title}`;
        const labelEl = row.querySelector(".job-track-label");
        if (labelEl.textContent !== label) labelEl.textContent = label;
      });
    });

    // Remove cards for jobs no longer in state.jobs (rare — jobs persist
    // for the process lifetime — but keeps things correct if that changes).
    container.querySelectorAll("[data-job-id]").forEach((card) => {
      if (!seenJobIds.has(card.dataset.jobId)) card.remove();
    });
  }

  async function toggleJobPause(job) {
    try {
      await api(`/api/downloads/${job.id}/${job.paused ? "resume" : "pause"}`, { method: "POST" });
    } catch (err) {
      alert(err.message || String(err));
      return;
    }
    pollJobs();
  }

  async function retryJob(jobId) {
    try {
      await api(`/api/downloads/${jobId}/retry`, { method: "POST" });
    } catch (err) {
      alert(err.message || String(err));
      return;
    }
    pollJobs();
  }

  async function deleteJob(jobId) {
    try {
      await api(`/api/downloads/${jobId}`, { method: "DELETE" });
    } catch (err) {
      alert(err.message || String(err));
      return;
    }
    jobTrackRows.delete(jobId);
    pollJobs();
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
    // panel until that's wired up too. Hide the tab entirely instead of
    // leaving a form whose "Save" button silently does nothing.
    if (IS_ANDROID_APP) {
      const generalTab = document.querySelector('.settings-tab[data-tab="general"]');
      if (generalTab) generalTab.hidden = true;
      const appearanceTab = document.querySelector('.settings-tab[data-tab="appearance"]');
      if (appearanceTab) appearanceTab.classList.add("active");
      el("settings-panel-general").hidden = true;
      el("settings-panel-appearance").hidden = false;
      return;
    }
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
      // Cover art is read straight from the file's own embedded tags
      // (see the Kotlin plugin's extractArtwork) as a data URI — there's
      // no HTTP artwork endpoint on Android, unlike desktop.
      el("player-art").src = track.thumbnail || "";
    } else {
      audio.src = `/api/stream/${track.id}`;
      el("player-art").src = `/api/artwork/${track.id}`;
      el("player-art").onerror = () => (el("player-art").src = "");
    }
    audio.play().catch(() => {});
    el("player-title").textContent = track.title || "Unknown";
    el("player-artist").textContent = track.artist || "Unknown artist";
    el("now-playing-art").src = el("player-art").src || "";
    el("now-playing-title").textContent = track.title || "Unknown";
    el("now-playing-artist").textContent = track.artist || "Unknown artist";
    refreshPlayingHighlight();
    loadLyrics(track);
  }

  // ---------------- Now Playing (Walkman-style full view) ----------------

  function openNowPlaying() {
    state.nowPlayingOpen = true;
    el("now-playing").hidden = false;
    if (state.nowPlayingLyricsOpen) renderLyrics();
    // Push a history entry so Android's hardware/gesture back button has
    // something to pop instead of falling through to the system default
    // (backgrounding or exiting the whole app) — the webview otherwise
    // has zero navigation history in this single-page app.
    history.pushState({ modal: "now-playing" }, "");
  }
  function closeNowPlaying(fromPopstate) {
    state.nowPlayingOpen = false;
    el("now-playing").hidden = true;
    // Only consume the history entry when the user closed via the X
    // button — a popstate-triggered close means it's already gone.
    if (!fromPopstate && history.state && history.state.modal === "now-playing") {
      history.back();
    }
  }
  el("player-art-wrap").addEventListener("click", openNowPlaying);
  el("now-playing-close").addEventListener("click", () => closeNowPlaying(false));
  window.addEventListener("popstate", () => {
    if (state.nowPlayingOpen) closeNowPlaying(true);
  });

  el("now-playing-play").addEventListener("click", () => el("play-btn").click());
  el("now-playing-prev").addEventListener("click", () => el("prev-btn").click());
  el("now-playing-next").addEventListener("click", () => el("next-btn").click());

  el("now-playing-seek").addEventListener("input", () => {
    if (!audio.duration) return;
    audio.currentTime = (el("now-playing-seek").value / 100) * audio.duration;
    setSeekFill("now-playing-seek", el("now-playing-seek").value);
  });

  el("now-playing-lyrics-toggle").addEventListener("click", () => {
    state.nowPlayingLyricsOpen = !state.nowPlayingLyricsOpen;
    el("now-playing-lyrics").hidden = !state.nowPlayingLyricsOpen;
    el("now-playing-lyrics-toggle").classList.toggle("active", state.nowPlayingLyricsOpen);
    if (state.nowPlayingLyricsOpen) renderLyrics();
  });

  el("now-playing-lyrics-download").addEventListener("click", () => {
    const track = state.queue[state.queueIndex];
    if (!track) return;
    if (IS_ANDROID_APP) {
      alert("Lyrics download isn't available in the standalone Android app yet.");
      return;
    }
    window.open(`/api/lyrics/${track.id}/download`, "_blank");
  });

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

  function renderLyricsInto(body) {
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

  function renderLyrics() {
    renderLyricsInto(el("lyrics-body"));
    if (state.nowPlayingLyricsOpen) renderLyricsInto(el("now-playing-lyrics"));
  }

  function updateLyricsHighlightIn(container) {
    const lines = container.querySelectorAll(".lyrics-line");
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

  function updateLyricsHighlight() {
    if (!state.lyrics || !state.lyrics.synced) return;
    if (state.lyricsOpen) updateLyricsHighlightIn(el("lyrics-body"));
    if (state.nowPlayingLyricsOpen) updateLyricsHighlightIn(el("now-playing-lyrics"));
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

  function onLyricsLineClick(e) {
    const line = e.target.closest(".lyrics-line");
    if (!line || !audio.duration) return;
    audio.currentTime = parseFloat(line.dataset.time);
  }
  el("lyrics-body").addEventListener("click", onLyricsLineClick);
  el("now-playing-lyrics").addEventListener("click", onLyricsLineClick);

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

  audio.addEventListener("play", () => {
    el("play-icon").outerHTML = ICONS.pause.replace("<svg", '<svg id="play-icon"');
    el("now-playing-play-icon").outerHTML = ICONS.pause.replace("<svg", '<svg id="now-playing-play-icon"');
  });
  audio.addEventListener("pause", () => {
    el("play-icon").outerHTML = ICONS.play.replace("<svg", '<svg id="play-icon"');
    el("now-playing-play-icon").outerHTML = ICONS.play.replace("<svg", '<svg id="now-playing-play-icon"');
  });

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

  function setSeekFill(elId, pct) {
    el(elId).style.setProperty("--progress", `${pct}%`);
  }

  audio.addEventListener("timeupdate", () => {
    if (!audio.duration) return;
    const pct = (audio.currentTime / audio.duration) * 100;
    el("seek").value = pct;
    setSeekFill("seek", pct);
    el("time-current").textContent = formatDuration(audio.currentTime);
    el("time-total").textContent = formatDuration(audio.duration);
    el("now-playing-seek").value = pct;
    setSeekFill("now-playing-seek", pct);
    el("now-playing-time-current").textContent = formatDuration(audio.currentTime);
    el("now-playing-time-total").textContent = formatDuration(audio.duration);
    updateLyricsHighlight();
  });

  el("seek").addEventListener("input", () => {
    if (!audio.duration) return;
    audio.currentTime = (el("seek").value / 100) * audio.duration;
    setSeekFill("seek", el("seek").value);
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
    document.querySelector('.nav-link[data-view="discover"]')?.remove();
  } else {
    loadLibStats();
    pollJobs();
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }
})();
