/* Local app shell. Profile, plans, recipes and checkmarks stay in localStorage. */
const SCOPE = new URL('./', self.location.href);
const CACHE = 'mealpreppe-v3-' + encodeURIComponent(SCOPE.pathname);
const SHELL = ['./', './index.html', './manifest.webmanifest', './apple-touch-icon.png'];
self.addEventListener('install', event => {
  // The complete shell must exist. Updates wait until previous app windows close.
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key === CACHE || !/^(mealpreppe-|sondagsro-(shell|flat)-)/.test(key)) continue;
      const old = await caches.open(key);
      // Cache names are origin-wide: remove only caches containing this app's shell.
      const belongsHere = await old.match(new URL('index.html', SCOPE).href) || await old.match(SCOPE.href);
      if (belongsHere) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== SCOPE.origin || !url.pathname.startsWith(SCOPE.pathname)) return;
  // Daily prices are not frozen into the shell cache. The app retains its last
  // validated prices locally and reports offline or failed fetching honestly.
  if (url.pathname.endsWith('/offers.json')) return;
  const networkFirst = request.mode === 'navigate' || /\.(html|md|json|webmanifest)$/.test(url.pathname);
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    if (!networkFirst) {
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
      if (request.mode === 'navigate') {
        const shell = await cache.match(new URL('index.html', SCOPE).href);
        if (shell) return shell;
      }
      throw error;
    }
  })());
});
