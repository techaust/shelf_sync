import { BookOpen, ChevronLeft, ChevronRight, X } from "lucide-react";
import { type MouseEvent, useEffect, useRef, useSyncExternalStore } from "react";
import { type DialogBehaviour, dialogBehaviour } from "../dialog";
import { Tip } from "../Tip";
import { GuideBody, H } from "./guides";
import { firstFocus, GUIDE_IDS, type GuideId, helpStore } from "./helpModel";

export function useHelp() {
  return useSyncExternalStore(helpStore.subscribe, helpStore.get, helpStore.get);
}

/** The app bar's Help button (the approved mockup's "?"), on every screen. */
export function HelpButton() {
  const { open } = useHelp();
  return (
    <Tip content={H.open}>
      <button
        type="button"
        className="btn is-icon help-btn"
        aria-label={H.open}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => helpStore.open(null)}
      >
        <span className="help-btn__glyph" aria-hidden="true">
          ?
        </span>
      </button>
    </Tip>
  );
}

/**
 * The Help panel (UI-HELP): a right-hand drawer on the native <dialog>, opened modally like ConfirmDialog (dialog.ts):
 * the browser traps the focus and makes the page inert, Esc closes it, and the focus goes back to the button that
 * opened it. It opens at its start (the guides) or straight at one guide (a page's "… guide" button).
 *
 * M5 adds two parts, in the places marked below: the current screen's own help above the guides, and the glossary
 * ("What does this word mean?", 13 section 5) under them. Nothing stands in for them until then.
 */
export function HelpPanel() {
  const { open, guide } = useHelp();
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const guideTitle = useRef<HTMLHeadingElement>(null);
  const guideLinks = useRef(new Map<GuideId, HTMLButtonElement>());
  const behaviour = useRef<DialogBehaviour | null>(null);
  const shown = useRef(false);
  const lastGuide = useRef<GuideId | null>(guide);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const made = dialogBehaviour(element, {
      onCancel: () => helpStore.close(),
      isBusy: () => false,
      fallback: () => document.querySelector<HTMLElement>("[data-nav-focus], h1"),
    });
    behaviour.current = made;
    return () => {
      behaviour.current = null;
      shown.current = false;
      made.dispose();
    };
  }, []);

  // Open and close only on a change of `open`; the first focus follows firstFocus().
  useEffect(() => {
    const made = behaviour.current;
    if (!made || open === shown.current) return;
    shown.current = open;
    if (open) {
      const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      lastGuide.current = helpStore.get().guide;
      made.open(firstFocus(helpStore.get().guide) === "guide-title" ? guideTitle.current : close.current, opener);
    } else made.close();
  }, [open]);

  // Moving between the guides inside the open panel: into a guide, its title; back, the guide's own link.
  useEffect(() => {
    if (!shown.current || guide === lastGuide.current) return;
    const from = lastGuide.current;
    lastGuide.current = guide;
    if (guide) guideTitle.current?.focus();
    else if (from) guideLinks.current.get(from)?.focus();
  }, [guide]);

  // A click on the backdrop (outside the drawer's box) closes it; a click in the drawer's own space doesn't.
  const onClick = (event: MouseEvent<HTMLDialogElement>) => {
    const element = dialog.current;
    if (!element || event.target !== element) return;
    const box = element.getBoundingClientRect();
    const outside =
      event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom;
    if (outside) helpStore.close();
  };

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: the backdrop click is a pointer extra; Esc and Close do the same
    <dialog ref={dialog} className="help-panel" aria-labelledby="help-title" onClick={onClick}>
      <div className="help-panel__head">
        <h2 className="help-panel__title" id="help-title">
          {H.title}
        </h2>
        <button
          ref={close}
          type="button"
          className="btn is-ghost is-icon"
          aria-label={H.close}
          onClick={() => helpStore.close()}
        >
          <X className="icon" aria-hidden="true" />
        </button>
      </div>
      <div className="help-panel__body">
        {guide ? (
          <section className="help-sec guide" aria-labelledby="help-guide-title">
            <button type="button" className="btn is-ghost is-compact guide__back" onClick={() => helpStore.show(null)}>
              <ChevronLeft className="icon" aria-hidden="true" />
              {H.allGuides}
            </button>
            <h3 className="guide__title" id="help-guide-title" ref={guideTitle} tabIndex={-1}>
              {H.guideTitles[guide]}
            </h3>
            <GuideBody guide={guide} onLeave={() => helpStore.close()} />
          </section>
        ) : (
          <>
            {/* M5: the current screen's own help goes here, above the guides. */}
            <section className="help-sec" aria-labelledby="help-guides-title">
              <h3 id="help-guides-title">{H.guides}</h3>
              <ul className="help-guides">
                {GUIDE_IDS.map((id) => (
                  <li key={id}>
                    <button
                      type="button"
                      className="help-guides__link"
                      ref={(element) => {
                        if (element) guideLinks.current.set(id, element);
                        else guideLinks.current.delete(id);
                      }}
                      onClick={() => helpStore.show(id)}
                    >
                      <BookOpen className="icon" aria-hidden="true" />
                      <span>{H.guideTitles[id]}</span>
                      <ChevronRight className="icon help-guides__go" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            {/* M5: the glossary, "What does this word mean?" (13 section 5), goes here, under the guides. */}
          </>
        )}
      </div>
    </dialog>
  );
}
