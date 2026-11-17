// Night mode before the first paint, on the signed-in app only (owner, 2026-11-15); public pages stay day. A file of
// its own, never inline, so the Content-Security-Policy can forbid inline scripts (Codex audit, 2026-11-15). Mirrors
// src/lib/theme.ts (key "paperaid.appearance": light, dark or system).
(function () {
  try {
    if (!/^\/(app|admin)(\/|$)/.test(location.pathname)) return
    var a = localStorage.getItem('paperaid.appearance')
    if (a === 'dark' || (a === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)) document.documentElement.dataset.theme = 'dark'
  } catch (e) {
    /* storage unavailable: day */
  }
})()
