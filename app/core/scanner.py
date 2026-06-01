from __future__ import annotations

import tempfile
from pathlib import Path
from time import perf_counter
import time
from typing import Iterable

from app.core.file_extract import extract_text
from app.core.git_utils import get_modified_files, has_git_repo
from app.core.report import build_report
from app.core.rules import Finding, apply_rules
from app.core.settings import load_settings, update_quick_state


SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".idea", ".vscode"}


def run_scan(target: Path, mode: str) -> dict:
    start = perf_counter()
    if target.is_file() and target.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temp_dir:
            extracted = _extract_zip(target, Path(temp_dir))
            report = _scan_folder(extracted, mode)
    else:
        report = _scan_folder(target, mode)

    report["elapsed_seconds"] = round(perf_counter() - start, 2)
    return report


def _scan_folder(folder: Path, mode: str) -> dict:
    settings = load_settings()
    flags = settings.get("scan_flags", {}) if isinstance(settings.get("scan_flags", {}), dict) else {}
    allow_list = settings.get("allow_list", {}) if isinstance(settings.get("allow_list", {}), dict) else {}
    personal_names = settings.get("names", {}).get("personal_names", [])

    ocr_settings = settings.get("ocr", {})
    limits = settings.get("limits", {})

    ocr_enabled = bool(ocr_settings.get("enabled_deep", True)) if mode == "deep" else bool(ocr_settings.get("enabled_quick", False))
    max_file_size_mb = int(limits.get("max_file_size_mb_deep", 25)) if mode == "deep" else int(limits.get("max_file_size_mb_quick", 10))
    max_text_chars = int(limits.get("max_text_chars", 500000))

    file_targets = _resolve_targets(folder, mode)
    findings: list[Finding] = []
    scanned_files = 0

    for path in file_targets:
        if not path.is_file():
            continue
        if _is_skipped(path):
            continue
        scanned_files += 1
        if path.stat().st_size > max_file_size_mb * 1024 * 1024:
            findings.append(
                Finding(
                    file_path=str(path),
                    rule="Large File",
                    severity="low",
                    confidence="high",
                    snippet=f"Size exceeds {max_file_size_mb} MB",
                    location="",
                )
            )
            continue

        result = extract_text(
            path,
            ocr_enabled=ocr_enabled,
            ocr_languages=ocr_settings.get("languages", ["en"]),
            pdf_readability_threshold=int(ocr_settings.get("pdf_readability_threshold", 200)),
            max_text_chars=max_text_chars,
        )

        per_file = apply_rules(
            text=result.text,
            file_path=str(path),
            allowed_domains={d.lower().lstrip("@") for d in allow_list.get("domains", [])},
            allowed_emails={e.lower() for e in allow_list.get("emails", [])},
            flags=flags,
            personal_names=personal_names,
        )
        findings.extend(per_file)

    if mode == "quick" and folder.exists():
        update_quick_state(folder, time.time())

    return build_report(
        scan_type=mode,
        folder=str(folder),
        findings=findings,
        scanned_files=scanned_files,
    )


def _resolve_targets(folder: Path, mode: str) -> Iterable[Path]:
    if mode == "quick":
        if has_git_repo(folder):
            modified = get_modified_files(folder)
            if modified:
                return modified
            return []
        return _incremental_targets(folder)

    return folder.rglob("*")


def _incremental_targets(folder: Path) -> list[Path]:
    from app.core.settings import load_quick_state

    state = load_quick_state()
    last_scan = state.get(str(folder))
    if not last_scan:
        return list(folder.rglob("*"))

    targets: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime > float(last_scan):
                targets.append(path)
        except OSError:
            continue
    return targets


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _extract_zip(zip_path: Path, dest: Path) -> Path:
    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    return dest
