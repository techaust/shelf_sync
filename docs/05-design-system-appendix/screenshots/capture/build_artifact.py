# Builds one self-contained artifact page from the P3.4 mockup (read-only on the mockup).
# Usage: python -I build_artifact.py <mockup_dir> <out_file>
import base64, re, sys
from pathlib import Path

src = Path(sys.argv[1]); out = Path(sys.argv[2])
html = (src / "index.html").read_text(encoding="utf-8")

def b64(p, mime):
    return f"data:{mime};base64," + base64.b64encode((src / p).read_bytes()).decode()

def css_file(rel):
    text = (src / rel).read_text(encoding="utf-8")
    base = (src / rel).parent
    def font(m):
        path = (base / m.group(1)).resolve().relative_to(src.resolve())
        return f'url("{b64(path, "font/woff2")}")'
    return re.sub(r'url\("([^"]+\.woff2)"\)', font, text)

head, body = html.split("<body>", 1)
body = body.rsplit("</body>", 1)[0]
title = re.search(r"<title>.*?</title>", head).group(0)
styles = [css_file(m) for m in re.findall(r'<link rel="stylesheet" href="([^"?]+)', head)]
scripts = re.findall(r'<script src="([^"?]+)', head)
sprite = (src / "icons/sprite.svg").read_text(encoding="utf-8")
sprite = re.sub(r"<\?xml.*?\?>", "", sprite).strip()
sprite = sprite.replace("<svg", '<svg aria-hidden="true" style="position:absolute;width:0;height:0;overflow:hidden"', 1)

def fix(s):
    return s.replace("icons/sprite.svg#", "#").replace("logo/", "data-logo/")

body = fix(body)
js = "\n".join(f"/* {s} */\n" + fix((src / s).read_text(encoding="utf-8")) for s in scripts)
for f in sorted((src / "logo").glob("*.svg")):
    js = js.replace(f"data-logo/{f.name}", b64(f"logo/{f.name}", "image/svg+xml"))
    body = body.replace(f"data-logo/{f.name}", b64(f"logo/{f.name}", "image/svg+xml"))

# Phones (owner, 2026-10-26): ShelfSync has no phone layout (05 §6), so below 1024 px the artifact
# shows the 1280 px desktop layout shrunk to the screen width, with a one-line note. Artifact only.
FIT_CSS = """
body{background:var(--color-bg, Canvas)}
.fit-note{display:none;margin:0;padding:calc(8px * var(--fit-inv, 1)) calc(16px * var(--fit-inv, 1));font:calc(15px * var(--fit-inv, 1))/1.4 Archivo,Arial,sans-serif;
  background:var(--color-surface-alt);color:var(--color-text);border-bottom:1px solid var(--color-border)}
html.is-fit .fit-note{display:block}
html.is-fit body{width:1280px}
"""
FIT_NOTE = ('<p class="fit-note" role="note">ShelfSync is a desktop app. On a phone this mockup shows the PC layout, '
            'shrunk to fit. Pinch to zoom in.</p>')
FIT_JS = """
(function () {
  var root = document.documentElement;
  function fit() {
    var w = window.innerWidth / (parseFloat(root.style.zoom) || 1);
    if (w < 1024) { root.classList.add("is-fit"); root.style.zoom = String(w / 1280); root.style.setProperty("--fit-inv", String(1280 / w)); }
    else { root.classList.remove("is-fit"); root.style.zoom = ""; root.style.removeProperty("--fit-inv"); }
  }
  function refit() { root.style.zoom = ""; fit(); }
  fit(); window.addEventListener("resize", refit); window.addEventListener("load", refit);
})();
"""

page = (title.replace(re.sub(r"</?title>", "", title), "ShelfSync Mockup") + "\n"
        + "<style>\n" + "\n".join(styles) + FIT_CSS + "</style>\n"
        + sprite + "\n" + FIT_NOTE + "\n" + body + "\n<script>\n" + FIT_JS + js + "\n</script>\n")
assert "data-logo/" not in page, "a logo reference was not inlined"
out.write_text(page, encoding="utf-8")
print(out, len(page.encode()) // 1024, "KB")
