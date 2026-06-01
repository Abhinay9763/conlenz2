from __future__ import annotations

import argparse
from pathlib import Path

from app.core.report import export_report_excel, send_report_email, write_report_json
from app.core.scanner import run_scan
from app.core.settings import load_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Conlenz audit scan (CLI)")
    parser.add_argument("--path", required=True, help="Folder or zip file to scan")
    parser.add_argument("--mode", choices=["quick", "deep"], default="deep")
    parser.add_argument("--recipient", default="", help="Override recipient email")
    parser.add_argument("--out", default="reports", help="Output directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.path).resolve()
    report = run_scan(target, args.mode)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = write_report_json(report, out_dir)
    excel_path = report_path.with_suffix(".xlsx")
    export_report_excel(report, excel_path)

    settings = load_settings()
    recipient = args.recipient.strip() or str(settings.get("receiver_email", "")).strip()
    if recipient:
        send_report_email(report=report, excel_path=excel_path, recipient=recipient)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
