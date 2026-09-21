import unittest

from renderer import markdown_to_minihtml


def body(markdown, base_dir='.'):
    return markdown_to_minihtml(markdown, base_dir).split('<div class="content">\n', 1)[1]


class RendererTests(unittest.TestCase):
    def test_basic_formatting(self):
        result = body('# Heading\n\nA **bold**, *italic* and `inline` paragraph.\n\n---')
        for fragment in ('<h1>Heading</h1>', '<strong>bold</strong>',
                         '<em>italic</em>', '<code>inline</code>', '<hr'):
            self.assertIn(fragment, result)

    def test_code_preserves_whitespace_and_escapes_markup(self):
        result = body('```\n  <tag> & value\n    next\n```')
        self.assertIn('<div class="code-block" id="md-code-0">', result)
        self.assertIn('&nbsp;&nbsp;&lt;tag&gt;&nbsp;&amp;&nbsp;value<br>\n'
                      '&nbsp;&nbsp;&nbsp;&nbsp;next', result)
        self.assertNotIn('<pre', result)

    def test_only_fenced_blocks_get_highlighting_ids(self):
        result = body('    indented\n\n```\nfirst\n```\n\n```\nsecond\n```')
        self.assertIn('<div class="code-block">indented</div>', result)
        self.assertIn('id="md-code-0">first', result)
        self.assertIn('id="md-code-1">second', result)
        self.assertNotIn('md-code-2', result)

    def test_table_alignment_and_plain_cell_text(self):
        result = body('| A | Long |\n|---|---|\n| **xx** | & |')
        self.assertIn('<div class="table-block">A&nbsp;&nbsp;|&nbsp;Long<br>\n'
                      '---+-----<br>\nxx&nbsp;|&nbsp;&amp;&nbsp;&nbsp;&nbsp;</div>', result)
        self.assertNotIn('<table', result)
        self.assertNotIn('<strong>', result)

    def test_nested_quotes(self):
        result = body('> Outer\n>\n> > Inner')
        self.assertEqual(result.count('<div class="md-quote">'), 2)
        self.assertNotIn('<blockquote', result)
        self.assertIn('Inner', result)

    def test_nested_ordered_lists_restart_numbering(self):
        result = body('1. outer\n    1. inner\n    2. inner two\n2. outer two')
        self.assertEqual(result.count('<div class="md-ol">'), 2)
        self.assertEqual(result.count('<span class="li-num">1.</span>'), 2)
        self.assertEqual(result.count('<span class="li-num">2.</span>'), 2)
        self.assertNotIn('<ol', result)

    def test_task_items_preserve_ordinary_list_items(self):
        result = body('- [ ] pending\n- [x] done\n- ordinary')
        self.assertIn('<span class="checkbox">☐</span> pending', result)
        self.assertIn('<span class="checkbox">☑</span> done', result)
        self.assertIn('<li>ordinary</li>', result)
        self.assertEqual(result.count('<div class="task-item">'), 2)
        self.assertNotIn('<input', result)

    def test_strikethrough_preserves_nested_formatting_and_entities(self):
        result = body('~~a **b** &~~')
        self.assertIn('<span class="md-strike">a̶ ̶<strong>b̶</strong> ̶&amp;̶</span>', result)

    def test_relative_and_absolute_images(self):
        for source, target in (
            ('../img/p.png', 'file:///project/img/p.png'),
            ('/img/p.png', 'file:///img/p.png'),
            ('https://example.com/p.png', 'https://example.com/p.png'),
            ('data:image/png;base64,abc', 'data:image/png;base64,abc'),
        ):
            with self.subTest(source=source):
                self.assertIn('src="{}"'.format(target),
                              body('![alt]({})'.format(source), '/project/docs'))
