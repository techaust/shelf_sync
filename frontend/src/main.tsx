// 1. The theme, first: set before anything renders (no inline script; the CSP forbids one).
import "./theme/early";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App, makeQueryClient } from "./app/App";
import { boot } from "./app/boot";
import { switchStore } from "./screens/settings/switchStore";

// 2. Sign-in (SYS-03): the ticket leaves the address, then the one request; the #t= listeners go on before the
//    router exists. The order is in boot.ts and tested there. While ShelfSync restarts after an Install or Roll back,
//    a 401 goes to the switch store (the restart panel), not to the lock panel.
const { api, session } = boot(window, undefined, () => switchStore.claimSignedOut());

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App api={api} session={session} queryClient={makeQueryClient()} />
    </StrictMode>,
  );
}
