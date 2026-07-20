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
  * no <blockquote>     -> rewritten to <div class="md-quote"> so text renders
  * no line-through     -> strikethrough applied via combining char U+0336
  * no <input>          -> task-list checkboxes become a glyph; the item is
                           rendered as a bulletless <div> (no list-style in css)
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
    r"<pre\b([^>]*)>\s*<code\b[^>]*>(.*?)</code>\s*</pre>", re.IGNORECASE | re.DOTALL
)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.IGNORECASE | re.DOTALL)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_BLOCKQUOTE_OPEN_RE = re.compile(r"<blockquote\b[^>]*>", re.IGNORECASE)
_BLOCKQUOTE_CLOSE_RE = re.compile(r"</blockquote>", re.IGNORECASE)
_STRIKE_RE = re.compile(r"<(s|del|strike)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_COMBINING_STRIKE = "̶"  # combining long stroke overlay
_CHECKBOX_RE = re.compile(r"<input\b[^>]*task-list-item-checkbox[^>]*>", re.IGNORECASE)
_CHECKED = "☑"  # ballot box with check (U+2611)
_UNCHECKED = "☐"  # ballot box (U+2610)
# Absolute URL (has a scheme) or protocol-relative.
_ABS_URL_RE = re.compile(r"^(?:[a-z][a-z0-9+.\-]*:|//)", re.IGNORECASE)


def markdown_to_minihtml(text, base_dir=".", colors=None):
    """Render markdown `text` to a complete minihtml document string."""
    html = markdown2.markdown(text, extras=MARKDOWN_EXTRAS)
    html = _convert_code_blocks(html)
    html = _convert_tables(html)
    html = _convert_blockquotes(html)
    html = _strikethrough(html)
    html = _convert_task_lists(html)
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
    """Render code blocks as monospaced <div>s.

    Fenced blocks (tagged ``data-md-fenced`` by the markdown2 patch) get a
    stable ``id="md-code-N"`` (document order) so the Sublime side (preview.py)
    can replace each with syntax-highlighted output from ``View.export_to_html``.
    Indented code blocks have no language, so they're emitted as a bare
    ``code-block`` div with no id and are never highlighted -- keeping the
    id/fence counts aligned so a stray indented block doesn't disable
    highlighting for the whole document. The monospaced text is also the fallback
    shown when highlighting isn't available (no Sublime, or counts don't line up).
    """
    counter = [0]

    def repl(match):
        is_fenced = "data-md-fenced" in match.group(1)
        code = match.group(2).strip("\n")
        if not is_fenced:
            return '<div class="code-block">{0}</div>'.format(_preformat(code))
        index = counter[0]
        counter[0] += 1
        return '<div class="code-block" id="md-code-{0}">{1}</div>'.format(
            index, _preformat(code)
        )

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
        # table-block (not code-block) so the highlighter doesn't treat the
        # monospaced table fallback as a code block to syntax-highlight.
        return '<div class="table-block">{0}</div>'.format(_preformat(escaped))

    return _TABLE_RE.sub(repl, html)


def _strip(cell):
    """Return a cell's plain text (tags removed, entities decoded)."""
    return _html.unescape(_STRIP_TAGS_RE.sub("", cell)).strip()


def _convert_blockquotes(html):
    """Rewrite unsupported <blockquote> to a styled <div> so its text renders."""
    html = _BLOCKQUOTE_OPEN_RE.sub('<div class="md-quote">', html)
    return _BLOCKQUOTE_CLOSE_RE.sub("</div>", html)


def _strikethrough(html):
    """Render <s>/<del>/<strike> with a combining strike (minihtml lacks
    text-decoration: line-through). The overlay char is inserted after each
    visible character; tags and entities inside are preserved."""

    def repl(match):
        out = []
        for part in _TAG_RE.split(match.group(2)):
            if part.startswith("<") and part.endswith(">"):
                out.append(part)  # keep nested inline tags as-is
            else:
                text = _html.unescape(part)
                struck = "".join(ch + _COMBINING_STRIKE for ch in text)
                out.append(_html.escape(struck))
        return '<span class="md-strike">{0}</span>'.format("".join(out))

    return _STRIKE_RE.sub(repl, html)


def _convert_task_lists(html):
    """Render `- [ ]` / `- [x]` items as checkboxes.

    markdown2's task_list extra emits <input type="checkbox">, which minihtml
    drops. Replace each checkbox input with a glyph and turn its <li> into a
    bulletless <div class="task-item"> (minihtml has no list-style to hide the
    bullet). A stack matches each <li> to its </li> so nested lists are handled;
    non-task <li>s (including ordinary items in a mixed list) are left as-is.
    """
    if "task-list-item-checkbox" not in html:
        return html

    tokens = _TAG_RE.split(html)
    out = []
    li_is_task = []  # one bool per currently-open <li>
    i = 0
    while i < len(tokens):
        token = tokens[i]
        low = token.lower()
        if low.startswith("<li"):
            is_task = _next_child_is_checkbox(tokens, i)
            li_is_task.append(is_task)
            out.append('<div class="task-item">' if is_task else token)
        elif low.startswith("</li"):
            is_task = li_is_task.pop() if li_is_task else False
            out.append("</div>" if is_task else token)
        elif _CHECKBOX_RE.match(token):
            checked = "checked" in low
            out.append(
                '<span class="checkbox">{0}</span>'.format(
                    _CHECKED if checked else _UNCHECKED
                )
            )
        else:
            out.append(token)
        i += 1
    return "".join(out)


def _next_child_is_checkbox(tokens, li_index):
    """True if the first non-empty token after an <li> is a checkbox <input>."""
    for token in tokens[li_index + 1 :]:
        if token.strip() == "":
            continue
        return bool(_CHECKBOX_RE.match(token))
    return False


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
