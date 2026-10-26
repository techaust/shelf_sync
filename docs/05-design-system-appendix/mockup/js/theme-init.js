// Sets the theme before first paint: ?theme=light|dark in the hash wins, otherwise the system theme (UI-SHELL).
// Nothing is saved: the override lives only in the address bar's hash.
"use strict";
(() => {
  const m = /[?&]theme=(light|dark)/.exec(location.hash);
  const dark = m ? m[1] === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
