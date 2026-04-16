const SW_VERSION = 4;
const CACHE_NAME = 'deures-shell-v4';

// App shell: files cached once and served instantly on repeat visits (saves egress)
const SHELL = [
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/manifest.json',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(c => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Only cache GET requests for our own origin
  if (e.request.method !== 'GET' || url.origin !== self.location.origin) return;

  // Static assets & uploads: cache-first (serve from cache, update in background)
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/uploads/')) {
    e.respondWith(
      caches.open(CACHE_NAME).then(cache =>
        cache.match(e.request).then(cached => {
          const fresh = fetch(e.request).then(resp => {
            if (resp.ok) cache.put(e.request, resp.clone());
            return resp;
          });
          return cached || fresh;
        })
      )
    );
    return;
  }

  // Everything else (HTML, API): network-first, no caching
});

self.addEventListener('push', e => {
  if (!e.data) return;
  let data;
  try { data = e.data.json(); }
  catch(err) { data = { title: 'deúres', body: e.data.text() }; }
  e.waitUntil(
    self.registration.showNotification(data.title || 'deúres', {
      body: data.body || '',
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      tag: 'deures-msg',
      renotify: true,
      data: { url: data.url || '/' }
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: 'window' }).then(list => {
      for (const c of list) { if ('focus' in c) return c.focus(); }
      if (self.clients.openWindow) return self.clients.openWindow(e.notification.data.url || '/');
    })
  );
});
