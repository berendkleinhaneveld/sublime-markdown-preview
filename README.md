# Markdown Preview (in-editor) for Sublime Text 4

Preview Markdown **inside** Sublime Text — no browser, no local server, no
external dependencies. The current file is rendered into a Sublime HTML sheet
(a tab) using Sublime's built-in [minihtml] engine, and refreshes live as you
type (debounced) and on save.

> Requires **Sublime Text 4** (uses `window.new_html_sheet`, Python 3.8 host).

## Usage

- Open a `.md` file.
- Command Palette → **Markdown Preview: Open / Refresh** (or `⌘K ⌘M`, or
  **Tools → Markdown Preview**).
- A `Preview: <file>` tab opens in the adjacent group and updates as you edit.
- Run the command again to refresh / focus the existing preview (it reuses the
  same sheet rather than opening duplicates).

## Install (development)

Sublime import namespaces can't contain hyphens, so this repo must be installed
under a **hyphen-free folder name**. Symlink it into your Packages directory:

```sh
ln -s "$PWD" \
  "$HOME/Library/Application Support/Sublime Text/Packages/MarkdownPreviewInline"
```

Then restart Sublime Text. (`Preferences → Browse Packages…` opens that folder.)

## Limitations

These all come from minihtml being a limited subset of HTML/CSS — the plugin
works around them as best it can:

- **Tables** aren't supported by minihtml, so they're rendered as a
  monospaced, column-aligned text block.
- **Ordered lists** render as bullets in minihtml, so the plugin injects
  explicit `1.`, `2.` … number prefixes.
- **Code blocks** have no syntax highlighting (rendered in a monospaced box;
  whitespace preserved).
- No JavaScript, forms, flexbox/grid, transforms, or media queries.
- **Images**: PNG/JPG/GIF only; relative paths are resolved to absolute
  `file://` URLs.

If you need full fidelity (real tables, syntax highlighting), a browser-based
preview such as [MarkdownPreview] is the better fit — but that renders outside
the editor.

## Layout

| File                      | Purpose                                                        |
|---------------------------|----------------------------------------------------------------|
| `preview.py`              | Commands + event listener; manages the per-file preview sheet. |
| `renderer.py`             | Markdown → minihtml. Sublime-free, unit-testable with python3. |
| `styles.py`               | minihtml stylesheet; derives colors from the active theme.     |
| `markdown2.py`            | Vendored MIT markdown parser (no `pip` in the plugin host).    |
| `*.sublime-commands/menu/keymap` | Command palette, Tools menu, and keybinding.            |

### Testing the renderer without Sublime

```sh
python3 -c "from renderer import markdown_to_minihtml; \
print(markdown_to_minihtml(open('sample.md').read(), '.'))"
```

## Roadmap

- Live split-pane phantom preview (`MarkdownLivePreviewCommand` is stubbed; the
  renderer is already shared so it slots in without refactoring).
- Code syntax highlighting.
- Scroll sync between source and preview.

[minihtml]: https://www.sublimetext.com/docs/minihtml.html
[MarkdownPreview]: https://packagecontrol.io/packages/MarkdownPreview
