export function registerServiceWorker(): void {
  if (!("serviceWorker" in navigator)) return;

  window.addEventListener(
    "load",
    () => {
      navigator.serviceWorker.register("/sw.js").catch((error: unknown) => {
        // PWA failure must never prevent the core web experience.
        console.warn("Service worker registration failed", error);
      });
    },
    { once: true },
  );
}
