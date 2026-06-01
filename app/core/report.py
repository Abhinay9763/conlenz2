from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from app.core.rules import Finding


def build_report(
    *,
    scan_type: str,
    folder: str,
    findings: list[Finding],
    scanned_files: int = 0,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    flagged_files = len({finding.file_path for finding in findings})
    return {
        "report_version": 1,
        "scan_type": scan_type,
        "folder": folder,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_scanned": scanned_files,
        "files_flagged": flagged_files,
        "elapsed_seconds": elapsed_seconds,
        "findings": [finding.__dict__ for finding in findings],
    }


def write_report_json(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"scan_report_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def export_report_excel(report: dict[str, Any], export_path: Path) -> None:
    try:
        import openpyxl
    except Exception as exc:
        raise RuntimeError("openpyxl is required for Excel export") from exc

    from openpyxl.styles import Alignment, Font, PatternFill

    export_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Report"

    header_fill = PatternFill("solid", fgColor="E9FCFF")
    bold_font = Font(bold=True)

    rows = _build_rows(report)
    for row in rows:
        sheet.append(row)

    for row_index in (1, 3, 9):
        if row_index > sheet.max_row:
            continue
        for cell in sheet[row_index]:
            cell.font = bold_font
            cell.fill = header_fill

    for col in sheet.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.column_dimensions[col_letter].width = min(max(12, max_len + 2), 80)

    sheet.freeze_panes = "A4"
    workbook.save(export_path)


def _build_rows(report: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    rows.append(["Scan Report"])
    rows.append([])
    rows.append(["Overview", "Value"])
    rows.append(["scan_type", report.get("scan_type", "")])
    rows.append(["folder", report.get("folder", "")])
    rows.append(["generated_at", report.get("generated_at", "")])
    rows.append(["files_scanned", report.get("files_scanned", 0)])
    rows.append(["files_flagged", report.get("files_flagged", 0)])
    rows.append(["elapsed_seconds", report.get("elapsed_seconds", "")])

    rows.append([])
    rows.append(["File Path", "Rule", "Severity", "Confidence", "Snippet", "Location"])
    for finding in report.get("findings", []):
        rows.append(
            [
                finding.get("file_path", ""),
                finding.get("rule", ""),
                finding.get("severity", ""),
                finding.get("confidence", ""),
                finding.get("snippet", ""),
                finding.get("location", ""),
            ]
        )
    return rows


def _load_env_value(key: str, env_path: Path | None = None) -> str | None:
    value = os.environ.get(key)
    if value:
        return value.strip()

    if env_path is None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return None

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        if name.strip() != key:
            continue
        return raw_value.strip().strip('"')
    return None


def build_report_email_body(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Conlenz Scan Summary",
            "",
            f"Scan type: {report.get('scan_type', '')}",
            f"Folder: {report.get('folder', '')}",
            f"Generated at: {report.get('generated_at', '')}",
            f"Files scanned: {report.get('files_scanned', 0)}",
            f"Files flagged: {report.get('files_flagged', 0)}",
            f"Elapsed seconds: {report.get('elapsed_seconds', '')}",
            "",
            "See attached Excel report for full details.",
        ]
    )


def send_report_email(*, report: dict[str, Any], excel_path: Path, recipient: str) -> None:
    api_key = _load_env_value("RESEND_KEY")
    sender = _load_env_value("RESEND_MAIL")
    if not api_key:
        raise RuntimeError("RESEND_KEY not configured")
    if not sender:
        raise RuntimeError("RESEND_MAIL not configured")

    content = base64.b64encode(excel_path.read_bytes()).decode("utf-8")
    payload = {
        "from": sender,
        "to": [recipient],
        "subject": "Conlenz Scan Report",
        "text": build_report_email_body(report),
        "attachments": [
            {
                "filename": excel_path.name,
                "content": content,
            }
        ],
    }

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code >= 300:
        raise RuntimeError(f"Resend error {response.status_code}: {response.text}")
