import { createContext, type ReactNode, useContext } from "react";
import type { ApiClient } from "../api/client";
import type { SessionStore } from "../api/session";

/** The tab's one API client and session store, for the screens that read or write through the API (M1b on). */
export interface Services {
  api: ApiClient;
  session: SessionStore;
}

const ServicesContext = createContext<Services | null>(null);

export function ServicesProvider({ value, children }: { value: Services; children: ReactNode }) {
  return <ServicesContext.Provider value={value}>{children}</ServicesContext.Provider>;
}

export function useServices(): Services {
  const services = useContext(ServicesContext);
  if (!services) throw new Error("useServices needs a ServicesProvider");
  return services;
}
