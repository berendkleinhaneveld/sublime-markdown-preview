"""Convert Markdown into Sublime Text minihtml.

Import-safe outside Sublime Text: this module must never import `sublime`, so
it can be unit-tested with plain `python3` (see the verification step in the
plan). The plugin (`preview.py`) supplies theme colors; standalone callers get
the light defaults from `styles.DEFAULT_COLORS`.

minihtml is a limited subset of HTML/CSS. The transforms below work around the
relevant gaps:
  * no <pre>            -> fenced code becomes a <div class="code-block">
  * <ol> shows bullets  -> ordered lists get explicit "1." number prefixes
  * no <table>          -> tables become a monospaced, column-aligned block
  * image src must be   -> relative <img> sources are rewritten to absolute
    file://, res:// ...     file:// URLs
"""

import html as _html
import os
import re

try:  # packaged inside Sublime (folder must be hyphen-free for this to work)
    from . import markdown2
    from .styles import build_stylesheet, DEFAULT_COLORS
except (ImportError, ValueError):  # run as a plain script for unit testing
    import markdown2
    from styles import build_stylesheet, DEFAULT_COLORS

MARKDOWN_EXTRAS = [
    "fenced-code-blocks",
    "tables",
    "cuddled-lists",
    "strike",
    "code-friendly",
    "footnotes",
    "task_list",
]

_TAG_RE = re.compile(r"(<[^>]+>)")
_IMG_RE = re.compile(r'<img\b([^>]*?)\bsrc="([^"]*)"([^>]*)>', re.IGNORECASE)
_TABLE_RE = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
_CODEBLOCK_RE = re.compile(
    r"<pre\b[^>]*>\s*<code\b[^>]*>(.*?)</code>\s*</pre>", re.IGNORECASE | re.DOTALL
)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.IGNORECASE | re.DOTALL)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
# Absolute URL (has a scheme) or protocol-relative.
_ABS_URL_RE = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:|//)", re.IGNORECASE)


def markdown_to_minihtml(text, base_dir=".", colors=None):
    """Render markdown `text` to a complete minihtml document string."""
    html = markdown2.markdown(text, extras=MARKDOWN_EXTRAS)
    html = _convert_code_blocks(html)
    html = _convert_tables(html)
    html = _number_ordered_lists(html)
    html = _absolutize_images(html, base_dir)
    stylesheet = build_stylesheet(dict(DEFAULT_COLORS, **(colors or {})))
    return (
        '<body id="markdown-preview">\n'
        "<style>{css}</style>\n"
        '<div class="content">\n{body}\n</div>\n'
        "</body>"
    ).format(css=stylesheet, body=html)


def _preformat(text):
    """Make already-escaped text render verbatim in minihtml.

    minihtml collapses whitespace, so replace spaces/tabs/newlines with markup
    that survives. Input is expected to be HTML-escaped already.
    """
    text = text.replace("\t", "    ")
    text = text.replace(" ", "&nbsp;")
    text = text.replace("\n", "<br>\n")
    return text


def _convert_code_blocks(html):
    def repl(match):
        code = match.group(1).strip("\n")
        return '<div class="code-block">{0}</div>'.format(_preformat(code))

    return _CODEBLOCK_RE.sub(repl, html)


def _convert_tables(html):
    def repl(match):
        block = match.group(0)
        rows = []
        for row in _ROW_RE.finditer(block):
            cells = [_strip(c) for c in _CELL_RE.findall(row.group(1))]
            if cells:
                rows.append(cells)
        if not rows:
            return block
        ncols = max(len(r) for r in rows)
        rows = [r + [""] * (ncols - len(r)) for r in rows]
        widths = [max(len(r[i]) for r in rows) for i in range(ncols)]
        lines = []
        for i, row in enumerate(rows):
            lines.append(" | ".join(row[c].ljust(widths[c]) for c in range(ncols)))
            if i == 0:
                lines.append("-+-".join("-" * widths[c] for c in range(ncols)))
        escaped = _html.escape("\n".join(lines))
        return '<div class="code-block">{0}</div>'.format(_preformat(escaped))

    return _TABLE_RE.sub(repl, html)


def _strip(cell):
    """Return a cell's plain text (tags removed, entities decoded)."""
    return _html.unescape(_STRIP_TAGS_RE.sub("", cell)).strip()


def _number_ordered_lists(html):
    """Give ordered-list items explicit numbers.

    minihtml renders <ol> the same as <ul> (a bullet, no number). Rewrite
    ordered lists to <div>s with a number span so they read correctly, while
    leaving unordered lists as native <ul>/<li>. A stack keeps per-level
    counters so nested lists number independently.
    """
    out = []
    stack = []  # entries: ["ol", count] or ["ul"]
    for token in _TAG_RE.split(html):
        low = token.lower()
        if low.startswith("<ol"):
            stack.append(["ol", 0])
            out.append('<div class="md-ol">')
        elif low.startswith("<ul"):
            stack.append(["ul"])
            out.append(token)
        elif low.startswith("</ol"):
            if stack:
                stack.pop()
            out.append("</div>")
        elif low.startswith("</ul"):
            if stack:
                stack.pop()
            out.append(token)
        elif low.startswith("<li"):
            if stack and stack[-1][0] == "ol":
                stack[-1][1] += 1
                out.append(
                    '<div class="md-li"><span class="li-num">{0}.</span> '.format(
                        stack[-1][1]
                    )
                )
            else:
                out.append(token)
        elif low.startswith("</li"):
            if stack and stack[-1][0] == "ol":
                out.append("</div>")
            else:
                out.append(token)
        else:
            out.append(token)
    return "".join(out)


def _absolutize_images(html, base_dir):
    base_dir = os.path.abspath(base_dir)

    def repl(match):
        pre, src, post = match.group(1), match.group(2), match.group(3)
        if not _ABS_URL_RE.match(src):
            path = (
                src
                if os.path.isabs(src)
                else os.path.normpath(os.path.join(base_dir, src))
            )
            src = "file://" + path
        return '<img{0}src="{1}"{2}>'.format(pre, src, post)

    return _IMG_RE.sub(repl, html)
