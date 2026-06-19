from __future__ import annotations

from PySide6.QtGui import QFont


def apply_style(app) -> None:
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(
        """
        QWidget {
            color: #0c1a24;
            background: #f5f7fb;
        }
        #AppRoot {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #f2fbff, stop:0.55 #f7f7ff, stop:1 #f8fbf0);
        }
        QLabel#BrandTitle {
            font-size: 26px;
            font-weight: 700;
            color: #0f2b3c;
        }
        QLabel#BrandSubtitle {
            color: #3c5a6a;
        }
        QLabel#BrandLogo {
            background: transparent;
        }
        QLabel#AutoTitle {
            font-size: 22px;
            font-weight: 700;
            color: #0f2b3c;
        }
        QLabel#AutoSubtitle {
            color: #4e6b7c;
        }
        QPushButton#PrimaryBtn {
            background: #0f7acb;
            color: white;
            padding: 10px 16px;
            border-radius: 8px;
            font-weight: 600;
        }
        QPushButton#PrimaryBtn:hover {
            background: #0c64a6;
        }
        QPushButton#GhostBtn {
            background: transparent;
            border: 1px solid #c8d7e3;
            color: #1a3a4a;
            padding: 8px 14px;
            border-radius: 8px;
        }
        QPushButton#GhostBtn:hover {
            background: #eaf4ff;
            border-color: #5fa8d3;
            color: #0a2a3a;
        }
        QPushButton#GhostBtn:pressed {
            background: #d0eaff;
            border-color: #3a88b8;
        }
        QPushButton#PrimaryBtn:pressed {
            background: #0a5292;
        }
        QLineEdit#InputField {
            background: white;
            border: 1px solid #d5e2ec;
            border-radius: 8px;
            padding: 8px 10px;
        }
        QWidget#Card {
            background: white;
            border-radius: 12px;
            border: 1px solid #e1edf5;
        }
        QWidget#DropZone {
            background: #f1f8ff;
            border: 2px dashed #92b7d0;
            border-radius: 12px;
        }
        QLabel#DropTitle {
            font-size: 16px;
            font-weight: 600;
            color: #0f2b3c;
        }
        QLabel#DropHint {
            color: #4e6b7c;
        }
        QTableWidget {
            background: white;
            border: 1px solid #e1edf5;
            border-radius: 10px;
            gridline-color: #e9f0f5;
        }
        QHeaderView::section {
            background: #e9f6ff;
            padding: 6px;
            border: none;
            font-weight: 600;
        }
        QLabel#StatValue {
            font-size: 20px;
            font-weight: 700;
            color: #0f2b3c;
        }
        QLabel#StatLabel {
            color: #4e6b7c;
        }
        QCheckBox {
            spacing: 8px;
        }
        """
    )
