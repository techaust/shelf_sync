import * as Tooltip from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";

/**
 * A tooltip on a focusable trigger (Radix Tooltip): opens on hover and on keyboard focus, closes on Esc without
 * moving focus or the pointer (WCAG 1.4.13), and describes the trigger to screen readers. Never the only place
 * information lives: the trigger's own text says what it is. Rendered in a portal, on the page's surfaces.
 */
export function Tip({
  content,
  children,
  side = "bottom",
  disabled = false,
}: {
  content: ReactNode;
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
  disabled?: boolean;
}) {
  if (disabled) return children;
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className="tip" side={side} sideOffset={8} collisionPadding={8}>
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export const TipProvider = Tooltip.Provider;
