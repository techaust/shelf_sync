import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { RouterProvider } from "react-router";
import type { ApiClient } from "../api/client";
import { checkSession, type SessionState, type SessionStore } from "../api/session";
import { TipProvider } from "../components/Tip";
import { SessionGate } from "../screens/SessionGate";
import { createAppRouter } from "./router";

/**
 * Shows the result of the sign-in main.tsx started (the ticket never reaches React), then the shell; any later
 * 401 "signed_out" from the API client switches the tab to the signed-out state through the same store.
 */
export function App({
  api,
  session,
  started,
  queryClient,
}: {
  api: ApiClient;
  session: SessionStore;
  started: Promise<SessionState>;
  queryClient: QueryClient;
}) {
  const state = useSyncExternalStore(session.subscribe, session.get);

  useEffect(() => {
    let current = true;
    started.then((next) => {
      if (current && session.get().kind === "checking") session.set(next);
    });
    return () => {
      current = false;
    };
  }, [started, session]);

  // "Try again" (only after a session check got no answer; never after a ticket, which is used up): checks the
  // session once more.
  const retry = useCallback(() => {
    session.set({ kind: "checking" });
    checkSession(api).then(session.set);
  }, [api, session]);

  // One hash router per signed-in spell. Made in an effect, not during render, so it can be disposed (its popstate
  // listener removed) when the tab signs out or signs in again; StrictMode's extra mount and cleanup in development
  // makes a second router and disposes the first, which is correct too.
  const [router, setRouter] = useState<ReturnType<typeof createAppRouter> | null>(null);
  const signedIn = state.kind === "signed_in";
  useEffect(() => {
    if (!signedIn) return;
    const next = createAppRouter();
    setRouter(next);
    return () => {
      setRouter(null);
      next.dispose();
    };
  }, [signedIn]);

  return (
    <QueryClientProvider client={queryClient}>
      <TipProvider delayDuration={300}>
        {signedIn && router ? <RouterProvider router={router} /> : <SessionGate state={state} onRetry={retry} />}
      </TipProvider>
    </QueryClientProvider>
  );
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        // A refusal is final (signed out, forbidden); only a request that got no answer is tried again, twice.
        retry: (failures, error) => failures < 2 && error instanceof Error && error.name === "ApiUnreachableError",
      },
    },
  });
}
