import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, type LucideIcon, Monitor, Moon, Sun } from "lucide-react";
import { isThemePreference, type ThemePreference } from "../theme/theme";
import { useSavedTheme } from "../theme/useSavedTheme";

// Wording from the approved mockup's Settings, App, Theme (docs/05-design-system-appendix/mockup/js/screens-b.js).
const OPTIONS: { value: ThemePreference; label: string; Icon: LucideIcon }[] = [
  { value: "system", label: "Same as Windows", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

/**
 * The manual theme override in the app bar (UI-SHELL): Same as Windows (default), Light, Dark. A Radix dropdown
 * menu with radio items (arrow keys, Enter, Esc, focus returns to the button). It is non-modal on purpose: the
 * modal menu locks page scrolling by injecting a <style> element, which the CSP (style-src 'self') refuses.
 * It shares the tab's one theme with Settings › App, and a choice here is saved too (useSavedTheme).
 */
export function ThemeMenu() {
  const { preference, choose } = useSavedTheme();
  const current = OPTIONS.find((option) => option.value === preference) ?? OPTIONS[0];
  const CurrentIcon = current?.Icon ?? Monitor;
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button type="button" className="btn is-icon" aria-label={`Theme: ${current?.label ?? "Same as Windows"}`}>
          <CurrentIcon className="icon" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content className="menu" align="end" sideOffset={8} collisionPadding={8}>
          <DropdownMenu.Label className="menu__label">Theme</DropdownMenu.Label>
          <DropdownMenu.RadioGroup
            value={preference}
            onValueChange={(value) => {
              if (isThemePreference(value)) void choose(value);
            }}
          >
            {OPTIONS.map(({ value, label, Icon }) => (
              <DropdownMenu.RadioItem key={value} value={value} className="menu__item">
                <Icon className="icon" />
                <span>{label}</span>
                <DropdownMenu.ItemIndicator className="menu__check">
                  <Check className="icon" />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
