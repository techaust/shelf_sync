// 1. The theme, first: set before anything renders (no inline script; the CSP forbids one).
import "./theme/early";
import "./styles/app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App, makeQueryClient } from "./app/App";
import { boot } from "./app/boot";

// 2. Sign-in (SYS-03): the ticket leaves the address, then the one request; the #t= listeners go on before the
//    router exists. The order is in boot.ts and tested there.
const { api, session, started } = boot(window);

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App api={api} session={session} started={started} queryClient={makeQueryClient()} />
    </StrictMode>,
  );
}
