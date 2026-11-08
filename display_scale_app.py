#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QTextEdit, QMessageBox, QFrame
)

APP_DIR = Path.home() / ".config" / "cocelo-display-scale"
STATE_FILE = APP_DIR / "original_state.json"
ICON_FILE = Path(__file__).resolve().parent / "assets" / "cocelo-display-scale.png"

CANDIDATE_RESOLUTIONS = [
    "1280x720", "1280x800", "1366x768", "1440x900", "1600x900",
    "1680x1050", "1920x1080", "1920x1200", "2560x1080",
    "2560x1440", "2560x1600", "2880x1800", "3440x1440", "3680x1440",
    "3840x2160", "3840x2400",
]
SCALE_PRESETS = (100, 125, 150, 175, 200, 250, 300)


def run_cmd(args):
    try:
        p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {args[0]}"


def parse_xrandr():
    rc, out, err = run_cmd(["xrandr", "--query"])
    if rc != 0:
        raise RuntimeError(err.strip() or "xrandr --query failed")

    screen = {"current": "", "maximum": ""}
    outputs = []
    current = None

    for line in out.splitlines():
        m = re.match(r"^Screen\s+\d+:\s+minimum\s+\d+\s+x\s+\d+,\s+current\s+(\d+)\s+x\s+(\d+),\s+maximum\s+(\d+)\s+x\s+(\d+)", line)
        if m:
            screen["current"] = f"{m.group(1)}x{m.group(2)}"
            screen["maximum"] = f"{m.group(3)}x{m.group(4)}"
            continue

        m = re.match(r"^(\S+)\s+(connected|disconnected)(?:\s+primary)?", line)
        if m:
            name = m.group(1)
            connected = m.group(2) == "connected"
            primary = " connected primary" in line
            current = {
                "name": name,
                "connected": connected,
                "primary": primary,
                "current_mode": "",
                "preferred_mode": "",
                "modes": [],
            }
            outputs.append(current)
            continue

        if current and current["connected"] and line.startswith("   "):
            parts = line.split()
            if not parts:
                continue
            mode = parts[0]
            current["modes"].append(mode)
            if "*" in line:
                current["current_mode"] = mode
            if "+" in line:
                current["preferred_mode"] = mode

    return screen, outputs


def parse_resolution(res):
    m = re.match(r"^(\d+)x(\d+)$", res)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def save_original_state(output, mode, fb):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"output": output, "mode": mode, "fb": fb}, indent=2), encoding="utf-8")


def load_original_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def pick_default_output(outputs):
    connected = [o for o in outputs if o["connected"]]
    if not connected:
        return None
    for o in connected:
        if o["primary"]:
            return o
    return connected[0]


class DisplayScaleApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("COCELO DISPLAY SETUP")
        self.setWindowIcon(QIcon(str(ICON_FILE)))
        self.setMinimumWidth(700)
        self.setMinimumHeight(560)
        self.outputs = []
        self.screen = {}
        self.apply_bios_theme()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        for tab, active in [("Main", False), ("Config", False), ("Date/Time", False), ("Security", False), ("Startup", True), ("Restart", False)]:
            label = QLabel(tab)
            label.setObjectName("activeTab" if active else "tab")
            label.setAlignment(Qt.AlignCenter)
            top_layout.addWidget(label)
        top_layout.addStretch(1)
        root.addWidget(top_bar)

        body = QVBoxLayout()
        body.setContentsMargins(28, 24, 28, 20)
        body.setSpacing(14)
        root.addLayout(body)

        title = QLabel("Display Scale Setup")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignRight)
        body.addWidget(title)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.status)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("separator")
        body.addWidget(line)

        row_output = QHBoxLayout()
        output_label = QLabel("▶ Display Output")
        output_label.setObjectName("menuLabel")
        self.output_combo = QComboBox()
        self.output_combo.setMinimumHeight(34)
        row_output.addWidget(output_label, 1)
        row_output.addWidget(self.output_combo, 2)
        body.addLayout(row_output)

        row_scale = QHBoxLayout()
        scale_label = QLabel("▶ Logical Scale")
        scale_label.setObjectName("menuLabel")
        self.scale_combo = QComboBox()
        self.scale_combo.setMinimumHeight(34)
        self.scale_combo.setToolTip(
            "Logical size relative to the selected output mode. "
            "200% doubles width and height; this is not desktop UI/text scaling."
        )
        row_scale.addWidget(scale_label, 1)
        row_scale.addWidget(self.scale_combo, 2)
        body.addLayout(row_scale)

        res_label = QLabel("Resolution Candidates")
        res_label.setObjectName("sectionLabel")
        body.addWidget(res_label)

        self.resolution_list = QListWidget()
        self.resolution_list.setMinimumHeight(190)
        body.addWidget(self.resolution_list)

        row_buttons = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Selected")
        self.restore_btn = QPushButton("Restore Original")
        self.refresh_btn = QPushButton("Refresh")
        row_buttons.addStretch(1)
        row_buttons.addWidget(self.apply_btn)
        row_buttons.addWidget(self.restore_btn)
        row_buttons.addWidget(self.refresh_btn)
        body.addLayout(row_buttons)

        log_label = QLabel("System Log")
        log_label.setObjectName("sectionLabel")
        body.addWidget(log_label)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        body.addWidget(self.log)

        footer = QLabel("F10 Apply    F9 Restore    ESC Close")
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignRight)
        body.addWidget(footer)

        self.apply_btn.clicked.connect(self.apply_selected_resolution)
        self.restore_btn.clicked.connect(self.restore_resolution)
        self.refresh_btn.clicked.connect(self.refresh)
        self.resolution_list.itemDoubleClicked.connect(lambda _: self.apply_selected_resolution())
        self.output_combo.currentIndexChanged.connect(self.populate_resolution_candidates)
        self.scale_combo.currentIndexChanged.connect(self.select_scale_preset)
        self.resolution_list.currentItemChanged.connect(self.sync_scale_selection)
        self.refresh()

    def apply_bios_theme(self):
        self.setStyleSheet("""
            QWidget { background-color: #b7b7b7; color: #000050; font-family: "DejaVu Sans Mono", "Ubuntu Mono", monospace; font-size: 14px; }
            #topBar { background-color: #0000b8; border-bottom: 2px solid #ffffff; }
            #tab { background-color: #0000b8; color: #ffffff; font-weight: bold; padding: 7px 18px; border-right: 1px solid #6060ff; }
            #activeTab { background-color: #d7d7d7; color: #0000a0; font-weight: bold; padding: 7px 18px; border-left: 2px solid #ffffff; border-right: 2px solid #202020; }
            #title { color: #ffffff; font-size: 34px; font-weight: bold; font-style: italic; letter-spacing: 1px; }
            #status { color: #000000; background-color: #c9c9c9; padding: 8px; border: 1px solid #808080; }
            #menuLabel, #sectionLabel { color: #000080; font-weight: bold; }
            QComboBox { background-color: #d8d8d8; color: #000000; selection-background-color: #0000b8; selection-color: #ffffff; border: 2px solid #808080; padding: 5px; }
            QComboBox::drop-down { border-left: 1px solid #808080; width: 24px; }
            QListWidget { background-color: #c9c9c9; color: #000050; border: 2px solid #808080; outline: none; padding: 4px; }
            QListWidget::item { padding: 5px 8px; }
            QListWidget::item:selected { background-color: #0000b8; color: #ffffff; }
            QPushButton { background-color: #d8d8d8; color: #000080; font-weight: bold; border-top: 2px solid #ffffff; border-left: 2px solid #ffffff; border-right: 2px solid #404040; border-bottom: 2px solid #404040; padding: 7px 14px; min-width: 120px; }
            QPushButton:pressed { border-top: 2px solid #404040; border-left: 2px solid #404040; border-right: 2px solid #ffffff; border-bottom: 2px solid #ffffff; background-color: #c0c0c0; }
            QTextEdit { background-color: #a9a9a9; color: #000000; border: 2px inset #808080; padding: 6px; }
            QMessageBox { background-color: #b7b7b7; }
            #separator { color: #808080; background-color: #808080; max-height: 1px; }
            #footer { color: #000080; font-weight: bold; }
        """)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F10:
            self.apply_selected_resolution()
        elif event.key() == Qt.Key_F9:
            self.restore_resolution()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def append_log(self, text):
        self.log.append(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def refresh(self):
        try:
            self.screen, self.outputs = parse_xrandr()
        except Exception as e:
            self.status.setText("xrandr read failed")
            self.append_log(f"ERROR: {e}")
            return

        previous_output = self.output_combo.currentData()
        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        connected = [o for o in self.outputs if o["connected"]]
        for o in connected:
            primary = " primary" if o["primary"] else ""
            mode = o["current_mode"] or "unknown"
            self.output_combo.addItem(f"{o['name']}  [{mode}{primary}]", o["name"])

        default = pick_default_output(self.outputs)
        if default:
            idx = self.output_combo.findData(previous_output)
            if idx < 0:
                idx = self.output_combo.findData(default["name"])
            if idx >= 0:
                self.output_combo.setCurrentIndex(idx)
        self.output_combo.blockSignals(False)

        self.status.setText(f"Current framebuffer: {self.screen.get('current', 'unknown')}     Max framebuffer: {self.screen.get('maximum', 'unknown')}")
        self.populate_resolution_candidates()
        self.append_log("Display list refreshed." if connected else "ERROR: No connected display found.")

    def populate_resolution_candidates(self):
        previous_resolution = self.selected_resolution()
        previous_scale = self.scale_combo.currentData()
        current_fb = self.screen.get("current", "")
        max_fb = self.screen.get("maximum", "")
        max_pair = parse_resolution(max_fb)
        candidates = set(CANDIDATE_RESOLUTIONS)
        output = self.selected_output()
        # Legacy RandR exposes "default" without CRTC transform support.
        legacy_output = output and output["name"] == "default"
        if legacy_output:
            candidates = set(output["modes"])
        mode_pair = parse_resolution(output["current_mode"]) if output else None
        scale_resolutions = {}
        if mode_pair and not legacy_output:
            for percent in SCALE_PRESETS:
                w, h = (max(1, (value * percent + 50) // 100) for value in mode_pair)
                if max_pair and (w > max_pair[0] or h > max_pair[1]):
                    continue
                scale_resolutions[f"{w}x{h}"] = percent
        self.scale_combo.blockSignals(True)
        self.scale_combo.clear()
        self.scale_combo.addItem("Use resolution preset", None)
        for res, percent in scale_resolutions.items():
            self.scale_combo.addItem(f"{percent}%  [{res}]", res)
        self.scale_combo.setEnabled(bool(scale_resolutions))
        self.scale_combo.setToolTip(
            "This legacy output supports registered resolutions only."
            if legacy_output else
            "Logical size relative to the selected output mode; not desktop UI/text scaling."
        )
        self.scale_combo.blockSignals(False)

        def sort_key(res):
            pair = parse_resolution(res)
            if not pair:
                return (999999999, res)
            w, h = pair
            return (w, h)

        self.resolution_list.blockSignals(True)
        self.resolution_list.clear()
        for res in sorted(candidates, key=sort_key):
            pair = parse_resolution(res)
            if not pair:
                continue
            if max_pair:
                w, h = pair
                max_w, max_h = max_pair
                if w > max_w or h > max_h:
                    continue
            label = f"  {res}"
            if res == current_fb:
                label += "    * Current"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, res)
            self.resolution_list.addItem(item)
            if res == previous_resolution:
                self.resolution_list.setCurrentItem(item)
        if self.resolution_list.currentItem() is None:
            for index in range(self.resolution_list.count()):
                item = self.resolution_list.item(index)
                if item.data(Qt.UserRole) == current_fb:
                    self.resolution_list.setCurrentItem(item)
                    break
        if self.resolution_list.currentItem() is None and self.resolution_list.count() > 0:
            self.resolution_list.setCurrentRow(self.resolution_list.count() - 1)
        self.resolution_list.blockSignals(False)
        if previous_scale:
            index = self.scale_combo.findData(previous_scale)
            if index >= 0:
                self.scale_combo.setCurrentIndex(index)

    def select_scale_preset(self):
        target = self.scale_combo.currentData()
        if target:
            self.resolution_list.blockSignals(True)
            self.resolution_list.setCurrentRow(-1)
            self.resolution_list.blockSignals(False)
        elif self.resolution_list.currentItem() is None and self.resolution_list.count():
            self.resolution_list.setCurrentRow(0)

    def sync_scale_selection(self):
        self.scale_combo.blockSignals(True)
        self.scale_combo.setCurrentIndex(0)
        self.scale_combo.blockSignals(False)

    def selected_output(self):
        name = self.output_combo.currentData()
        for o in self.outputs:
            if o["name"] == name:
                return o
        return None

    def selected_resolution(self):
        scale_target = self.scale_combo.currentData()
        if scale_target:
            return scale_target
        item = self.resolution_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def apply_selected_resolution(self):
        target = self.selected_resolution()
        if not target:
            QMessageBox.warning(self, "No resolution", "Select a resolution candidate first.")
            return
        output = self.selected_output()
        if not output:
            QMessageBox.warning(self, "No output", "No connected output selected.")
            return
        mode = output["current_mode"]
        if not mode:
            QMessageBox.warning(self, "No mode", f"Cannot detect current mode for {output['name']}.")
            return
        if output["name"] == "default" and target not in output["modes"]:
            QMessageBox.warning(self, "Unsupported resolution", "Select a registered display mode, or refresh the display list.")
            return
        fb = self.screen.get("current") or mode
        save_original_state(output["name"], mode, fb)
        cmd = ["xrandr", "--fb", target, "--output", output["name"], "--mode", mode, "--scale-from", target, "--pos", "0x0"]
        if output["name"] == "default":
            cmd = ["xrandr", "--size", target]
        self.append_log("$ " + " ".join(cmd))
        rc, out, err = run_cmd(cmd)
        if out.strip():
            self.append_log(out.strip())
        if err.strip():
            self.append_log(err.strip())
        if rc != 0:
            QMessageBox.critical(self, "Apply failed", err.strip() or "xrandr failed")
            return
        self.refresh()
        QMessageBox.information(self, "Applied", f"Resolution set to {target} on {output['name']}.\nRustDesk may need reconnecting to capture the new size.")

    def restore_resolution(self):
        # 저장된 이전 상태가 아니라 HD-0의 기본(preferred/native) 해상도로 복원한다.
        try:
            self.screen, self.outputs = parse_xrandr()
        except Exception as e:
            QMessageBox.critical(self, "Restore failed", str(e))
            return

        connected = [o for o in self.outputs if o["connected"]]

        # 사용 환경에 따라 출력명이 HD-0 또는 HDMI-0일 수 있으므로 순서대로 탐색한다.
        output = next((o for o in connected if o["name"].lower() == "hd-0"), None)
        if output is None:
            output = next((o for o in connected if o["name"].lower() == "hdmi-0"), None)
        if output is None:
            output = pick_default_output(self.outputs)

        if not output:
            QMessageBox.warning(self, "No output", "No connected display output found.")
            return

        # xrandr에서 '+'가 붙은 preferred mode를 우선 사용한다.
        # preferred 표시가 없으면 해당 출력의 첫 번째 모드를 기본 모드로 사용한다.
        mode = output.get("preferred_mode") or (output["modes"][0] if output["modes"] else "")
        if not mode:
            QMessageBox.warning(
                self,
                "No default mode",
                f"Cannot detect the default resolution for {output['name']}.",
            )
            return

        # 스케일/패닝을 제거한 뒤 실제 출력 모드와 framebuffer를 동일하게 맞춘다.
        commands = [
            [
                "xrandr",
                "--output", output["name"],
                "--mode", mode,
                "--scale", "1x1",
                "--panning", "0x0",
                "--pos", "0x0",
            ],
            ["xrandr", "--fb", mode],
        ]
        if output["name"] == "default":
            commands = [["xrandr", "--size", mode]]

        for cmd in commands:
            self.append_log("$ " + " ".join(cmd))
            rc, out, err = run_cmd(cmd)
            if out.strip():
                self.append_log(out.strip())
            if err.strip():
                self.append_log(err.strip())
            if rc != 0:
                QMessageBox.critical(self, "Restore failed", err.strip() or "xrandr failed")
                return

        self.refresh()
        QMessageBox.information(
            self,
            "Restored",
            f"Restored {output['name']} to its default resolution: {mode}.",
        )


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON_FILE)))
    w = DisplayScaleApp()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
