/* Offline shell only. Profile, recipes and plans are stored by storage.js. */
const CACHE = 'sondagsro-shell-v1';
const SHELL = [
  './', './index.html', './style.css', './manifest.webmanifest', './icon.svg', './apple-touch-icon.png',
  './src/app.js', './src/storage.js', './src/data.js', './src/engine.js', './src/offers.js', './src/visuals.js',
  './docs/INSTALLATION.md', './docs/NUTRITION.md', './docs/SOURCES.md'
];
self.addEventListener('install', event => {
  // All-or-nothing installation avoids claiming offline readiness with missing code.
  // A new worker waits until the old app windows are closed before activation.
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('sondagsro-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith(new URL('./', self.location.href).pathname)) return;
  const isPage = request.mode === 'navigate' || url.pathname.endsWith('.html') || url.pathname.endsWith('.md');
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    if (!isPage) {
      const cached = await cache.match(request);
      if (cached) return cached;
    }
    try {
      const response = await fetch(request);
      if (response.ok && response.type === 'basic') await cache.put(request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(request);
      if (cached) return cached;
      if (request.mode === 'navigate') return await cache.match('./index.html');
      throw error;
    }
  })());
});
