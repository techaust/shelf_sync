// The stores list and Test connection as hooks, shared by Settings › Stores and the shell's HealthArea (SET-01,
// ERR-01). The list is asked for again after each test, save or remove, and when the window regains focus; never on a
// timer. It lives in app/ (m2.5b), beside the shell that uses it, so no component imports a screen's module.

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { listStores, STORES_QUERY_KEY, testStore } from "../api/stores";
import { storeTests } from "../lib/storeTests";
import { useSwitchPhase } from "../screens/settings/switchStore";
import { useServices } from "./services";

export function useStoresQuery() {
  const { api } = useServices();
  const restarting = useSwitchPhase().kind === "restarting";
  return useQuery({
    queryKey: STORES_QUERY_KEY,
    queryFn: () => listStores(api),
    refetchOnWindowFocus: true,
    enabled: !restarting, // paused while ShelfSync restarts after an update
  });
}

/** Test connection for one store: one at a time per store, then the list is read again (the saved health). */
export function useRunStoreTest(): (id: number) => void {
  const { api } = useServices();
  const queryClient = useQueryClient();
  return useCallback(
    (id: number) => {
      void storeTests.run(
        id,
        () => testStore(api, id),
        () => queryClient.invalidateQueries({ queryKey: STORES_QUERY_KEY }),
      );
    },
    [api, queryClient],
  );
}
