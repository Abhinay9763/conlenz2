from __future__ import annotations

import subprocess
from pathlib import Path


def has_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def get_modified_files(root: Path) -> list[Path]:
    if not has_git_repo(root):
        return []

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    files: list[Path] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        raw_path = line[3:].strip()
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[-1].strip()
        if not raw_path:
            continue
        files.append((root / raw_path).resolve())

    return files
