const CACHE_NAME = "aether-shell-v2";

function basePath() {
  return new URL(self.registration.scope).pathname;
}

function assetPath(pathname) {
  return new URL(pathname, self.registration.scope).pathname;
}

self.addEventListener("install", (event) => {
  const appShell = [assetPath("manifest.webmanifest")];
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(appShell)).then(() => self.skipWaiting()),
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
  const rootPath = basePath();
  const manifestPath = assetPath("manifest.webmanifest");
  const assetsPath = assetPath("assets/");
  const isDocumentRequest =
    event.request.mode === "navigate" ||
    requestUrl.pathname === rootPath ||
    requestUrl.pathname === `${rootPath}index.html`;

  if (isDocumentRequest) {
    event.respondWith(
      fetch(event.request).catch(
        () => new Response("AETHER dashboard is offline. Reconnect to refresh the command surface.", { status: 503 }),
      ),
    );
    return;
  }

  if (requestUrl.pathname.startsWith(assetsPath) || requestUrl.pathname === manifestPath) {
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
