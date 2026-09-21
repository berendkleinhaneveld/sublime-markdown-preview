"""Isolated Sublime API doubles for tests that run in plain Python."""
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class PreviewTestCase(unittest.TestCase):
    def setUp(self):
        self.sublime = types.ModuleType('sublime')
        for name in ('status_message', 'set_timeout', 'set_timeout_async',
                     'load_settings', 'active_window'):
            setattr(self.sublime, name, Mock())
        self.sublime.Region = lambda start, end: (start, end)
        self.sublime.HtmlSheet = type('HtmlSheet', (), {})
        plugin = types.ModuleType('sublime_plugin')
        plugin.TextCommand = plugin.WindowCommand = plugin.EventListener = object
        package = types.ModuleType('_preview_tests')
        package.__path__ = [str(Path(__file__).resolve().parents[1])]
        modules = patch.dict(sys.modules, {
            'sublime': self.sublime, 'sublime_plugin': plugin,
            '_preview_tests': package,
        })
        modules.start()
        self.addCleanup(modules.stop)
        self.preview = importlib.import_module('_preview_tests.preview')
