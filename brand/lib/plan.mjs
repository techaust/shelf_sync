// The complete list of generated files, as { "path relative to brand/": Buffer | string }. The build writes exactly
// these; the drift test regenerates them in memory and compares them with the files on disk: byte for byte where
// there is no zlib (SVG, CSS, JSON, BMP, ICO directories and bitmap frames), by decoded pixels for PNG data.
import { APP_ICON, FAVICON_ICO_SIZES, TRAY } from "../geometry.mjs";
import { artCanvases } from "./art.mjs";
import { encodeBmp, encodeIco, encodePng } from "./formats.mjs";
import { appFrame, faviconSvg, trayFrame } from "./icons.mjs";
import { logoFiles, minimums } from "./lockups.mjs";
import { channelClear, contrasts, pixelFit, ratios, share } from "./measure.mjs";
import { renderTokensCss, tokenSource } from "./tokens.mjs";

const png = (c) => encodePng(c.w, c.h, c.pixels());

/** Every generated file plus the frames and facts the review page shows. */
export async function plan() {
  const files = {};
  const frames = {}; // icon frames as RGBA, for the review page's enlarged views and the tests
  files["generated/tokens.css"] = renderTokensCss();

  for (const [name, svg] of Object.entries(await logoFiles())) files[`assets/logo/${name}`] = svg;

  // App icon and favicon.ico (the same plate frames).
  const app = Object.fromEntries(APP_ICON.sizes.map((px) => [px, appFrame(px)]));
  const asFrames = (sizes) => sizes.map((px) => ({ size: px, rgba: app[px].pixels() }));
  files["assets/app/shelfsync.ico"] = encodeIco(asFrames(APP_ICON.sizes), { dibMax: APP_ICON.dibMax });
  files["assets/favicon/favicon.ico"] = encodeIco(asFrames(FAVICON_ICO_SIZES), { dibMax: APP_ICON.dibMax });
  files["assets/favicon/favicon.svg"] = faviconSvg();
  for (const px of APP_ICON.sizes) frames[`app-${px}`] = { size: px, canvas: app[px] };

  // Tray icons: one .ico per taskbar theme and state.
  for (const taskbar of Object.keys(TRAY.taskbars)) for (const state of TRAY.states) {
    const list = TRAY.sizes.map((px) => {
      const c = trayFrame(px, taskbar, state);
      frames[`tray-${state}-${taskbar}-${px}`] = { size: px, canvas: c };
      return { size: px, rgba: c.pixels() };
    });
    files[`assets/tray/tray-${state}-${taskbar}.ico`] = encodeIco(list, { dibMax: 256 });
  }

  // Installer art (BMP for NSIS, PNG for previews) and GitHub images.
  const art = await artCanvases();
  for (const k of ["panel", "header"]) {
    const c = art[k].canvas;
    files[`assets/installer/installer-${k}.bmp`] = encodeBmp(c.w, c.h, c.pixels());
    files[`assets/installer/installer-${k}.png`] = png(c);
  }
  files["assets/github/social-preview.png"] = png(art.social.canvas);
  files["assets/github/readme-header-light.png"] = png(art["readme-light"].canvas);
  files["assets/github/readme-header-dark.png"] = png(art["readme-dark"].canvas);

  const facts = {
    generatedBy: "brand/scripts/build.mjs (npm run build)",
    tokens: tokenSource,
    share: share(), ratios: ratios(), pixelFit: pixelFit(), channelClear16: channelClear(16),
    minimums: await minimums(),
    installer: {
      panel: { box: round(art.panel.box), symbol: art.panel.placed },
      header: { box: round(art.header.box), symbol: art.header.placed },
    },
    contrasts: contrasts().map(({ doc, label, fg, fgName, bg, ratio, stated, min, matches, passes, docMismatch }) => ({ doc, label, fg: fgName ?? fg, hex: fg, bg, ratio, stated, min, matches, passes, docMismatch })),
  };
  files["generated/measurements.json"] = JSON.stringify(facts, null, 2) + "\n";
  return { files, frames, art, facts };
}

function round(o) {
  return Object.fromEntries(Object.entries(o).map(([k, v]) => [k, Math.round(v * 100) / 100]));
}
