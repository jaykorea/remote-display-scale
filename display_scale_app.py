#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QMessageBox,
)


APP_DIR = Path.home() / ".config" / "cocelo-display-scale"
STATE_FILE = APP_DIR / "original_state.json"

# RustDesk 원격 접속용으로 자주 쓰는 논리 해상도 후보군
CANDIDATE_RESOLUTIONS = [
    "1280x720",
    "1366x768",
    "1600x900",
    "1920x1080",
    "2560x1080",
    "2560x1440",
    "3440x1440",
    "3840x2160",
]


def run_cmd(args):
    try:
        p = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
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
        m = re.match(
            r"^Screen\s+\d+:\s+minimum\s+\d+\s+x\s+\d+,\s+current\s+(\d+)\s+x\s+(\d+),\s+maximum\s+(\d+)\s+x\s+(\d+)",
            line,
        )
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

    return screen, outputs


def parse_resolution(res):
    m = re.match(r"^(\d+)x(\d+)$", res)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def save_original_state(output, mode, fb):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"output": output, "mode": mode, "fb": fb}, indent=2),
        encoding="utf-8",
    )


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
        self.setWindowTitle("Cocelo Display Scale")
        self.setMinimumWidth(620)
        self.setMinimumHeight(520)

        self.outputs = []
        self.screen = {}

        layout = QVBoxLayout(self)

        self.status = QLabel()
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)

        row_output = QHBoxLayout()
        row_output.addWidget(QLabel("Output"))
        self.output_combo = QComboBox()
        row_output.addWidget(self.output_combo)
        layout.addLayout(row_output)

        layout.addWidget(QLabel("Resolution candidates"))
        self.resolution_list = QListWidget()
        self.resolution_list.setMinimumHeight(170)
        layout.addWidget(self.resolution_list)

        row_buttons = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Selected")
        self.restore_btn = QPushButton("Restore Original")
        self.refresh_btn = QPushButton("Refresh")
        row_buttons.addWidget(self.apply_btn)
        row_buttons.addWidget(self.restore_btn)
        row_buttons.addWidget(self.refresh_btn)
        layout.addLayout(row_buttons)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(160)
        layout.addWidget(self.log)

        self.apply_btn.clicked.connect(self.apply_selected_resolution)
        self.restore_btn.clicked.connect(self.restore_resolution)
        self.refresh_btn.clicked.connect(self.refresh)
        self.resolution_list.itemDoubleClicked.connect(lambda _: self.apply_selected_resolution())

        self.refresh()

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

        self.output_combo.clear()
        connected = [o for o in self.outputs if o["connected"]]
        for o in connected:
            primary = " primary" if o["primary"] else ""
            mode = o["current_mode"] or "unknown"
            self.output_combo.addItem(f"{o['name']}  ({mode}{primary})", o["name"])

        default = pick_default_output(self.outputs)
        if default:
            idx = self.output_combo.findData(default["name"])
            if idx >= 0:
                self.output_combo.setCurrentIndex(idx)

        self.status.setText(
            f"Current framebuffer: {self.screen.get('current', 'unknown')} / "
            f"Max framebuffer: {self.screen.get('maximum', 'unknown')}"
        )

        self.populate_resolution_candidates()

        if not connected:
            self.append_log("ERROR: No connected display found.")
        else:
            self.append_log("Refreshed display list.")

    def populate_resolution_candidates(self):
        current_fb = self.screen.get("current", "")
        max_fb = self.screen.get("maximum", "")
        max_pair = parse_resolution(max_fb)

        candidates = set(CANDIDATE_RESOLUTIONS)

        # 물리 모니터가 제공하는 모드도 후보에 추가
        for o in self.outputs:
            if o["connected"]:
                candidates.update(o["modes"])

        # 현재 framebuffer도 후보에 추가
        if parse_resolution(current_fb):
            candidates.add(current_fb)

        def sort_key(res):
            pair = parse_resolution(res)
            if not pair:
                return (999999999, res)
            w, h = pair
            return (w * h, w, h)

        sorted_candidates = sorted(candidates, key=sort_key)

        self.resolution_list.clear()
        for res in sorted_candidates:
            pair = parse_resolution(res)
            if not pair:
                continue

            # X screen maximum보다 큰 후보는 제외
            if max_pair:
                w, h = pair
                max_w, max_h = max_pair
                if w > max_w or h > max_h:
                    continue

            label = res
            if res == current_fb:
                label += "  [current]"
            if res in CANDIDATE_RESOLUTIONS and res not in current_fb:
                pass

            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, res)
            self.resolution_list.addItem(item)

            if res == "3440x1440":
                self.resolution_list.setCurrentItem(item)

        if self.resolution_list.currentItem() is None and self.resolution_list.count() > 0:
            self.resolution_list.setCurrentRow(self.resolution_list.count() - 1)

    def selected_output(self):
        name = self.output_combo.currentData()
        for o in self.outputs:
            if o["name"] == name:
                return o
        return None

    def selected_resolution(self):
        item = self.resolution_list.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole)

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

        fb = self.screen.get("current") or mode
        save_original_state(output["name"], mode, fb)

        cmd = [
            "xrandr",
            "--fb", target,
            "--output", output["name"],
            "--mode", mode,
            "--scale-from", target,
            "--pos", "0x0",
        ]

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
        QMessageBox.information(
            self,
            "Applied",
            f"Logical resolution set to {target} on {output['name']}.\n"
            "RustDesk may need reconnecting to capture the new size.",
        )

    def restore_resolution(self):
        state = load_original_state()
        if not state:
            QMessageBox.warning(
                self,
                "No saved state",
                f"No saved original state found:\n{STATE_FILE}",
            )
            return

        output = state["output"]
        mode = state["mode"]
        fb = state["fb"]

        cmd1 = [
            "xrandr",
            "--output", output,
            "--mode", mode,
            "--scale", "1x1",
            "--panning", mode,
            "--pos", "0x0",
        ]
        cmd2 = ["xrandr", "--fb", fb]

        for cmd in (cmd1, cmd2):
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
        QMessageBox.information(self, "Restored", f"Restored {output} to {fb}.")


def main():
    app = QApplication(sys.argv)
    w = DisplayScaleApp()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
