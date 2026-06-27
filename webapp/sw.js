/* Service worker for the parklife PWA.
 *
 * - App shell (same-origin HTML/JS/manifest/icon): cache-first with a background
 *   refresh → instant loads, works offline.
 * - /api/* : network-first with cache fallback → fresh data when online, last
 *   known data when offline.
 * - Cross-origin (Leaflet from unpkg, map tiles): not intercepted; the browser
 *   handles them normally (tiles would bloat the cache).
 */
const VERSION = 'parklife-v1';
const SHELL = ['/', '/index.html', '/app.js', '/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // let cross-origin pass through

  if (url.pathname.startsWith('/api/')) {
    // network-first, fall back to cached response when offline
    e.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // app shell: cache-first, refresh in the background
  e.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy));
        return res;
      }).catch(() => cached);
      return cached || network;
    })
  );
});
