import type { components } from "../api/schema";

/** A store's colour key, as the backend stores and serves it (`StoreModel.color`). */
export type StoreColor = components["schemas"]["StoreModel"]["color"];

/**
 * The store identifier colours (05 section 2.3): each key the backend allows maps to its light and dark dot. Typed as a
 * record over the schema's own union, so a key the backend adds without a pair here fails `npm run typecheck`.
 * `indigo` is GPLFamily's pair (brand primary) and `teal` is PluginWay's (a deeper teal chosen for contrast). The values
 * are store data, not design tokens; `contrast.test.ts` checks every pair for 3:1 on every surface it can sit on.
 */
export const STORE_PALETTE: Record<StoreColor, { light: string; dark: string }> = {
  indigo: { light: "#4d4d99", dark: "#a3a3e6" },
  teal: { light: "#007b80", dark: "#3cc8cb" },
};
