import unittest
from unittest.mock import Mock

from styles import build_stylesheet, theme_colors


class StylesTests(unittest.TestCase):
    def test_partial_colors_keep_defaults_without_mutating_input(self):
        colors = {'foreground': '#123456'}
        css = build_stylesheet(colors)
        self.assertIn('color: #123456;', css)
        self.assertIn('background-color: #ffffff;', css)
        self.assertEqual(colors, {'foreground': '#123456'})

    def test_ui_and_editor_font_roles(self):
        css = build_stylesheet(None, 'Fira Code')
        self.assertIn('font-family: system;', css.split('.content')[0])
        for selector in ('code {', '.code-block, .table-block {'):
            rule = css.split(selector)[1].split('}')[0]
            self.assertIn('font-family: "Fira Code", monospace;', rule)
        self.assertIn('font-family: monospace;', build_stylesheet(None))

    def test_font_cannot_break_out_of_stylesheet(self):
        css = build_stylesheet(None, 'A"\\</style>\n&')
        self.assertNotIn('</style>', css)
        self.assertIn(r'"A\22 \5c \3c /style\3e \a \26 ", monospace', css)

    def view(self, **colors):
        view = Mock()
        view.style.return_value = dict(background='#000', foreground='#FFFFFFff', **colors)
        view.style_for_scope.return_value = {'foreground': '#abc'}
        return view

    def test_theme_normalization_and_contrasting_shades(self):
        colors = theme_colors(self.view(accent='#123456'))
        self.assertEqual(colors, {
            'background': '#000000', 'foreground': '#ffffff', 'accent': '#123456',
            'code_foreground': '#aabbcc', 'code_background': '#0f0f0f',
            'border': '#333333', 'quote': '#737373',
        })

    def test_accent_fallbacks(self):
        for values, expected in (({'bluish': '#123'}, '#112233'),
                                 ({'function': '#456'}, '#445566'), ({}, '#ffffff')):
            with self.subTest(values=values):
                self.assertEqual(theme_colors(self.view(**values))['accent'], expected)

    def test_inline_code_falls_back_to_string_then_accent(self):
        for string_color, expected in (('#123', '#112233'), ('#fff', '#aabbcc')):
            with self.subTest(string_color=string_color):
                view = self.view(accent='#abc')
                view.style_for_scope.side_effect = [
                    {'foreground': '#fff'}, {'foreground': string_color},
                ]
                self.assertEqual(theme_colors(view)['code_foreground'], expected)

    def test_unavailable_scope_uses_accent(self):
        view = self.view(accent='#123')
        view.style_for_scope.side_effect = RuntimeError('unavailable')
        self.assertEqual(theme_colors(view)['code_foreground'], '#112233')

    def test_unavailable_or_incomplete_theme_uses_defaults(self):
        view = Mock()
        view.style.side_effect = RuntimeError('closed view')
        self.assertEqual(theme_colors(view), {})
        view.style.side_effect = None
        for style in ({}, {'background': '#fff'}, {'background': None, 'foreground': '#000'}):
            view.style.return_value = style
            self.assertEqual(theme_colors(view), {})
