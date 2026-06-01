from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.auto_track_manager import AutoTrackManager
from app.core.settings import load_settings
from app.ui.icon_utils import apply_window_icon


class AutoTrackWindow(QMainWindow):
    def __init__(self, manager: AutoTrackManager) -> None:
        super().__init__()
        self.setWindowTitle("Auto-Track")
        self.resize(980, 640)
        apply_window_icon(self)

        self._manager = manager
        self._manager.repoUpdated.connect(self._refresh_table)

        root = QWidget()
        root.setObjectName("AutoTrackRoot")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Auto-Track")
        title.setObjectName("AutoTitle")
        subtitle = QLabel("Track git pushes and run scans automatically.")
        subtitle.setObjectName("AutoSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        self.add_btn = QPushButton("Add Repo")
        self.add_btn.setObjectName("PrimaryBtn")
        self.add_btn.clicked.connect(self._add_repo)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("GhostBtn")
        self.edit_btn.clicked.connect(self._edit_repo)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("GhostBtn")
        self.remove_btn.clicked.connect(self._remove_repo)

        self.toggle_btn = QPushButton("Enable/Disable")
        self.toggle_btn.setObjectName("GhostBtn")
        self.toggle_btn.clicked.connect(self._toggle_repo)

        controls.addWidget(self.add_btn)
        controls.addWidget(self.edit_btn)
        controls.addWidget(self.remove_btn)
        controls.addWidget(self.toggle_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 10)
        self.table.setObjectName("AutoTrackTable")
        self.table.setHorizontalHeaderLabels(
            [
                "Repo",
                "Path",
                "Scan",
                "Enabled",
                "On Push",
                "Heartbeat",
                "Every (min)",
                "Last Push",
                "Last Scan",
                "Status",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 90)
        self.table.setColumnWidth(7, 140)
        self.table.setColumnWidth(8, 140)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self._edit_repo())
        layout.addWidget(self.table)

        hint_label = QLabel("Hooks are installed automatically when a repo is added.")
        hint_label.setObjectName("DropHint")
        layout.addWidget(hint_label)

        self._refresh_table()

    def _add_repo(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select git repo to track")
        if not folder:
            return

        repo_root = Path(folder)
        if not (repo_root / ".git").exists():
            QMessageBox.warning(self, "Invalid Repo", "Selected folder does not contain a .git directory.")
            return

        result = self._manager.add_repo(folder)
        if not result.get("ok"):
            QMessageBox.warning(self, "Auto-Track", str(result.get("error", "Failed to add repo.")))
            return

        self._refresh_table()

    def _edit_repo(self) -> None:
        repo = self._get_selected_repo()
        if not repo:
            QMessageBox.information(self, "Auto-Track", "Select a repo to edit.")
            return

        dialog = RepoEditDialog(self, repo)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        updates = {
            "scan_type": dialog.scan_type,
            "enabled": dialog.enabled,
            "scan_on_push": dialog.scan_on_push,
            "heartbeat_enabled": dialog.heartbeat_enabled,
            "heartbeat_minutes": dialog.heartbeat_minutes,
        }
        self._manager.update_repo(repo["id"], updates)

    def _remove_repo(self) -> None:
        repo = self._get_selected_repo()
        if not repo:
            QMessageBox.information(self, "Auto-Track", "Select a repo to remove.")
            return

        confirm = QMessageBox.question(
            self,
            "Remove Repo",
            "Remove this repo from Auto-Track?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._manager.remove_repo(repo["id"])

    def _toggle_repo(self) -> None:
        repo = self._get_selected_repo()
        if not repo:
            QMessageBox.information(self, "Auto-Track", "Select a repo to enable/disable.")
            return
        enabled = not bool(repo.get("enabled", True))
        self._manager.update_repo(repo["id"], {"enabled": enabled})

    def _get_selected_repo(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        repo_id = item.data(Qt.ItemDataRole.UserRole)
        if not repo_id:
            return None

        settings = load_settings()
        repos = settings.get("auto_track", {}).get("repos", [])
        if not isinstance(repos, list):
            return None
        for repo in repos:
            if isinstance(repo, dict) and repo.get("id") == repo_id:
                return repo
        return None

    def _refresh_table(self) -> None:
        settings = load_settings()
        repos = settings.get("auto_track", {}).get("repos", [])
        if not isinstance(repos, list):
            repos = []

        self.table.setRowCount(0)
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)

            path = str(repo.get("path", ""))
            name = Path(path).name if path else ""
            scan_type = str(repo.get("scan_type", ""))
            enabled = "Yes" if repo.get("enabled", True) else "No"
            on_push = "Yes" if repo.get("scan_on_push", True) else "No"
            heartbeat_enabled = "Yes" if repo.get("heartbeat_enabled", False) else "No"
            heartbeat_minutes = str(repo.get("heartbeat_minutes", ""))
            last_push = str(repo.get("last_push_at", ""))
            last_scan = str(repo.get("last_scan_at", ""))
            status = str(repo.get("last_scan_status", ""))

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, repo.get("id"))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(path))
            self.table.setItem(row, 2, QTableWidgetItem(scan_type))
            self.table.setItem(row, 3, QTableWidgetItem(enabled))
            self.table.setItem(row, 4, QTableWidgetItem(on_push))
            self.table.setItem(row, 5, QTableWidgetItem(heartbeat_enabled))
            self.table.setItem(row, 6, QTableWidgetItem(heartbeat_minutes))
            self.table.setItem(row, 7, QTableWidgetItem(last_push))
            self.table.setItem(row, 8, QTableWidgetItem(last_scan))
            self.table.setItem(row, 9, QTableWidgetItem(status))


class RepoEditDialog(QDialog):
    def __init__(self, parent: QWidget, repo: dict[str, Any]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Repo")

        self.scan_type = str(repo.get("scan_type", "quick")) or "quick"
        self.enabled = bool(repo.get("enabled", True))
        self.scan_on_push = bool(repo.get("scan_on_push", True))
        self.heartbeat_enabled = bool(repo.get("heartbeat_enabled", False))
        self.heartbeat_minutes = int(repo.get("heartbeat_minutes", 60) or 60)

        layout = QVBoxLayout(self)

        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Scan Type"))
        self.scan_combo = QComboBox()
        self.scan_combo.addItems(["quick", "deep"])
        self.scan_combo.setCurrentText(self.scan_type)
        scan_row.addWidget(self.scan_combo)
        layout.addLayout(scan_row)

        enabled_row = QHBoxLayout()
        enabled_row.addWidget(QLabel("Enabled"))
        self.enabled_combo = QComboBox()
        self.enabled_combo.addItems(["Yes", "No"])
        self.enabled_combo.setCurrentText("Yes" if self.enabled else "No")
        enabled_row.addWidget(self.enabled_combo)
        layout.addLayout(enabled_row)

        push_row = QHBoxLayout()
        push_row.addWidget(QLabel("Scan on Push"))
        self.push_check = QCheckBox()
        self.push_check.setChecked(self.scan_on_push)
        push_row.addWidget(self.push_check)
        layout.addLayout(push_row)

        heartbeat_row = QHBoxLayout()
        heartbeat_row.addWidget(QLabel("Heartbeat"))
        self.heartbeat_check = QCheckBox()
        self.heartbeat_check.setChecked(self.heartbeat_enabled)
        heartbeat_row.addWidget(self.heartbeat_check)
        heartbeat_row.addWidget(QLabel("Every (min)"))
        self.heartbeat_combo = QComboBox()
        self.heartbeat_combo.setEditable(True)
        self.heartbeat_combo.addItems(["5", "10", "15", "30", "60", "120", "240"])
        self.heartbeat_combo.setCurrentText(str(self.heartbeat_minutes))
        heartbeat_row.addWidget(self.heartbeat_combo)
        layout.addLayout(heartbeat_row)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self) -> None:
        self.scan_type = self.scan_combo.currentText().strip()
        self.enabled = self.enabled_combo.currentText() == "Yes"
        self.scan_on_push = self.push_check.isChecked()
        self.heartbeat_enabled = self.heartbeat_check.isChecked()
        try:
            self.heartbeat_minutes = max(1, int(self.heartbeat_combo.currentText().strip()))
        except ValueError:
            self.heartbeat_minutes = 60
        super().accept()
