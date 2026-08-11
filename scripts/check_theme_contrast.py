"""Verify every theme in musicgrab/web/themes.js meets WCAG AA contrast.

Checks text/textMuted against bg (>=4.5:1) and onAccent against accent
(>=3:1, the AA-large threshold, since onAccent is only used on large/bold
button text). Run with: python scripts/check_theme_contrast.py
"""

import json
import re
import sys
from pathlib import Path


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def srgb_to_linear(c):
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color):
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(hex1, hex2):
    l1, l2 = relative_luminance(hex1), relative_luminance(hex2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def load_themes():
    # Evaluate the real ES module with Node rather than regex-parsing JS —
    # far more robust than trying to hand-roll a JS-object-literal parser.
    import subprocess

    src = Path(__file__).parent.parent / "musicgrab" / "web" / "themes.js"
    script = (
        f"import('{src.as_uri()}').then(m => console.log(JSON.stringify(m.THEMES)))"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def main():
    themes = load_themes()
    fails = []
    for t in themes:
        checks = {
            "text/bg": (contrast(t["text"], t["bg"]), 4.5),
            "textMuted/bg": (contrast(t["textMuted"], t["bg"]), 4.5),
            "onAccent/accent": (contrast(t["onAccent"], t["accent"]), 3.0),
        }
        for label, (ratio, minimum) in checks.items():
            if ratio < minimum:
                fails.append((t["id"], label, round(ratio, 2), minimum))

    if fails:
        for f in fails:
            print(f"FAIL {f[0]}: {f[1]} = {f[2]} (need >= {f[3]})")
        sys.exit(1)

    print(f"All {len(themes)} themes pass WCAG AA contrast.")


if __name__ == "__main__":
    main()
