from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from app.core.report import export_report_excel, send_report_email, write_report_json
from app.core.scanner import run_scan
from app.core.settings import app_root, load_settings, save_settings


EVENT_FILE_NAME = "conlenz-autotrack-event"


@dataclass
class RepoState:
    last_event_value: str | None = None
    debounce_timer: QTimer | None = None
    is_scanning: bool = False
    pending_scan: bool = False
    pending_source: str | None = None


class AutoTrackScanWorker(QObject):
    scanFinished = Signal(str, str, str, bool, str, str)

    def __init__(self, repo_id: str, folder: str, scan_type: str, source: str) -> None:
        super().__init__()
        self.repo_id = repo_id
        self.folder = folder
        self.scan_type = scan_type
        self.source = source

    def run(self) -> None:
        try:
            report = run_scan(Path(self.folder), self.scan_type)
        except Exception as exc:
            self.scanFinished.emit(self.repo_id, self.scan_type, self.source, False, str(exc), "")
            return

        try:
            report_path = write_report_json(report, _reports_dir())
        except Exception as exc:
            self.scanFinished.emit(self.repo_id, self.scan_type, self.source, False, str(exc), "")
            return

        try:
            settings = load_settings()
            receiver_email = str(settings.get("receiver_email", "")).strip()
            if not receiver_email:
                raise RuntimeError("Receiver email not configured")
            export_path = report_path.with_suffix(".xlsx")
            export_report_excel(report, export_path)
            send_report_email(report=report, excel_path=export_path, recipient=receiver_email)
        except Exception as exc:
            self.scanFinished.emit(self.repo_id, self.scan_type, self.source, False, str(exc), str(report_path))
            return

        self.scanFinished.emit(self.repo_id, self.scan_type, self.source, True, "ok", str(report_path))


class AutoTrackManager(QObject):
    repoUpdated = Signal()
    scanStarted = Signal(str, str, str)
    scanNotification = Signal(str, str, str, bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._repo_states: dict[str, RepoState] = {}
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, AutoTrackScanWorker] = {}
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_repo_events)
        self._poll_timer.start()

    def reload_settings(self) -> None:
        settings = load_settings()
        repos = _normalize_repos(settings.get("auto_track", {}).get("repos", []))

        current_ids = {repo.get("id") for repo in repos if isinstance(repo, dict)}
        for repo_id in list(self._repo_states.keys()):
            if repo_id not in current_ids:
                state = self._repo_states.pop(repo_id)
                if state.debounce_timer is not None:
                    state.debounce_timer.stop()
                self._threads.pop(repo_id, None)

        for repo in repos:
            repo_id = repo.get("id")
            if not repo_id:
                continue
            state = self._repo_states.setdefault(repo_id, RepoState())
            if state.last_event_value is None:
                repo_path = Path(str(repo.get("path", "")))
                git_dir = _resolve_git_dir(repo_path)
                if git_dir is not None:
                    event_path = _resolve_event_path(git_dir)
                    if event_path is not None:
                        try:
                            state.last_event_value = event_path.read_text(encoding="utf-8").strip()
                        except Exception:
                            pass
            repo_path = Path(str(repo.get("path", "")))
            if repo.get("enabled", True):
                self.ensure_hook(repo_path)
        self.repoUpdated.emit()

    def add_repo(self, repo_path: str, scan_type: str | None = None) -> dict[str, Any]:
        repo_path = repo_path.strip()
        if not repo_path:
            return {"ok": False, "error": "Repo path is required."}

        repo_root = Path(repo_path)
        if not _is_git_repo(repo_root):
            return {"ok": False, "error": "Selected folder is not a git repo (.git missing)."}

        settings = load_settings()
        auto_track = settings.get("auto_track", {})
        repos = _normalize_repos(auto_track.get("repos", []))

        for repo in repos:
            if Path(repo.get("path", "")).resolve() == repo_root.resolve():
                return {"ok": False, "error": "Repo is already tracked."}

        repo_id = uuid.uuid4().hex
        new_repo = {
            "id": repo_id,
            "path": str(repo_root),
            "scan_type": scan_type or auto_track.get("default_scan_type", "quick"),
            "enabled": True,
            "scan_on_push": True,
            "heartbeat_enabled": False,
            "heartbeat_minutes": 60,
            "last_push_at": "",
            "last_scan_at": "",
            "last_scan_status": "",
            "last_heartbeat_at": "",
        }
        repos.append(new_repo)
        auto_track["repos"] = repos
        settings["auto_track"] = auto_track
        save_settings(settings)
        state = self._repo_states.setdefault(repo_id, RepoState())
        git_dir = _resolve_git_dir(repo_root)
        if git_dir is not None:
            event_path = _resolve_event_path(git_dir)
            if event_path is not None:
                try:
                    state.last_event_value = event_path.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
        self.ensure_hook(repo_root)
        self.repoUpdated.emit()
        return {"ok": True, "repo_id": repo_id}

    def update_repo(self, repo_id: str, updates: dict[str, Any]) -> None:
        settings = load_settings()
        auto_track = settings.get("auto_track", {})
        repos = _normalize_repos(auto_track.get("repos", []))
        updated = False

        for repo in repos:
            if repo.get("id") != repo_id:
                continue
            was_heartbeat = bool(repo.get("heartbeat_enabled", False))
            repo.update(updates)
            if not was_heartbeat and bool(repo.get("heartbeat_enabled", False)):
                repo.setdefault("last_heartbeat_at", _now_iso())
            updated = True
            if updates.get("enabled") and repo.get("path"):
                self.ensure_hook(Path(str(repo.get("path"))))
            break

        if updated:
            auto_track["repos"] = repos
            settings["auto_track"] = auto_track
            save_settings(settings)
            self.repoUpdated.emit()

    def remove_repo(self, repo_id: str) -> None:
        settings = load_settings()
        auto_track = settings.get("auto_track", {})
        repos = _normalize_repos(auto_track.get("repos", []))
        repos = [repo for repo in repos if repo.get("id") != repo_id]
        auto_track["repos"] = repos
        settings["auto_track"] = auto_track
        save_settings(settings)
        state = self._repo_states.pop(repo_id, None)
        if state and state.debounce_timer is not None:
            state.debounce_timer.stop()
        self._threads.pop(repo_id, None)
        self.repoUpdated.emit()

    def ensure_hook(self, repo_root: Path) -> None:
        git_dir = _resolve_git_dir(repo_root)
        if git_dir is None:
            return
        hooks_dir = _resolve_hooks_dir(repo_root, git_dir)
        hooks_dir.mkdir(parents=True, exist_ok=True)

        hook_body = "\n".join(
            [
                "#!/bin/sh",
                "git_dir=\"${GIT_DIR:-.git}\"",
                "if [ -f \"$git_dir/commondir\" ]; then",
                "  common_dir=\"$(cat \"$git_dir/commondir\")\"",
                "  case \"$common_dir\" in",
                "    /*) git_dir=\"$common_dir\" ;;",
                "    *) git_dir=\"$git_dir/$common_dir\" ;;",
                "  esac",
                "fi",
                f"event_file=\"$git_dir/{EVENT_FILE_NAME}\"",
                "date -u +\"%Y-%m-%dT%H:%M:%SZ\" > \"$event_file\"",
                "exit 0",
            ]
        )

        hook_cmd_body = "\n".join(
            [
                "@echo off",
                "set git_dir=%GIT_DIR%",
                "if \"%git_dir%\"==\"\" set git_dir=.git",
                "set common_file=%git_dir%\\commondir",
                "if exist \"%common_file%\" for /f \"usebackq delims=\" %%c in (\"%common_file%\") do set git_dir=%git_dir%\\%%c",
                f"set event_file=%git_dir%\\{EVENT_FILE_NAME}",
                "powershell -NoProfile -Command \"Get-Date -Format o | Set-Content -Path '%event_file%' -Encoding ascii\"",
                "exit /b 0",
            ]
        )

        for hook_name in ("pre-push", "post-push"):
            hook_path = hooks_dir / hook_name
            hook_cmd_path = hooks_dir / f"{hook_name}.cmd"
            hook_path.write_text(hook_body, encoding="utf-8")
            hook_cmd_path.write_text(hook_cmd_body, encoding="utf-8")
            try:
                hook_path.chmod(hook_path.stat().st_mode | 0o111)
            except Exception:
                pass

    def _poll_repo_events(self) -> None:
        settings = load_settings()
        auto_track = settings.get("auto_track", {})
        if not auto_track.get("enabled", True):
            return

        repos = _normalize_repos(auto_track.get("repos", []))
        debounce_seconds = int(auto_track.get("debounce_seconds", 2))

        for repo in repos:
            if not repo.get("enabled", True):
                continue
            repo_id = str(repo.get("id", ""))
            repo_path = Path(str(repo.get("path", "")))
            git_dir = _resolve_git_dir(repo_path)
            if git_dir is None:
                continue

            if not _is_hook_installed(repo_path, git_dir):
                self.ensure_hook(repo_path)

            if repo.get("scan_on_push", True):
                event_path = _resolve_event_path(git_dir)
                if event_path is not None:
                    try:
                        value = event_path.read_text(encoding="utf-8").strip()
                    except Exception:
                        value = ""

                    state = self._repo_states.setdefault(repo_id, RepoState())
                    if value and value != state.last_event_value:
                        state.last_event_value = value
                        self._set_repo_fields(repo_id, {"last_push_at": _now_iso()})
                        self._schedule_debounced_scan(repo_id, debounce_seconds, "push")

            self._maybe_trigger_heartbeat(repo, repo_id)

    def _schedule_debounced_scan(self, repo_id: str, debounce_seconds: int, source: str) -> None:
        state = self._repo_states.setdefault(repo_id, RepoState())
        if state.is_scanning:
            state.pending_scan = True
            state.pending_source = source
            return
        if state.debounce_timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda rid=repo_id: self._trigger_scan(rid, source))
            state.debounce_timer = timer

        state.debounce_timer.stop()
        state.debounce_timer.setInterval(int(debounce_seconds) * 1000)
        state.debounce_timer.start()

    def _trigger_scan(self, repo_id: str, source: str) -> None:
        settings = load_settings()
        auto_track = settings.get("auto_track", {})
        repos = _normalize_repos(auto_track.get("repos", []))
        repo = next((item for item in repos if item.get("id") == repo_id), None)
        if not repo:
            return

        repo_path = str(repo.get("path", ""))
        if not repo_path:
            return

        state = self._repo_states.setdefault(repo_id, RepoState())
        if state.is_scanning:
            state.pending_scan = True
            state.pending_source = source
            return

        scan_type = str(repo.get("scan_type") or auto_track.get("default_scan_type", "quick"))
        scan_type = "deep" if scan_type == "deep" else "quick"
        self.scanStarted.emit(repo_id, scan_type, source)

        worker = AutoTrackScanWorker(repo_id, repo_path, scan_type, source)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.scanFinished.connect(self._on_scan_finished)
        worker.scanFinished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda rid=repo_id: self._workers.pop(rid, None))

        state.is_scanning = True
        self._threads[repo_id] = thread
        self._workers[repo_id] = worker
        thread.start()

        if source == "heartbeat":
            self._set_repo_fields(repo_id, {"last_heartbeat_at": _now_iso()})

    def _on_scan_finished(
        self,
        repo_id: str,
        scan_type: str,
        source: str,
        ok: bool,
        message: str,
        report_path: str,
    ) -> None:
        state = self._repo_states.setdefault(repo_id, RepoState())
        state.is_scanning = False
        fields = {
            "last_scan_at": _now_iso(),
            "last_scan_status": "ok" if ok else "error",
        }
        if ok:
            fields["last_scan_report"] = report_path
        self._set_repo_fields(repo_id, fields)
        self.scanNotification.emit(repo_id, scan_type, source, ok, report_path if ok else message)

        if state.pending_scan:
            state.pending_scan = False
            pending_source = state.pending_source or "push"
            state.pending_source = None
            settings = load_settings()
            auto_track = settings.get("auto_track", {})
            debounce_seconds = int(auto_track.get("debounce_seconds", 1))
            if pending_source == "heartbeat":
                self._trigger_scan(repo_id, "heartbeat")
            else:
                self._schedule_debounced_scan(repo_id, debounce_seconds, "push")

    def _set_repo_fields(self, repo_id: str, fields: dict[str, Any]) -> None:
        settings = load_settings()
        auto_track = settings.get("auto_track", {})
        repos = _normalize_repos(auto_track.get("repos", []))
        updated = False

        for repo in repos:
            if repo.get("id") != repo_id:
                continue
            repo.update(fields)
            updated = True
            break

        if updated:
            auto_track["repos"] = repos
            settings["auto_track"] = auto_track
            save_settings(settings)
            self.repoUpdated.emit()

    def _maybe_trigger_heartbeat(self, repo: dict[str, Any], repo_id: str) -> None:
        if not repo.get("heartbeat_enabled", False):
            return
        interval_minutes = int(repo.get("heartbeat_minutes", 60) or 0)
        if interval_minutes <= 0:
            return

        last_beat = str(repo.get("last_heartbeat_at", ""))
        last_time = _parse_iso(last_beat)
        now = datetime.now(timezone.utc)
        if last_time is None:
            due = True
        else:
            due = (now - last_time).total_seconds() >= interval_minutes * 60
        if not due:
            return

        state = self._repo_states.setdefault(repo_id, RepoState())
        if state.is_scanning:
            state.pending_scan = True
            state.pending_source = "heartbeat"
            return
        self._trigger_scan(repo_id, "heartbeat")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_repos(repos: Any) -> list[dict[str, Any]]:
    if not isinstance(repos, list):
        return []
    return [repo for repo in repos if isinstance(repo, dict)]


def _is_git_repo(repo_root: Path) -> bool:
    return _resolve_git_dir(repo_root) is not None


def _resolve_git_dir(repo_root: Path) -> Path | None:
    git_path = repo_root / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        try:
            content = git_path.read_text(encoding="utf-8").strip()
        except Exception:
            return None
        if content.lower().startswith("gitdir:"):
            git_dir_value = content.split(":", 1)[1].strip()
            git_dir = Path(git_dir_value)
            if not git_dir.is_absolute():
                git_dir = (repo_root / git_dir).resolve()
            if git_dir.exists():
                return git_dir
    return None


def _resolve_hooks_dir(repo_root: Path, git_dir: Path) -> Path:
    hooks_path = _read_hooks_path(git_dir, repo_root)
    if hooks_path is not None:
        path = Path(hooks_path)
        return path if path.is_absolute() else (repo_root / path)
    return git_dir / "hooks"


def _read_hooks_path(git_dir: Path, repo_root: Path) -> str | None:
    local_path = _read_hooks_path_from_config(git_dir / "config")
    if local_path:
        return local_path

    for config_path in _global_git_config_paths():
        hooks_path = _read_hooks_path_from_config(config_path)
        if hooks_path:
            return hooks_path
    return None


def _read_hooks_path_from_config(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    in_core = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_core = stripped.strip("[]").strip().lower() == "core"
            continue
        if in_core and "=" in stripped:
            key, value = [part.strip() for part in stripped.split("=", 1)]
            if key.lower() == "hookspath":
                return value
    return None


def _global_git_config_paths() -> list[Path]:
    home = Path.home()
    return [
        home / ".gitconfig",
        home / ".config" / "git" / "config",
    ]


def _resolve_event_path(git_dir: Path) -> Path | None:
    primary = git_dir / EVENT_FILE_NAME
    if primary.exists():
        return primary
    legacy = git_dir / "conlenz_autotrack_event"
    if legacy.exists():
        return legacy
    return None


def _is_hook_installed(repo_root: Path, git_dir: Path) -> bool:
    hooks_dir = _resolve_hooks_dir(repo_root, git_dir)
    for hook_name in ("pre-push", "post-push"):
        hook_path = hooks_dir / hook_name
        hook_cmd_path = hooks_dir / f"{hook_name}.cmd"
        if hook_path.exists() or hook_cmd_path.exists():
            return True
    return False


def _reports_dir() -> Path:
    root = app_root() / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root
