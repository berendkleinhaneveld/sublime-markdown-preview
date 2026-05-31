"""Sublime Text 4 in-editor markdown preview.

Renders the current markdown file into a minihtml HTML sheet (a tab), refreshing
live as you type (debounced) and on save. One preview sheet is kept per source
view, so re-running the command updates that sheet rather than opening a new one.

A live split-pane phantom mode is planned (see MarkdownLivePreviewCommand). The
markdown -> minihtml conversion lives in `renderer.py` and is reused by both
modes, so adding the phantom surface won't touch the renderer.
"""

import os

import sublime
import sublime_plugin

from .renderer import markdown_to_minihtml
from .styles import theme_colors

# source view id -> preview HtmlSheet id
_previews = {}
# source view id -> debounce token (latest edit wins)
_pending = {}

_MD_EXTENSIONS = (".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn")
_DEBOUNCE_MS = 400


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
    return markdown_to_minihtml(text, base_dir, colors=theme_colors(view))


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


def _refresh(view):
    window = view.window() or sublime.active_window()
    if window is None:
        return
    sheet = _find_sheet(window, view)
    if sheet is not None:
        sheet.set_contents(_render(view))


class MarkdownPreviewCommand(sublime_plugin.TextCommand):
    """Open the preview sheet for the current file, or refresh it if already open."""

    def run(self, edit):
        window = self.view.window()
        if window is None:
            return
        sheet = _find_sheet(window, self.view)
        if sheet is not None:
            sheet.set_contents(_render(self.view))
            window.focus_sheet(sheet)
            return
        # Open in the adjacent group when the window is split, else the current one.
        group = window.active_group()
        if window.num_groups() > 1:
            group = (group + 1) % window.num_groups()
        sheet = window.new_html_sheet(
            _title(self.view), _render(self.view), group=group
        )
        _previews[self.view.id()] = sheet.id()
        window.focus_view(self.view)

    def is_enabled(self):
        return _is_markdown(self.view)

    is_visible = is_enabled


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
