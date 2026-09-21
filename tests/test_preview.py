from unittest.mock import Mock, patch

from renderer import markdown_to_minihtml
from sublime_stub import PreviewTestCase


class PreviewTests(PreviewTestCase):
    def setUp(self):
        super().setUp()
        self.view = Mock()
        self.view.id.return_value = 7
        self.view.file_name.return_value = '/project/notes.md'
        self.window = self.view.window.return_value
        self.window.sheets.return_value = []
        self.window.active_group.return_value = 0
        self.window.get_sheet_index.return_value = (0, 0)

    def test_markdown_detection_from_syntax_or_extension(self):
        self.assertFalse(self.preview._is_markdown(None))
        for name in ('notes.MD', 'notes.markdown', 'notes.mdown', 'notes.mkd',
                     'notes.mkdn', 'notes.mdwn'):
            self.view.syntax.return_value = None
            self.view.file_name.return_value = name
            self.assertTrue(self.preview._is_markdown(self.view))
        self.view.file_name.return_value = None
        self.view.syntax.return_value = Mock(scope='text.html.markdown')
        self.assertTrue(self.preview._is_markdown(self.view))
        self.view.syntax.return_value = Mock(scope='source.python')
        self.assertFalse(self.preview._is_markdown(self.view))

    def test_fences_require_matching_marker_and_sufficient_length(self):
        text = 'intro\n````python\na\n```\n~~~\nb\n````\n~~~\nc\n~~~'
        regions = self.preview._fenced_code_regions(self.view, text)
        self.assertEqual([text[a:b] for a, b in regions], ['a\n```\n~~~\nb\n', 'c\n'])

    def test_empty_and_unclosed_fences(self):
        text = '```\n```\n\n~~~\nunfinished'
        regions = self.preview._fenced_code_regions(self.view, text)
        self.assertEqual(regions, [(4, 4)])

    def test_highlighting_keeps_indented_code_and_tables(self):
        text = '    plain\n\n```\nfenced\n```\n\n| A |\n|---|\n| B |'
        document = markdown_to_minihtml(text)
        self.view.export_to_html.return_value = (
            '<span style="background-color: #000; color: #fff;">colored</span>'
        )
        result = self.preview._highlight_code_blocks(self.view, text, document)
        self.assertIn('<div class="code-block">plain</div>', result)
        self.assertIn('<span style=" color: #fff;">colored</span>', result)
        self.assertIn('<div class="table-block">', result)
        start = text.index('fenced')
        self.view.export_to_html.assert_called_once_with(
            regions=[(start, start + len('fenced\n'))], minihtml=True
        )

    def test_export_failure_preserves_all_fallback_blocks(self):
        text = '```\na\n```\n\n```\nb\n```'
        document = markdown_to_minihtml(text)
        self.view.export_to_html.side_effect = ['highlighted', RuntimeError('failed')]
        with patch('builtins.print'):
            self.assertEqual(self.preview._highlight_code_blocks(self.view, text, document), document)

    def test_fence_count_mismatch_skips_export(self):
        document = markdown_to_minihtml('```\na\n```')
        self.assertEqual(self.preview._highlight_code_blocks(self.view, '', document), document)
        self.view.export_to_html.assert_not_called()

    def test_stale_sheet_registration_is_removed(self):
        self.preview._previews[7] = 99
        self.assertIsNone(self.preview._find_sheet(self.window, self.view))
        self.assertNotIn(7, self.preview._previews)

    def test_existing_preview_is_refreshed_and_reused(self):
        sheet = Mock(spec=self.sublime.HtmlSheet)
        sheet.id = Mock(return_value=99)
        sheet.set_contents = Mock()
        self.window.sheets.return_value = [sheet]
        self.preview._previews[7] = 99
        command = self.preview.MarkdownPreviewCommand()
        command.view = self.view
        with patch.object(self.preview, '_render', return_value='updated'):
            command.run(None)
        sheet.set_contents.assert_called_once_with('updated')
        self.window.focus_sheet.assert_called_once_with(sheet)
        self.window.new_html_sheet.assert_not_called()

    def test_new_preview_focus_and_explicit_group(self):
        command = self.preview.MarkdownPreviewCommand()
        command.view = self.view
        with patch.object(self.preview, '_render', return_value='contents'):
            command.run(None, group=2, focus_preview=True)
        self.window.new_html_sheet.assert_called_once_with('Preview: notes.md', 'contents', group=2)
        sheet = self.window.new_html_sheet.return_value
        self.assertEqual(self.preview._previews[7], sheet.id())
        self.window.focus_sheet.assert_called_once_with(sheet)
        self.window.focus_view.assert_not_called()

    def test_side_group_reuses_neighbor_without_changing_layout(self):
        self.window.num_groups.return_value = 3
        for active, expected in ((0, 1), (1, 2), (2, 1)):
            self.window.active_group.return_value = active
            self.assertEqual(self.preview._side_group(self.window), expected)
        self.window.set_layout.assert_not_called()

    def test_split_width_defaults_and_bounds(self):
        self.window.num_groups.return_value = 1
        for width, divider in ((0.3, 0.7), (-1, 0.9), (2, 0.1), ('bad', 0.5), (None, 0.5)):
            with self.subTest(width=width):
                self.sublime.load_settings.return_value.get.return_value = width
                self.assertEqual(self.preview._side_group(self.window), 1)
                layout = self.window.set_layout.call_args.args[0]
                self.assertAlmostEqual(layout['cols'][1], divider)
                self.assertEqual(layout['cells'], [[0, 0, 1, 1], [1, 0, 2, 1]])

    def test_rapid_edits_only_refresh_latest_version(self):
        self.preview._previews[7] = 99
        events = self.preview.MarkdownPreviewEvents()
        events.on_modified_async(self.view)
        events.on_modified_async(self.view)
        callbacks = self.sublime.set_timeout_async.call_args_list
        self.assertEqual(len(callbacks), 2)
        with patch.object(self.preview, '_refresh') as refresh:
            callbacks[0].args[0]()
            refresh.assert_not_called()
            callbacks[1].args[0]()
            refresh.assert_called_once_with(self.view)

    def test_close_cancels_pending_refresh_and_clears_state(self):
        self.preview._previews[7] = 99
        events = self.preview.MarkdownPreviewEvents()
        events.on_modified_async(self.view)
        callback = self.sublime.set_timeout_async.call_args.args[0]
        events.on_close(self.view)
        with patch.object(self.preview, '_refresh') as refresh:
            callback()
            refresh.assert_not_called()
        self.assertNotIn(7, self.preview._previews)
        self.assertNotIn(7, self.preview._pending)

    def test_edits_without_preview_do_not_schedule_work(self):
        self.preview.MarkdownPreviewEvents().on_modified_async(self.view)
        self.sublime.set_timeout_async.assert_not_called()

    def test_save_refreshes_preview(self):
        with patch.object(self.preview, '_refresh') as refresh:
            self.preview.MarkdownPreviewEvents().on_post_save_async(self.view)
            refresh.assert_called_once_with(self.view)

    def test_default_command_opens_in_current_group_and_focuses_preview(self):
        command = self.preview.MarkdownPreviewCommand()
        command.view = self.view
        with patch.object(self.preview, '_render', return_value='contents'):
            command.run(None)
        self.window.new_html_sheet.assert_called_once_with('Preview: notes.md', 'contents', group=0)
        self.window.focus_sheet.assert_called_once_with(self.window.new_html_sheet.return_value)
        self.window.focus_view.assert_not_called()
        self.window.set_layout.assert_not_called()
        self.sublime.load_settings.assert_not_called()

    def test_side_command_creates_split_and_returns_focus_to_source(self):
        self.window.num_groups.return_value = 1
        self.sublime.load_settings.return_value.get.return_value = 0.5
        command = self.preview.MarkdownPreviewToSideCommand()
        command.view = self.view
        with patch.object(self.preview, '_render', return_value='contents'):
            command.run(None)
        self.window.new_html_sheet.assert_called_once_with('Preview: notes.md', 'contents', group=1)
        self.window.set_layout.assert_called_once()
        focus_calls = [call[0] for call in self.window.method_calls if call[0].startswith('focus_')]
        self.assertEqual(focus_calls, ['focus_sheet', 'focus_view'])
        self.window.focus_view.assert_called_once_with(self.view)

    def test_switching_commands_moves_existing_preview_and_preserves_focus_contract(self):
        sheet = Mock(spec=self.sublime.HtmlSheet)
        sheet.id = Mock(return_value=99)
        sheet.set_contents = Mock()
        self.window.sheets.return_value = [sheet]
        self.window.num_groups.return_value = 2
        self.preview._previews[7] = 99
        for command_type, old_group, target, keep_source in (
            (self.preview.MarkdownPreviewToSideCommand, 0, 1, True),
            (self.preview.MarkdownPreviewCommand, 1, 0, False),
            (self.preview.MarkdownPreviewToSideCommand, 1, 1, True),
        ):
            with self.subTest(command=command_type.__name__, old_group=old_group):
                self.window.reset_mock()
                self.window.get_sheet_index.return_value = (old_group, 0)
                command = command_type()
                command.view = self.view
                with patch.object(self.preview, '_render', return_value='contents'):
                    command.run(None)
                self.window.new_html_sheet.assert_not_called()
                if old_group != target:
                    self.window.set_sheet_index.assert_called_once_with(sheet, target, 0)
                else:
                    self.window.set_sheet_index.assert_not_called()
                self.window.focus_sheet.assert_called_once_with(sheet)
                if keep_source:
                    self.window.focus_view.assert_called_once_with(self.view)
                else:
                    self.window.focus_view.assert_not_called()
