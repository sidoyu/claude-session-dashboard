const CACHE_NAME = 'claude-dashboard-v2';

self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);

  // Don't cache API requests
  if (url.pathname.startsWith('/active') ||
      url.pathname.startsWith('/start/') ||
      url.pathname.startsWith('/stop/') ||
      url.pathname.startsWith('/search') ||
      url.pathname.startsWith('/refresh') ||
      url.pathname.startsWith('/hidden') ||
      url.pathname.startsWith('/new-session') ||
      url.pathname.startsWith('/rename/') ||
      url.pathname === '/whoami') {
    return;
  }

  // HTML pages: cache-first, update in background
  event.respondWith(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.match(event.request).then(function(cached) {
        var fetched = fetch(event.request).then(function(response) {
          if (response.ok) {
            cache.put(event.request, response.clone());
          }
          return response;
        }).catch(function() {
          return cached;
        });

        return cached || fetched;
      });
    })
  );
});

// Clean up old caches on activation
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(n) { return n !== CACHE_NAME; })
          .map(function(n) { return caches.delete(n); })
      );
    })
  );
});
