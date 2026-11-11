from queue import Queue
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from audioscribe.gui import AudioScribeWindow, _choose_body_font


class GuiProgressTests(unittest.TestCase):
    def setUp(self):
        # Tcl variables work without opening a desktop window.
        self.tcl = tk.Tcl()
        self.window = AudioScribeWindow.__new__(AudioScribeWindow)
        self.window.root = Mock()
        self.window.messages = Queue()
        self.window.busy = True
        self.window.total_items = 0
        for name in ('status', 'progress_detail', 'completed_count'):
            setattr(self.window, name, tk.StringVar(master=self.tcl))
        self.window.progress_bar = Mock()
        self.window.download_button = Mock()
        self.window.append_result = Mock()
        self.window.show_results = Mock()

    def test_live_progress_does_not_end_the_download(self):
        self.window.queue_progress({
            'stage': 'downloading', 'item_index': 2,
            'total_items': 10, 'completed_items': 1, 'url': 'second',
        })
        self.window.check_download()
        self.assertTrue(self.window.busy)
        self.assertEqual(self.window.status.get(), 'Downloading 2 of 10')
        self.window.progress_bar.configure.assert_called_with(maximum=10, value=1)
        self.window.root.after.assert_called_once()

    def test_failed_item_advances_the_processed_count(self):
        self.window.display_progress({
            'stage': 'failed', 'item_index': 2, 'total_items': 10,
            'completed_items': 2, 'url': 'invalid',
        })
        self.assertEqual(self.window.completed_count.get(), 'Processed 2 of 10 items')
        self.window.append_result.assert_called_once_with('FAILED: invalid', succeeded=False)

    def test_result_after_progress_restores_download_button(self):
        self.window.messages.put(('progress', {
            'stage': 'downloading', 'item_index': 1,
            'total_items': 2, 'completed_items': 0, 'url': 'first',
        }))
        self.window.messages.put(('result', {
            'ok': False, 'items': [{'ok': True, 'title': 'first'},
                                    {'ok': False, 'url': 'invalid'}],
        }))
        self.window.check_download()
        self.assertFalse(self.window.busy)
        self.assertEqual(self.window.status.get(), 'Completed with errors')
        self.window.download_button.configure.assert_called_with(state=tk.NORMAL, text='Download')
        self.assertEqual(self.window.completed_count.get(), 'Successful: 1  |  Failed: 1')

    def test_worker_forwards_progress_and_then_final_result(self):
        event = {'stage': 'downloading', 'item_index': 1, 'total_items': 1}
        result = {'ok': True, 'items': []}
        def fake_ingest(**options):
            options['on_event'](event)
            return result
        with patch('audioscribe.gui.ingest', side_effect=fake_ingest):
            self.window.run_download({'inputs': ['one'], 'output_dir': 'outputs'})
        self.assertEqual(self.window.messages.get_nowait(), ('progress', event))
        self.assertEqual(self.window.messages.get_nowait(), ('result', result))

    def test_unexpected_worker_error_restores_window(self):
        with patch('audioscribe.gui.ingest', side_effect=RuntimeError('test failure')):
            self.window.run_download({})
        self.window.check_download()
        self.assertFalse(self.window.busy)
        self.assertEqual(self.window.status.get(), 'Failed')
        self.window.show_results.assert_called_once_with('Download failed:\ntest failure')

    def test_job_events_do_not_overwrite_item_progress(self):
        self.window.status.set('Downloading 2 of 10')
        self.window.display_progress({'stage': 'finished', 'url': None})
        self.assertEqual(self.window.status.get(), 'Downloading 2 of 10')
        self.window.progress_bar.configure.assert_not_called()


    def test_missing_urls_uses_themed_notice(self):
        self.window.busy = False
        self.window.urls = Mock()
        self.window.urls.get.return_value = "  \n"
        self.window.output_dir = tk.StringVar(master=self.tcl, value="outputs")
        self.window._show_notice = Mock()
        self.window.start_download()
        self.window._show_notice.assert_called_once_with("Missing URLs", "Enter at least one URL.")
        self.assertFalse(self.window.busy)

    def test_missing_folder_uses_themed_notice(self):
        self.window.busy = False
        self.window.urls = Mock()
        self.window.urls.get.return_value = "https://example.com/video"
        self.window.output_dir = tk.StringVar(master=self.tcl, value="  ")
        self.window._show_notice = Mock()
        self.window.start_download()
        self.window._show_notice.assert_called_once_with("Missing folder", "Choose an output folder.")
        self.assertFalse(self.window.busy)

    def test_busy_close_uses_themed_notice_and_keeps_window(self):
        self.window._show_notice = Mock()
        self.window.close_window()
        self.window._show_notice.assert_called_once()
        self.window.root.destroy.assert_not_called()

    def test_body_font_prefers_abeezee_and_handles_missing_fonts(self):
        with patch('audioscribe.gui.tkfont.families', return_value=('Trebuchet MS', 'ABeeZee')):
            self.assertEqual(_choose_body_font(self.window.root), 'ABeeZee')
        with patch('audioscribe.gui.tkfont.families', return_value=('Trebuchet MS',)):
            self.assertEqual(_choose_body_font(self.window.root), 'Trebuchet MS')
        with patch('audioscribe.gui.tkfont.families', return_value=()), \
             patch('audioscribe.gui.tkfont.nametofont') as default:
            default.return_value.actual.return_value = 'System Sans'
            self.assertEqual(_choose_body_font(self.window.root), 'System Sans')


if __name__ == '__main__':
    unittest.main()
