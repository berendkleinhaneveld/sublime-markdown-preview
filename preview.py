"""Sublime Text 4 in-editor markdown preview.

Renders the current markdown file into a minihtml HTML sheet (a tab), refreshing
live as you type (debounced) and on save. One preview sheet is kept per source
view, so re-running the command updates that sheet rather than opening a new one.

A live split-pane phantom mode is planned (see MarkdownLivePreviewCommand). The
markdown -> minihtml conversion lives in `renderer.py` and is reused by both
modes, so adding the phantom surface won't touch the renderer.
"""

import os
import re

import sublime
import sublime_plugin

from .renderer import markdown_to_minihtml
from .styles import theme_colors

# A code block emitted by renderer._convert_code_blocks, including its id.
_CODE_DIV_RE = re.compile(
    r'<div class="code-block" id="md-code-\d+">.*?</div>', re.DOTALL
)
# Opening/closing fence: a run of >=3 backticks or tildes, any indentation.
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
# Background declarations in export_to_html output, dropped so the code box uses
# our single .code-block background instead of doubling it with the editor's.
_BACKGROUND_RE = re.compile(r"background(-color)?\s*:\s*[^;\"']+;?", re.IGNORECASE)

# source view id -> preview HtmlSheet id
_previews = {}
# source view id -> debounce token (latest edit wins)
_pending = {}

_MD_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn")
_DEBOUNCE_MS = 400

_SETTINGS_FILE = "MarkdownPreview.sublime-settings"


def _settings():
    return sublime.load_settings(_SETTINGS_FILE)


def _is_markdown(view):
    if view is None:
        return False
    syntax = view.syntax()
    if syntax and "markdown" in syntax.scope.lower():
        return True
    name = view.file_name() or ""
    return name.lower().endswith(_MD_EXTENSIONS)


def _render(view):
    text = view.substr(sublime.Region(0, view.size()))
    fname = view.file_name()
    base_dir = os.path.dirname(fname) if fname else "."
    html = markdown_to_minihtml(
        text, base_dir, colors=theme_colors(view),
        editor_font=view.settings().get("font_face"),
    )
    return _highlight_code_blocks(view, text, html)


def _fenced_code_regions(view, text):
    """Buffer regions for the *contents* of fenced code blocks, in order.

    Computed from the text (not a scope selector) so it's independent of which
    Markdown syntax package is installed. The actual colors come later from
    export_to_html, which reads whatever grammar Sublime injected into the fence.
    """
    regions = []
    offset = 0
    open_fence = None  # (marker_char, marker_len, content_start_offset)
    for line in text.splitlines(keepends=True):
        match = _FENCE_RE.match(line)
        if open_fence is None:
            if match:
                marker = match.group(1)
                open_fence = (marker[0], len(marker), offset + len(line))
        elif (
            match
            and match.group(1)[0] == open_fence[0]
            and len(match.group(1)) >= open_fence[1]
        ):
            start = open_fence[2]
            if offset > start:
                regions.append(sublime.Region(start, offset))
            else:
                regions.append(sublime.Region(start, start))  # empty block
            open_fence = None
        offset += len(line)
    return regions


def _highlight_code_blocks(view, text, html):
    """Replace plain code-block fallbacks with Sublime-highlighted minihtml.

    Maps the Nth code-block div to the Nth fenced region. If the counts don't
    match (e.g. indented code blocks are present, or an unclosed fence) or the
    export fails, the plain monospaced fallback is left untouched.
    """
    n_blocks = len(_CODE_DIV_RE.findall(html))
    if n_blocks == 0:
        return html
    regions = _fenced_code_regions(view, text)
    if len(regions) != n_blocks:
        return html

    fragments = []
    for region in regions:
        try:
            fragment = view.export_to_html(regions=[region], minihtml=True)
        except Exception as error:
            print("MarkdownPreview: export_to_html failed:", error)
            return html
        fragments.append(_BACKGROUND_RE.sub("", fragment))

    pieces = iter(fragments)
    return _CODE_DIV_RE.sub(
        lambda _m: '<div class="code-block">{0}</div>'.format(next(pieces)), html
    )


def _title(view):
    name = view.file_name()
    base = os.path.basename(name) if name else (view.name() or "untitled")
    return "Preview: " + base


def _find_sheet(window, view):
    """Return the live preview sheet for `view`, or None (clearing stale state)."""
    sheet_id = _previews.get(view.id())
    if sheet_id is None:
        return None
    for sheet in window.sheets():
        if sheet.id() == sheet_id and isinstance(sheet, sublime.HtmlSheet):
            return sheet
    _previews.pop(view.id(), None)
    return None


def _side_group(window):
    """Group to host the preview when opening it to the side.

    Reuses the group next to the active one; if the window has a single group,
    it's first split into two columns so there is a group to put the preview in.
    """
    active = window.active_group()
    num = window.num_groups()
    if num == 1:
        try:
            fraction = float(_settings().get("preview_width", 0.5))
        except (TypeError, ValueError):
            fraction = 0.5
        fraction = min(max(fraction, 0.1), 0.9)
        window.set_layout(
            {
                "cols": [0.0, 1.0 - fraction, 1.0],
                "rows": [0.0, 1.0],
                "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
            }
        )
        return 1
    # Prefer the group to the right; fall back to the left when already rightmost
    # so a 3+ group layout reuses a truly adjacent group rather than wrapping.
    return active + 1 if active + 1 < num else active - 1


def _refresh(view):
    window = view.window() or sublime.active_window()
    if window is None:
        return
    sheet = _find_sheet(window, view)
    if sheet is not None:
        sheet.set_contents(_render(view))


class MarkdownPreviewCommand(sublime_plugin.TextCommand):
    """Open the preview sheet for the current file, or refresh it if already open."""

    def run(self, edit, group=None, focus_preview=False):
        window = self.view.window()
        if window is None:
            return
        sheet = _find_sheet(window, self.view)
        if sheet is not None:
            sheet.set_contents(_render(self.view))
            window.focus_sheet(sheet)
            return
        if group is None:
            if _settings().get("open_to_side", True):
                group = _side_group(window)
            else:
                group = window.active_group()
        sheet = window.new_html_sheet(
            _title(self.view), _render(self.view), group=group
        )
        _previews[self.view.id()] = sheet.id()
        if focus_preview:
            window.focus_sheet(sheet)
        else:
            window.focus_view(self.view)

    def is_enabled(self):
        return _is_markdown(self.view)

    is_visible = is_enabled


class MarkdownPreviewOpenLinkCommand(sublime_plugin.WindowCommand):
    """Open linked files, showing Markdown in a preview once it has loaded."""

    def run(self, path):
        if not os.path.isfile(path):
            sublime.status_message("MarkdownPreview: file not found: " + path)
            return
        group = self.window.active_group()
        view = self.window.open_file(path)

        def on_loaded():
            if not view.is_valid() or not self.window.is_valid():
                return
            if view.is_loading():
                sublime.set_timeout(on_loaded, 50)
                return
            if _is_markdown(view):
                view.run_command(
                    "markdown_preview", {"group": group, "focus_preview": True}
                )

        on_loaded()


class MarkdownLivePreviewCommand(sublime_plugin.TextCommand):
    """Planned: live split-pane preview using a read-only view + PhantomSet.

    Phase 2. The renderer and `_render()` are already shared, so this command
    will create the split, a scratch read-only view, and a PhantomSet, then feed
    it `_render(self.view)` on debounced `on_modified_async` — no renderer
    changes required. For now it points users at the working sheet command.
    """

    def run(self, edit):
        sublime.status_message(
            "Live split-pane preview is not implemented yet — use Markdown Preview."
        )
        self.view.run_command("markdown_preview")

    def is_enabled(self):
        return _is_markdown(self.view)

    is_visible = is_enabled


class MarkdownPreviewEvents(sublime_plugin.EventListener):
    def on_post_save_async(self, view):
        _refresh(view)

    def on_modified_async(self, view):
        vid = view.id()
        if vid not in _previews:
            return
        token = _pending.get(vid, 0) + 1
        _pending[vid] = token

        def go():
            if _pending.get(vid) == token:
                _refresh(view)

        sublime.set_timeout_async(go, _DEBOUNCE_MS)

    def on_close(self, view):
        _previews.pop(view.id(), None)
        _pending.pop(view.id(), None)
