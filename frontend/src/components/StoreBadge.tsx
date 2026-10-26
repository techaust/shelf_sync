import type { CSSProperties } from "react";
import type { StoreIdentifier } from "../api/placeholder";

/**
 * A store's identifier (05 section 2.3): its shape, its dot colour and its two-letter code in text, so a store is
 * never told apart by colour alone. The dot colours are the store's data; they reach the stylesheet as custom
 * properties set through the CSSOM (allowed by the CSP's style-src 'self'; no style attribute in the HTML).
 */
export function StoreBadge({ store }: { store: StoreIdentifier }) {
  const dot = { "--dot-light": store.dot.light, "--dot-dark": store.dot.dark } as CSSProperties;
  return (
    <span className="store-badge">
      <span className={`store-dot is-${store.shape}`} style={dot} aria-hidden="true" />
      {store.code}
      <span className="sr-only"> ({store.name})</span>
    </span>
  );
}
