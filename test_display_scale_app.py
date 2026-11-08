import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

import display_scale_app as display


class DisplayScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication([])

    def setUp(self):
        self.screen = {"current": "3441x1440", "maximum": "3840x2400"}
        self.output = dict(name="default", connected=True, primary=True,
                           current_mode="3441x1440", preferred_mode="",
                           modes=["3441x1440", "1920x1080", "3840x2400"])
        self.query = patch.object(display, "parse_xrandr", return_value=(self.screen, [self.output]))
        self.query.start()
        self.addCleanup(self.query.stop)
        self.window = display.DisplayScaleApp()
        self.addCleanup(self.window.close)

    def test_legacy_output_lists_only_registered_modes_and_disables_scaling(self):
        modes = {self.window.resolution_list.item(i).data(Qt.UserRole)
                 for i in range(self.window.resolution_list.count())}
        self.assertEqual(modes, {"3441x1440", "1920x1080", "3840x2400"})
        self.assertFalse(self.window.scale_combo.isEnabled())

    def test_legacy_apply_changes_mode_without_transform(self):
        for i in range(self.window.resolution_list.count()):
            if self.window.resolution_list.item(i).data(Qt.UserRole) == "1920x1080":
                self.window.resolution_list.setCurrentRow(i)
        with patch.object(display, "run_cmd", return_value=(0, "", "")) as command, \
                patch.object(display, "save_original_state"), \
                patch.object(display.QMessageBox, "information"):
            self.window.apply_selected_resolution()
        command.assert_called_once_with(["xrandr", "--size", "1920x1080"])

    def test_legacy_restore_does_not_request_transform_or_panning(self):
        with patch.object(display, "run_cmd", return_value=(0, "", "")) as command, \
                patch.object(display.QMessageBox, "information"):
            self.window.restore_resolution()
        command.assert_called_once_with(["xrandr", "--size", "3441x1440"])

    def test_normal_output_keeps_scaling_presets(self):
        self.output["name"] = "HDMI-0"
        self.window.refresh()
        modes = {self.window.resolution_list.item(i).data(Qt.UserRole)
                 for i in range(self.window.resolution_list.count())}
        self.assertIn("2880x1800", modes)
        self.assertIn("3677x1440", modes)
        self.assertTrue(self.window.scale_combo.isEnabled())

    def test_legacy_apply_rejects_unregistered_mode(self):
        with patch.object(self.window, "selected_resolution", return_value="2880x1800"), \
                patch.object(display, "run_cmd") as command, \
                patch.object(display.QMessageBox, "warning") as warning:
            self.window.apply_selected_resolution()
        command.assert_not_called()
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
