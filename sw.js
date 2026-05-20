const CACHE_NAME = 'claude-dashboard-2b4b633245';

self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);

  // API 요청은 캐시하지 않음
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

  // HTML 페이지: 캐시 우선, 백그라운드에서 업데이트
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

// 새 SW 활성화 시 이전 캐시 삭제
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
