"""Render launcher/icon.svg to the PNG sizes macOS needs (AppIcon.iconset) plus tools/ui/icon.png.

Usage: .venv/bin/python launcher/render_icon.py   (called by launcher/build.sh)
Uses the Playwright already in .venv, so there is nothing to install.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SET = HERE / "build" / "AppIcon.iconset"
SIZES = {16: ["icon_16x16"], 32: ["icon_16x16@2x", "icon_32x32"], 64: ["icon_32x32@2x"],
         128: ["icon_128x128"], 256: ["icon_128x128@2x", "icon_256x256"],
         512: ["icon_256x256@2x", "icon_512x512"], 1024: ["icon_512x512@2x"]}


def main():
    SET.mkdir(parents=True, exist_ok=True)
    svg = (HERE / "icon.svg").read_text()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page()
        for size, names in SIZES.items():
            page.set_viewport_size({"width": size, "height": size})
            page.set_content(f'<html><body style="margin:0;background:transparent">'
                             f'<div style="width:{size}px;height:{size}px">{svg.replace("<svg ", f"<svg width=\"{size}\" height=\"{size}\" ", 1)}</div></body></html>')
            page.wait_for_timeout(150)
            for name in names:
                page.screenshot(path=str(SET / f"{name}.png"), omit_background=True)
        browser.close()
    (HERE.parent / "tools" / "ui" / "icon.png").write_bytes((SET / "icon_128x128@2x.png").read_bytes())
    print(f"rendered {sum(len(n) for n in SIZES.values())} PNGs into {SET}")


if __name__ == "__main__":
    main()
