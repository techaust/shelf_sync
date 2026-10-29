import type { CSSProperties } from "react";
import type { StoreIdentifier } from "../api/placeholder";

/** The dot's colours as custom properties, set through the CSSOM (allowed by the CSP's style-src 'self'; React sets
 *  them on the element's style object, never as a style attribute in the HTML). */
function dotColours(dot: StoreIdentifier["dot"]): CSSProperties {
  return { "--dot-light": dot.light, "--dot-dark": dot.dark } as CSSProperties;
}

/** A store's shape in its colour, on its own (the identifier picker's choices). Decorative: the text beside it names
 *  the shape and the colour. */
export function StoreDot({ shape, dot }: Pick<StoreIdentifier, "shape" | "dot">) {
  return <span className={`store-dot is-${shape}`} style={dotColours(dot)} aria-hidden="true" />;
}

/**
 * A store's identifier (05 section 2.3): its shape, its dot colour and its two-letter code in text, so a store is
 * never told apart by colour alone. The dot colours are the store's data (storePalette.ts), not app styling.
 */
export function StoreBadge({ store, large = false }: { store: StoreIdentifier; large?: boolean }) {
  return (
    <span className={`store-badge${large ? " is-large" : ""}`}>
      <StoreDot shape={store.shape} dot={store.dot} />
      {store.code}
      {store.name ? <span className="sr-only"> ({store.name})</span> : null}
    </span>
  );
}
