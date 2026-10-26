// UI-SHELL: the theme follows Windows by default, with a manual override (system, light, dark) kept in
// localStorage as a convenience only: a broken or missing storage never stops the page.
import { describe, expect, it } from "vitest";
import {
  applyTheme,
  readPreference,
  resolveTheme,
  savePreference,
  THEME_STORAGE_KEY,
  type ThemeHost,
  type ThemePreference,
} from "./theme";

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

function host(options: { storage?: ReturnType<typeof memoryStorage> | null; dark?: boolean; throwing?: boolean }) {
  const root = { dataset: {} as DOMStringMap };
  const broken = {
    getItem: () => {
      throw new Error("SecurityError");
    },
    setItem: () => {
      throw new Error("QuotaExceededError");
    },
    removeItem: () => {
      throw new Error("SecurityError");
    },
  };
  const theHost: ThemeHost = {
    storage: () => (options.throwing ? broken : (options.storage ?? null)),
    prefersDark: () => options.dark ?? false,
    root: () => root,
  };
  return { theHost, root };
}

describe("resolveTheme", () => {
  it.each<[ThemePreference, boolean, string]>([
    ["system", false, "light"],
    ["system", true, "dark"],
    ["light", true, "light"],
    ["dark", false, "dark"],
  ])("%s with Windows dark=%s gives %s", (preference, dark, expected) => {
    expect(resolveTheme(preference, dark)).toBe(expected);
  });
});

describe("the stored preference", () => {
  it("defaults to following Windows", () => {
    expect(readPreference(host({ storage: memoryStorage() }).theHost)).toBe("system");
  });

  it("reads a saved override", () => {
    expect(readPreference(host({ storage: memoryStorage({ [THEME_STORAGE_KEY]: "dark" }) }).theHost)).toBe("dark");
  });

  it.each(["", "blue", "DARK", "system ", "{}"])("ignores a value that isn't a preference: %j", (value) => {
    expect(readPreference(host({ storage: memoryStorage({ [THEME_STORAGE_KEY]: value }) }).theHost)).toBe("system");
  });

  it("saving light or dark stores it; saving system removes it", () => {
    const storage = memoryStorage();
    const { theHost } = host({ storage });
    savePreference(theHost, "light");
    expect(storage.data.get(THEME_STORAGE_KEY)).toBe("light");
    savePreference(theHost, "system");
    expect(storage.data.has(THEME_STORAGE_KEY)).toBe(false);
  });

  it("works without storage, and with storage that throws", () => {
    for (const theHost of [host({ storage: null }).theHost, host({ throwing: true }).theHost]) {
      expect(readPreference(theHost)).toBe("system");
      expect(() => savePreference(theHost, "dark")).not.toThrow();
    }
  });
});

describe("applyTheme", () => {
  it("an override sets data-theme on the root", () => {
    const { theHost, root } = host({ dark: true });
    expect(applyTheme(theHost, "light")).toBe("light");
    expect(root.dataset.theme).toBe("light");
    expect(applyTheme(theHost, "dark")).toBe("dark");
    expect(root.dataset.theme).toBe("dark");
  });

  it('"system" removes data-theme, so the stylesheet follows Windows live (every screen, signed out too)', () => {
    const { theHost, root } = host({ dark: true });
    applyTheme(theHost, "dark");
    expect(applyTheme(theHost, "system")).toBe("dark");
    expect("theme" in root.dataset).toBe(false);
  });

  it("reports light when the media query can't be read, and still sets no attribute", () => {
    const { theHost, root } = host({});
    theHost.prefersDark = () => {
      throw new Error("no matchMedia");
    };
    expect(applyTheme(theHost, "system")).toBe("light");
    expect("theme" in root.dataset).toBe(false);
  });
});
