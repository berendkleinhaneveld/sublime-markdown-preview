import html
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from sublime_stub import PreviewTestCase

from renderer import markdown_to_minihtml


class LinkRenderingTests(unittest.TestCase):
    def target(self, source, base_dir):
        document = markdown_to_minihtml(source, base_dir)
        href = document.split('href="', 1)[1].split('"', 1)[0]
        command, args = html.unescape(href).split(' ', 1)
        self.assertEqual(command, 'subl:markdown_preview_open_link')
        return json.loads(args)['path']

    def test_relative_encoded_path_and_fragment(self):
        self.assertEqual(
            self.target('[next](../guide/My%20Notes.md#intro)', '/project/docs'),
            '/project/guide/My Notes.md',
        )

    def test_file_url_and_special_characters(self):
        self.assertEqual(
            self.target('[next](file:///project/a%22b%26c.md)', '/elsewhere'),
            '/project/a"b&c.md',
        )

    def test_raw_html_single_quoted_link(self):
        self.assertEqual(
            self.target("<a href='notes.txt'>notes</a>", '/project'),
            '/project/notes.txt',
        )

    def test_external_urls_and_anchors_are_preserved(self):
        for href in ('https://example.com', 'mailto:a@example.com', '#heading',
                     '//example.com/file.md'):
            with self.subTest(href=href):
                document = markdown_to_minihtml('[link]({})'.format(href))
                self.assertIn('href="{}"'.format(href), document)

    def test_reference_link_forms(self):
        for label in ('[Guide]', '[Guide][]', '[Guide][guide]'):
            with self.subTest(label=label):
                document = markdown_to_minihtml(
                    label + '\n\n[guide]: https://example.com "Help"\n'
                )
                self.assertIn(
                    '<a href="https://example.com" title="Help">Guide</a>', document
                )

    def test_shortcut_local_link(self):
        self.assertEqual(
            self.target('[Guide]\n\n[guide]: next.md\n', '/project'),
            '/project/next.md',
        )

    def test_reference_syntax_in_code_and_escaped_text_is_literal(self):
        document = markdown_to_minihtml(
            '`[guide]` and \\[guide] and [undefined]\n\n'
            '```\n[guide]\n```\n\n[guide]: https://example.com\n'
        )
        self.assertNotIn('<a ', document)
        self.assertIn('<code>[guide]</code>', document)
        self.assertIn('[undefined]', document)

    def test_explicit_reference_and_inline_link_take_precedence(self):
        document = markdown_to_minihtml(
            '[guide][missing]\n\n[guide](https://other.example)\n\n'
            '[guide]: https://example.com\n'
        )
        self.assertIn('[guide][missing]', document)
        self.assertIn('<a href="https://other.example">guide</a>', document)
        self.assertNotIn('href="https://example.com"', document)

    def test_shortcut_image(self):
        document = markdown_to_minihtml(
            '![logo]\n\n[logo]: images/logo.png "Logo"\n', '/project'
        )
        self.assertIn('src="file:///project/images/logo.png"', document)
        self.assertIn('alt="logo" title="Logo"', document)

    def test_readme_reference_links(self):
        readme = Path(__file__).resolve().parents[1] / 'README.md'
        document = markdown_to_minihtml(readme.read_text())
        self.assertIn(
            '<a href="https://www.sublimetext.com/docs/minihtml.html">minihtml</a>',
            document,
        )
        self.assertIn(
            '<a href="https://packagecontrol.io/packages/MarkdownPreview">'
            'MarkdownPreview</a>', document,
        )


class LinkCommandTests(PreviewTestCase):
    def setUp(self):
        super().setUp()
        self.command = self.preview.MarkdownPreviewOpenLinkCommand()
        self.command.window = Mock()
        self.command.window.active_group.return_value = 1
        self.view = self.command.window.open_file.return_value
        self.view.is_loading.return_value = False
        self.view.syntax.return_value = None
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def file(self, name):
        path = Path(self.directory.name) / name
        path.write_text('content')
        self.view.file_name.return_value = str(path)
        return str(path)

    def test_markdown_opens_focused_preview_after_loading(self):
        path = self.file('next.MD')
        self.view.is_loading.return_value = True
        self.command.run(path)
        self.view.run_command.assert_not_called()
        callback, delay = self.sublime.set_timeout.call_args.args
        self.assertEqual(delay, 50)
        self.view.is_loading.return_value = False
        callback()
        self.view.run_command.assert_called_once_with(
            'markdown_preview', {'group': 1, 'focus_preview': True}
        )

    def test_other_file_opens_source(self):
        path = self.file('source.py')
        self.command.run(path)
        self.command.window.open_file.assert_called_once_with(path)
        self.view.run_command.assert_not_called()

    def test_missing_file_does_not_create_buffer(self):
        self.command.run(str(Path(self.directory.name) / 'missing.md'))
        self.command.window.open_file.assert_not_called()
        self.sublime.status_message.assert_called_once()

    def test_closed_view_stops_loading_callback(self):
        self.view.is_valid.return_value = False
        self.command.run(self.file('closed.md'))
        self.sublime.set_timeout.assert_not_called()
        self.view.run_command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
