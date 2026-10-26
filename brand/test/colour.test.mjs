// Colour: the verdigris share, every contrast pair in 05 and 14 (and the new ones), the tray states not relying on
// colour, and tokens.json being TecHaust's file unchanged.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TRAY, VERSIONS } from "../geometry.mjs";
import { decodeIco } from "../lib/formats.mjs";
import { badgeGeometry } from "../lib/icons.mjs";
import { scanCoverage } from "../lib/render.mjs";
import { mark } from "../geometry.mjs";
import { contrasts, share } from "../lib/measure.mjs";
import { renderTokensCss, rgb, semantic, tokens } from "../lib/tokens.mjs";

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url));

describe("verdigris share (variant A, the cut piece)", () => {
  it("is the smaller part: 10.6 % of the vector mark, 9.3 % at 16 px", () => {
    const s = share();
    expect(s.vector).toBe(10.6);
    expect(s.px16).toBe(9.3);
    expect(s.vector).toBeLessThan(50);
  });
  it("uses verdigris-700 in every colour-version file and nothing else from the verdigris ramp", () => {
    const v700 = tokens.palette["verdigris-700"].toUpperCase();
    const others = Object.entries(tokens.palette).filter(([k]) => k.startsWith("verdigris-") && k !== "verdigris-700").map(([, v]) => v.toUpperCase());
    for (const kind of ["primary", "symbol", "endorsed", "stacked", "compact"]) {
      const svg = read(`assets/logo/logo-${kind}-color.svg`).toString();
      expect(svg).toContain(`fill="${v700}"`);
      for (const o of others) expect(svg).not.toContain(o);
    }
  });
});

describe("contrast", () => {
  const all = contrasts();
  it.each(all.map((c) => [c.label, c]))("%s meets its level", (_, c) => {
    expect(c.passes, `${c.ratio}:1 against ${c.min ?? "-"}:1`).toBe(true);
  });
  it("matches every value 05 and 14 state, except the three 05 values known to be off", () => {
    const off = all.filter((c) => !c.matches).map((c) => c.label);
    expect(off).toEqual(all.filter((c) => c.docMismatch).map((c) => c.label));
    expect(off).toEqual(["Control border on page (light)", "Control border on card (light)", "Success on page (light)"]);
  });
  it("covers every pair in 05 2.2 and 2.3 and 14 2.6", () => {
    const by = (doc) => all.filter((c) => c.doc === doc).length;
    expect(by("05 2.2")).toBe(37);
    expect(by("05 2.3")).toBe(5);
    expect(by("14 2.6")).toBe(12);
  });
});

describe("tray states", () => {
  const frames = (state, taskbar) => decodeIco(read(`assets/tray/tray-${state}-${taskbar}.ico`));
  const alphaIn = (f, box) => { const out = []; for (let y = box.y; y < box.y + box.h; y++) for (let x = box.x; x < box.x + box.w; x++) out.push(f.rgba[(y * f.size + x) * 4 + 3] >= 128 ? 1 : 0); return out; };
  it("paint the badges in the status colours from the tokens", () => {
    for (const taskbar of Object.keys(TRAY.taskbars)) for (const state of ["paused", "attention"]) {
      const want = rgb(semantic(TRAY.status[state], taskbar));
      for (const f of frames(state, taskbar)) {
        const b = badgeGeometry(f.size, state).box;
        const cx = Math.floor(b.x + b.w / 2), cy = b.y + b.h - 1 - Math.floor(b.h / 2);
        const at = (x, y) => [...f.rgba.subarray((y * f.size + x) * 4, (y * f.size + x) * 4 + 4)];
        const probe = state === "paused" ? at(b.x, b.y + 1) : at(cx, cy);
        expect(probe, `${state} ${taskbar} ${f.size}`).toEqual([...want, 255]);
      }
    }
  });
  it("differ by shape, not only colour: the paused and attention badges cover different pixels", () => {
    for (const taskbar of Object.keys(TRAY.taskbars)) {
      const p = frames("paused", taskbar), a = frames("attention", taskbar);
      p.forEach((pf, i) => {
        const af = a[i];
        const b = badgeGeometry(pf.size, "attention").box;
        const mp = alphaIn(pf, b), ma = alphaIn(af, b);
        const diff = mp.reduce((s, v, k) => s + (v !== ma[k] ? 1 : 0), 0);
        expect(diff / mp.length, `${taskbar} ${pf.size} px`).toBeGreaterThan(0.25);
      });
    }
  });
  it("hold only badge pixels inside the cut-out corner, with no sliver of the stem left", () => {
    for (const taskbar of Object.keys(TRAY.taskbars)) for (const state of ["paused", "attention"]) {
      const want = rgb(semantic(TRAY.status[state], taskbar));
      for (const f of frames(state, taskbar)) {
        const px = f.size, g = badgeGeometry(px, state), m = mark(px);
        const cut = scanCoverage(g.knockout, px, px), badge = scanCoverage(g.shape, px, px);
        for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
          const k = y * px + x, i = k * 4;
          const stem = x >= px - m.p.v && y >= m.f.y1; // the right stem's columns below the spine
          if (cut[k] === 0 && !stem) continue; // the knockout is snapped: any pixel it touches is cleared
          const where = `${state} ${taskbar} ${px} px at ${x},${y}`;
          expect(f.rgba[i + 3], where).toBe(Math.round(255 * badge[k]));
          if (f.rgba[i + 3]) expect([...f.rgba.subarray(i, i + 3)], where).toEqual(want);
        }
      }
    }
  });
  it("keep at least one fully clear pixel between the ink and the badge, all round", () => {
    // Every pixel with any badge colour and every pixel with any ink are at least 2 apart (Chebyshev): no ink pixel,
    // however faint, touches a badge pixel along a side or a corner.
    for (const taskbar of Object.keys(TRAY.taskbars)) for (const state of ["paused", "attention"]) {
      const want = rgb(semantic(TRAY.status[state], taskbar));
      for (const f of frames(state, taskbar)) {
        const px = f.size, kind = [];
        for (let k = 0; k < px * px; k++) {
          const a = f.rgba[k * 4 + 3];
          const isBadge = a > 0 && [0, 1, 2].every((c) => f.rgba[k * 4 + c] === want[c]);
          kind.push(a === 0 ? 0 : isBadge ? 2 : 1);
        }
        for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
          if (kind[y * px + x] !== 2) continue;
          for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
            const X = x + dx, Y = y + dy;
            if (X < 0 || Y < 0 || X >= px || Y >= px) continue;
            expect(kind[Y * px + X], `${state} ${taskbar} ${px} px: ink at ${X},${Y} touches the badge at ${x},${y}`).not.toBe(1);
          }
        }
      }
    }
  });
  it("leave the normal frame untouched outside the badge corner (paused and attention)", () => {
    for (const taskbar of Object.keys(TRAY.taskbars)) for (const state of ["paused", "attention"]) {
      const n = frames("normal", taskbar), s = frames(state, taskbar);
      n.forEach((nf, i) => {
        const g = TRAY.badge[nf.size];
        const top = nf.size - g.box - g.gap;
        const len = top * nf.size * 4; // every row above the badge's gap, all four channels
        expect(Buffer.from(s[i].rgba.subarray(0, len)).equals(Buffer.from(nf.rgba.subarray(0, len))), `${state} ${taskbar} ${nf.size} px`).toBe(true);
      });
    }
  });
});

describe("tokens", () => {
  it("tokens.json is TecHaust's file byte for byte, plus the two recorded keys", () => {
    const text = read("tokens.json").toString();
    const raw = JSON.parse(text);
    expect(raw.$copied).toBe("2026-10-26");
    expect(raw.$source).toMatch(/techaust_platform packages\/ui\/tokens\/tokens\.json/);
    const original = text.split("\n").filter((l) => !l.startsWith('  "$source"') && !l.startsWith('  "$copied"')).join("\n");
    const sha = createHash("sha256").update(original).digest("hex");
    expect(raw.$source).toContain(sha);
  });
  it("tokens.css carries every palette colour and every semantic colour in light and dark", () => {
    const css = renderTokensCss();
    for (const [k, v] of Object.entries(tokens.palette)) expect(css).toContain(`--color-${k}: ${v.toLowerCase()};`);
    const dark = css.slice(css.indexOf(':root[data-theme="dark"]'));
    for (const k of Object.keys(tokens.semantic)) {
      expect(css).toContain(`--color-${k}: ${semantic(k, "light").toLowerCase()};`);
      expect(dark).toContain(`--color-${k}: ${semantic(k, "dark").toLowerCase()};`);
    }
  });
  it("the five versions use palette tokens only", () => {
    for (const v of Object.values(VERSIONS)) for (const k of ["base", "accent", "text", "on"]) expect(tokens.palette[v[k]], `${k} ${v[k]}`).toBeTruthy();
  });
});
