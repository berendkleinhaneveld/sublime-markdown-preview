import html
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

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


class LinkCommandTests(unittest.TestCase):
    def setUp(self):
        self.sublime = types.ModuleType('sublime')
        self.sublime.status_message = Mock()
        self.sublime.set_timeout = Mock()
        plugin = types.ModuleType('sublime_plugin')
        plugin.TextCommand = plugin.WindowCommand = plugin.EventListener = object
        package = types.ModuleType('_preview_link_tests')
        package.__path__ = [str(Path(__file__).resolve().parents[1])]
        self.modules = patch.dict(sys.modules, {
            'sublime': self.sublime, 'sublime_plugin': plugin,
            '_preview_link_tests': package,
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.preview = importlib.import_module('_preview_link_tests.preview')
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
