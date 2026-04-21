const CACHE_NAME = "aether-shell-v2";
const APP_SHELL = ["/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const requestUrl = new URL(event.request.url);
  const isDocumentRequest = event.request.mode === "navigate" || requestUrl.pathname === "/";

  if (isDocumentRequest) {
    event.respondWith(
      fetch(event.request).catch(
        () => new Response("AETHER dashboard is offline. Reconnect to refresh the command surface.", { status: 503 }),
      ),
    );
    return;
  }

  if (requestUrl.pathname.startsWith("/assets/") || requestUrl.pathname === "/manifest.webmanifest") {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) {
          return cached;
        }

        return fetch(event.request).then((response) => {
          if (!response.ok) {
            return response;
          }

          const clone = response.clone();
          event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone)));
          return response;
        });
      }),
    );
  }
});
