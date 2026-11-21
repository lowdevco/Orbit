{% load static %}// Orbit service worker: cache the app shell, network-first for pages, offline fallback.
const CACHE = "orbit-v2";
const SHELL = [
  "{% static 'css/orbit.css' %}", "{% static 'js/orbit.js' %}", "{% static 'js/components/select.js' %}", "{% static 'icons/icon-192.png' %}",
  "{% static 'fonts/inter.woff2' %}", "{% static 'fonts/space-grotesk.woff2' %}", "/offline/",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.mode === "navigate") {
    // Pages are private per user: never cache them, just fall back when offline.
    e.respondWith(fetch(req).catch(() => caches.match("/offline/")));
    return;
  }
  if (new URL(req.url).pathname.startsWith("/static/")) {
    // Network-first so new deploys are picked up; cached copy only when offline.
    e.respondWith(
      fetch(req)
        .then((resp) => { const copy = resp.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return resp; })
        .catch(() => caches.match(req))
    );
  }
});
