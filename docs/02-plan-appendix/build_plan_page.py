# Builds the published plan page (P3.6) from plan-page.src.html: inlines the Patina tokens,
# the two brand fonts and the logo, so the artifact needs no other files.
# Usage (from the project root): python -I docs/02-plan-appendix/build_plan_page.py <out_file>
import base64, sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
here = Path(__file__).resolve().parent
mock = root / "docs/05-design-system-appendix/mockup"

def data(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()

tokens = (root / "brand/generated/tokens.css").read_text(encoding="utf-8")
fonts = "\n".join([
    f'@font-face {{ font-family: "Archivo"; src: url("{data(mock / "fonts/archivo-latin-wdth-normal.woff2", "font/woff2")}") format("woff2"); font-weight: 100 900; font-stretch: 62% 125%; font-display: swap; }}',
    f'@font-face {{ font-family: "IBM Plex Mono"; src: url("{data(mock / "fonts/ibm-plex-mono-latin-400-normal.woff2", "font/woff2")}") format("woff2"); font-weight: 400; font-display: swap; }}',
])
page = (here / "plan-page.src.html").read_text(encoding="utf-8")
page = (page.replace("/*@@TOKENS@@*/", tokens)
            .replace("/*@@FONTS@@*/", fonts)
            .replace("@@LOGO_COLOR@@", data(root / "brand/assets/logo/logo-endorsed-color.svg", "image/svg+xml"))
            .replace("@@LOGO_DARK@@", data(root / "brand/assets/logo/logo-endorsed-dark.svg", "image/svg+xml")))
assert "@@" not in page
Path(sys.argv[1]).write_text(page, encoding="utf-8")
print(sys.argv[1], len(page.encode()) // 1024, "KB")
