// Minimal service worker: exists only to satisfy PWA installability
// requirements (Chrome/Edge/Firefox on Windows and Linux). It does not
// cache anything — this is a local app talking to a local server, so
// offline caching of API responses would be actively wrong.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", () => {
  // Intentionally not intercepted — always hit the network.
});
