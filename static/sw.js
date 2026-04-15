const SW_VERSION = 3;

self.addEventListener('install', e => {
  console.log('[SW] Installing v' + SW_VERSION);
  e.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', e => {
  console.log('[SW] Activating v' + SW_VERSION);
  e.waitUntil(self.clients.claim());
});

self.addEventListener('push', e => {
  console.log('[SW] Push received');
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
      for (const c of list) {
        if ('focus' in c) return c.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(e.notification.data.url || '/');
    })
  );
});
