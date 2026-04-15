const SW_VERSION = 2;

self.addEventListener('install', e => {
  console.log('[SW] Installing v' + SW_VERSION);
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  console.log('[SW] Activating v' + SW_VERSION);
  e.waitUntil(clients.claim());
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(fetch(e.request).catch(() => new Response('Offline', {status: 503})));
});

self.addEventListener('push', e => {
  console.log('[SW] Push received', e);
  if (!e.data) {
    console.log('[SW] Push has no data');
    return;
  }
  let data;
  try {
    data = e.data.json();
    console.log('[SW] Push data:', data);
  } catch(err) {
    console.log('[SW] Failed to parse push data:', err);
    data = { title: 'deúres', body: e.data.text() };
  }
  e.waitUntil(
    self.registration.showNotification(data.title || 'deúres', {
      body: data.body || '',
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      tag: 'deures-msg',
      renotify: true,
      requireInteraction: false,
      data: { url: data.url || '/' }
    }).then(() => {
      console.log('[SW] Notification shown OK');
    }).catch(err => {
      console.log('[SW] showNotification error:', err);
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window' }).then(list => {
      for (const c of list) {
        if (c.url === e.notification.data.url && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow(e.notification.data.url);
    })
  );
});
