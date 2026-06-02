"""Stylesheet for the minihtml markdown preview.

Import-safe outside Sublime Text: nothing here imports `sublime` at module
load time. `theme_colors()` is the only Sublime-aware helper and it is only
ever called from the plugin commands, never from `renderer` at import time.
"""

# Sensible light-theme defaults, used when running outside Sublime (tests) or
# when theme colors can't be resolved.
DEFAULT_COLORS = {
    "background": "#ffffff",
    "foreground": "#24292e",
    "accent": "#0969da",
    "code_background": "#f6f8fa",
    "border": "#d0d7de",
    "quote": "#57606a",
}

# %(...)s placeholders are filled via `_STYLESHEET % colors`. Using percent
# formatting (not str.format) keeps the literal CSS braces untouched.
_STYLESHEET = """
body#markdown-preview {
    background-color: %(background)s;
    color: %(foreground)s;
    font-size: 1rem;
    margin: 0;
    padding: 0;
}
.content { padding: 14px 20px; }
h1, h2, h3, h4, h5, h6 {
    color: %(foreground)s;
    font-weight: bold;
    margin: 18px 0 8px 0;
}
h1 { font-size: 1.8rem; border-bottom: 1px solid %(border)s; padding-bottom: 3px; }
h2 { font-size: 1.5rem; border-bottom: 1px solid %(border)s; padding-bottom: 3px; }
h3 { font-size: 1.25rem; }
h4 { font-size: 1.1rem; }
p { line-height: 1.5; margin: 8px 0; }
a { color: %(accent)s; text-decoration: none; }
strong, b { font-weight: bold; }
em, i { font-style: italic; }
code {
    background-color: %(code_background)s;
    padding: 1px 4px;
    border-radius: 3px;
    font-family: monospace;
}
.code-block, .table-block {
    background-color: %(code_background)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
    padding: 8px 12px;
    margin: 10px 0;
    font-family: monospace;
    font-size: 0.9rem;
    line-height: 1.4;
}
.md-quote {
    border-left: 3px solid %(border)s;
    color: %(quote)s;
    margin: 10px 0;
    padding: 2px 0 2px 12px;
}
/* padding-left (not margin) keeps the bullet inside the list box so it doesn't
   hang to the left of the body text; 22px matches .md-ol's indent. */
ul { margin: 6px 0; padding-left: 22px; }
li { line-height: 1.5; margin: 2px 0; }
.md-ol { margin: 6px 0 6px 22px; padding: 0; }
.md-li { margin: 2px 0; line-height: 1.5; }
.li-num { color: %(quote)s; font-weight: bold; }
.task-item { margin: 2px 0; line-height: 1.5; }
.checkbox { font-family: monospace; }
hr { border: none; border-top: 1px solid %(border)s; margin: 16px 0; }
img { }
"""


def build_stylesheet(colors):
    """Return the CSS string with the given color map applied."""
    merged = dict(DEFAULT_COLORS, **(colors or {}))
    return _STYLESHEET % merged


def theme_colors(view):
    """Derive preview colors from the active color scheme.

    Sublime-only: call from a plugin command, not from module import. Returns a
    partial color map (missing keys fall back to DEFAULT_COLORS in
    build_stylesheet). Code background / border / quote are mixed from the
    theme's background and foreground so the preview reads well on both light
    and dark schemes.
    """
    try:
        style = view.style()
    except Exception:
        return {}

    bg = _normalize(style.get("background"))
    fg = _normalize(style.get("foreground"))
    if not bg or not fg:
        return {}

    accent = (
        _normalize(style.get("accent"))
        or _normalize(style.get("bluish"))
        or _normalize(style.get("function"))
        or fg
    )
    return {
        "background": bg,
        "foreground": fg,
        "accent": accent,
        "code_background": _mix(bg, fg, 0.06),
        "border": _mix(bg, fg, 0.20),
        "quote": _mix(bg, fg, 0.45),
    }


def _normalize(value):
    """Coerce a Sublime color (e.g. '#272822FF' or '#abc') to '#rrggbb'."""
    if not value or not isinstance(value, str) or not value.startswith("#"):
        return None
    h = value[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) >= 6:
        return "#" + h[:6].lower()
    return None


def _mix(a, b, t):
    """Blend hex color `a` toward `b` by fraction `t` (0..1)."""
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return "#{0:02x}{1:02x}{2:02x}".format(r, g, bl)


def _rgb(hexcolor):
    h = hexcolor.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
