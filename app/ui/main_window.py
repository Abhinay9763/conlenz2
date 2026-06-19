from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal, QObject, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QFrame,
)

from app.core.report import export_report_excel, send_report_email, write_report_json
from app.core.auto_track_manager import AutoTrackManager
from app.core.scanner import run_scan
from app.core.settings import DEFAULT_FLAGS, load_settings, save_settings
from app.ui.auto_track_window import AutoTrackWindow
from app.ui.icon_utils import apply_window_icon


class ScanWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)
    progress = Signal(str, int)  # current file path, count so far

    def __init__(self, target: Path, mode: str) -> None:
        super().__init__()
        self._target = target
        self._mode = mode

    def run(self) -> None:
        try:
            report = run_scan(self._target, self._mode, on_file=self._on_file)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(report)

    def _on_file(self, file_path: str, count: int) -> None:
        self.progress.emit(file_path, count)


class DropZone(QFrame):
    dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)

        title = QLabel("Drop a folder or zip here")
        title.setObjectName("DropTitle")
        hint = QLabel("Quick Scan runs incrementally. Deep Scan runs full OCR.")
        hint.setObjectName("DropHint")
        layout.addWidget(title)
        layout.addWidget(hint)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self.dropped.emit(path)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, settings: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        receiver_label = QLabel("Receiver Email")
        self.receiver_input = QLineEdit()
        self.receiver_input.setObjectName("InputField")
        self.receiver_input.setPlaceholderText("receiver@yourdomain.com")
        self.receiver_input.setText(str(settings.get("receiver_email", "")))

        allow_domains_label = QLabel("Allow-listed Domains")
        self.allow_domains = QLineEdit()
        self.allow_domains.setObjectName("InputField")
        self.allow_domains.setPlaceholderText("example.com, conlenz.com")
        self.allow_domains.setText(", ".join(settings.get("allow_list", {}).get("domains", [])))

        allow_emails_label = QLabel("Allow-listed Emails")
        self.allow_emails = QLineEdit()
        self.allow_emails.setObjectName("InputField")
        self.allow_emails.setPlaceholderText("user@example.com, team@conlenz.com")
        self.allow_emails.setText(", ".join(settings.get("allow_list", {}).get("emails", [])))

        flags_label = QLabel("Scan Flags")
        flags_label.setObjectName("DropHint")
        flags = settings.get("scan_flags", {}) if isinstance(settings.get("scan_flags", {}), dict) else {}

        self.flag_checks: dict[str, QCheckBox] = {}
        for key, label in [
            ("api_key", "API Keys"),
            ("private_key", "Private Keys"),
            ("credit_card", "Credit Cards"),
            ("aadhaar", "Aadhaar"),
            ("pan", "PAN"),
            ("email", "Emails"),
            ("phone", "Phone Numbers"),
            ("ip_address", "IP Addresses"),
            ("personal_name", "Personal Names"),
        ]:
            check = QCheckBox(label)
            check.setChecked(bool(flags.get(key, True)))
            self.flag_checks[key] = check

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("GhostBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch(1)

        layout.addWidget(receiver_label)
        layout.addWidget(self.receiver_input)
        layout.addWidget(allow_domains_label)
        layout.addWidget(self.allow_domains)
        layout.addWidget(allow_emails_label)
        layout.addWidget(self.allow_emails)
        layout.addWidget(flags_label)
        for check in self.flag_checks.values():
            layout.addWidget(check)
        layout.addLayout(btn_row)

    def accept(self) -> None:
        self._settings["receiver_email"] = self.receiver_input.text().strip()
        self._settings["allow_list"]["domains"] = _split_csv(self.allow_domains.text())
        self._settings["allow_list"]["emails"] = _split_csv(self.allow_emails.text())

        flags = dict(DEFAULT_FLAGS)
        for key, check in self.flag_checks.items():
            flags[key] = check.isChecked()
        self._settings["scan_flags"] = flags
        save_settings(self._settings)
        super().accept()


def _split_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Conlenz Audit Tool")
        self.resize(1200, 780)
        apply_window_icon(self)

        self._settings = load_settings()
        self._current_report: dict | None = None
        self._thread: QThread | None = None
        self._worker: ScanWorker | None = None
        self._mode = "quick"
        self._auto_track_manager = AutoTrackManager()
        self._auto_track_manager.reload_settings()
        self._auto_track_manager.scanStarted.connect(self._on_auto_track_scan_started)
        self._auto_track_manager.scanNotification.connect(self._on_auto_track_notification)
        self._auto_track_window: AutoTrackWindow | None = None

        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(18)

        header = self._build_header()
        main_layout.addWidget(header)

        content = QHBoxLayout()
        content.setSpacing(18)
        main_layout.addLayout(content)

        left = self._build_left_panel()
        right = self._build_right_panel()
        content.addWidget(left, 1)
        content.addWidget(right, 2)

        # Apply pointing hand cursor to every button in the window
        for btn in self.findChildren(QPushButton):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build_header(self) -> QWidget:
        card = QWidget()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        logo = QLabel()
        logo.setObjectName("BrandLogo")
        logo_pixmap = self._load_logo_pixmap()
        if logo_pixmap is not None:
            logo.setPixmap(logo_pixmap)
        layout.addWidget(logo)

        title = QLabel("Conlenz")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("Automatic audit tool for customer-facing content")
        subtitle.setObjectName("BrandSubtitle")

        left = QVBoxLayout()
        left.addWidget(title)
        left.addWidget(subtitle)

        layout.addLayout(left)
        layout.addStretch(1)

        auto_track_btn = QPushButton("Auto-Track")
        auto_track_btn.setObjectName("GhostBtn")
        auto_track_btn.clicked.connect(self._open_auto_track)
        layout.addWidget(auto_track_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("GhostBtn")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        return card

    def _build_left_panel(self) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        mode_title = QLabel("Scan Mode")
        mode_title.setObjectName("DropTitle")
        layout.addWidget(mode_title)

        mode_row = QHBoxLayout()
        self.quick_btn = QPushButton("Quick Scan")
        self.quick_btn.setObjectName("PrimaryBtn")
        self.quick_btn.clicked.connect(lambda: self._select_mode("quick"))
        self.deep_btn = QPushButton("Deep Scan")
        self.deep_btn.setObjectName("GhostBtn")
        self.deep_btn.clicked.connect(lambda: self._select_mode("deep"))
        mode_row.addWidget(self.quick_btn)
        mode_row.addWidget(self.deep_btn)
        layout.addLayout(mode_row)

        self.mode_label = QLabel("Incremental scan with git-aware changes")
        self.mode_label.setObjectName("DropHint")
        layout.addWidget(self.mode_label)

        target_row = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setObjectName("InputField")
        self.target_input.setPlaceholderText("Select a folder or zip")
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("GhostBtn")
        browse_btn.clicked.connect(self._browse_target)
        target_row.addWidget(self.target_input, 1)
        target_row.addWidget(browse_btn)
        layout.addLayout(target_row)

        drop = DropZone()
        drop.dropped.connect(self._set_target)
        layout.addWidget(drop)

        self.scan_btn = QPushButton("Start Scan")
        self.scan_btn.setObjectName("PrimaryBtn")
        self.scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self.scan_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("DropHint")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        return card

    def _build_right_panel(self) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        stats_row = QHBoxLayout()
        self.scanned_value = QLabel("0")
        self.scanned_value.setObjectName("StatValue")
        self.flagged_value = QLabel("0")
        self.flagged_value.setObjectName("StatValue")

        scanned_box = self._stat_box("Files Scanned", self.scanned_value)
        flagged_box = self._stat_box("Files Flagged", self.flagged_value)
        stats_row.addWidget(scanned_box)
        stats_row.addWidget(flagged_box)
        stats_row.addStretch(1)
        layout.addLayout(stats_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["File", "Rule", "Severity", "Confidence", "Snippet"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        self.export_btn = QPushButton("Export Excel")
        self.export_btn.setObjectName("GhostBtn")
        self.export_btn.clicked.connect(self._export_report)
        self.email_btn = QPushButton("Email Report")
        self.email_btn.setObjectName("GhostBtn")
        self.email_btn.clicked.connect(self._email_report)
        action_row.addWidget(self.export_btn)
        action_row.addWidget(self.email_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        return card

    def _stat_box(self, label: str, value: QLabel) -> QWidget:
        box = QWidget()
        box.setObjectName("Card")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 10)
        title = QLabel(label)
        title.setObjectName("StatLabel")
        layout.addWidget(title)
        layout.addWidget(value)
        return box

    def _select_mode(self, mode: str) -> None:
        self._mode = mode
        if mode == "quick":
            self.quick_btn.setObjectName("PrimaryBtn")
            self.deep_btn.setObjectName("GhostBtn")
            self.mode_label.setText("Incremental scan with git-aware changes")
        else:
            self.quick_btn.setObjectName("GhostBtn")
            self.deep_btn.setObjectName("PrimaryBtn")
            self.mode_label.setText("Full scan with OCR for PDFs and images")
        self.quick_btn.style().unpolish(self.quick_btn)
        self.quick_btn.style().polish(self.quick_btn)
        self.deep_btn.style().unpolish(self.deep_btn)
        self.deep_btn.style().polish(self.deep_btn)

    def _browse_target(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self._set_target(folder)

    def _set_target(self, path: str) -> None:
        self.target_input.setText(path)

    def _start_scan(self) -> None:
        target = self.target_input.text().strip()
        if not target:
            QMessageBox.warning(self, "Target Required", "Please select a folder or zip file.")
            return
        target_path = Path(target)
        if not target_path.exists():
            QMessageBox.warning(self, "Invalid Path", "Selected target does not exist.")
            return

        self.scan_btn.setEnabled(False)
        self.progress.show()
        self.status_label.setText("Scanning...")

        self._thread = QThread()
        self._worker = ScanWorker(target_path, self._mode)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._scan_finished)
        self._worker.failed.connect(self._scan_failed)
        self._worker.progress.connect(self._scan_progress)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _scan_finished(self, report: dict) -> None:
        self._current_report = report
        self.scanned_value.setText(str(report.get("files_scanned", 0)))
        self.flagged_value.setText(str(report.get("files_flagged", 0)))
        self._load_findings(report.get("findings", []))
        self.status_label.setText("Scan complete")
        self.progress.hide()
        self.scan_btn.setEnabled(True)

    def _scan_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Scan Failed", message)
        self.status_label.setText("Scan failed")
        self.progress.hide()
        self.scan_btn.setEnabled(True)

    def _scan_progress(self, file_path: str, count: int) -> None:
        self.scanned_value.setText(str(count))
        name = Path(file_path).name
        self.status_label.setText(f"Scanning: {name}")

    def _load_findings(self, findings: list[dict]) -> None:
        self.table.setRowCount(0)
        for finding in findings:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(finding.get("file_path", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(str(finding.get("rule", ""))))
            self.table.setItem(row, 2, QTableWidgetItem(str(finding.get("severity", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(str(finding.get("confidence", ""))))
            self.table.setItem(row, 4, QTableWidgetItem(str(finding.get("snippet", ""))))

    def _export_report(self) -> None:
        if not self._current_report:
            QMessageBox.information(self, "No Report", "Run a scan first.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Report", "scan_report.xlsx", "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_report_excel(self._current_report, Path(file_path))
        except Exception as exc:
            QMessageBox.warning(self, "Export Failed", str(exc))

    def _email_report(self) -> None:
        if not self._current_report:
            QMessageBox.information(self, "No Report", "Run a scan first.")
            return
        receiver = str(self._settings.get("receiver_email", "")).strip()
        if not receiver:
            QMessageBox.warning(self, "Receiver Email Required", "Set receiver email in settings.")
            return

        try:
            reports_dir = Path.cwd() / "reports"
            report_path = write_report_json(self._current_report, reports_dir)
            excel_path = report_path.with_suffix(".xlsx")
            export_report_excel(self._current_report, excel_path)
            send_report_email(report=self._current_report, excel_path=excel_path, recipient=receiver)
            QMessageBox.information(self, "Report Sent", "Report email sent successfully.")
        except Exception as exc:
            QMessageBox.warning(self, "Email Failed", str(exc))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self, load_settings())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._settings = load_settings()
            self._auto_track_manager.reload_settings()

    def _open_auto_track(self) -> None:
        if self._auto_track_window is None:
            self._auto_track_window = AutoTrackWindow(self._auto_track_manager)
        self._auto_track_window.show()
        self._auto_track_window.raise_()
        self._auto_track_window.activateWindow()

    def _load_logo_pixmap(self) -> QPixmap | None:
        logo_path = Path(__file__).resolve().parents[2] / "assets" / "logo.png"
        if not logo_path.exists():
            return None
        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            return None
        return pixmap.scaled(46, 46, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def _on_auto_track_scan_started(self, _repo_id: str, scan_type: str, source: str) -> None:
        self.status_label.setText(f"Auto-Track {source} {scan_type} scan started")

    def _on_auto_track_notification(self, _repo_id: str, scan_type: str, source: str, ok: bool, _message: str) -> None:
        status = "completed" if ok else "failed"
        self.status_label.setText(f"Auto-Track {source} {scan_type} scan {status}")
