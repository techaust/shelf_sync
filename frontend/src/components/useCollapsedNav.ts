import { useCallback, useEffect, useState } from "react";

/** 05 section 6: designed for 1280-1920 px; usable at 1024 px with the nav collapsed to icons. */
export const WIDE_QUERY = "(min-width: 80rem)";

function isWide(): boolean {
  return typeof window.matchMedia === "function" ? window.matchMedia(WIDE_QUERY).matches : true;
}

/**
 * Collapsed below 1280 px, expanded above. The owner's click overrides that until the window crosses 1280 px,
 * when the automatic choice takes over again (as in the approved mockup).
 */
export function useCollapsedNav(): { collapsed: boolean; toggle: () => void } {
  const [wide, setWide] = useState(isWide);
  const [override, setOverride] = useState<boolean | null>(null);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(WIDE_QUERY);
    const onChange = () => {
      setWide(query.matches);
      setOverride(null);
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const collapsed = override ?? !wide;
  const toggle = useCallback(() => setOverride(!collapsed), [collapsed]);
  return { collapsed, toggle };
}
