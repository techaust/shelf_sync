import type { ReactNode } from "react";
import { Link } from "react-router";
import logoUrl from "../assets/brand/logo-primary-dark.svg";

/** The approved primary lockup, dark version (the app bar is ink in both themes), 24 px high. */
export function Logo() {
  return <img className="app-bar__logo" src={logoUrl} alt="" width={159} height={24} />;
}

/**
 * The app bar (UI-SHELL): logo, then whatever the shell puts in it (health, theme, Pause everything). It carries
 * the .tone-dark token scope, so its contents use the dark semantic tokens in both themes (05 section 2.2).
 */
export function AppBar({ children, home = true }: { children?: ReactNode; home?: boolean }) {
  return (
    <header className="app-bar tone-dark">
      {home ? (
        <Link className="app-bar__logo-link" to="/" aria-label="ShelfSync, go to Dashboard">
          <Logo />
        </Link>
      ) : (
        <span className="app-bar__logo-link" role="img" aria-label="ShelfSync">
          <Logo />
        </span>
      )}
      {children}
    </header>
  );
}
