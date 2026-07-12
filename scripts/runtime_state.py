#!/usr/bin/env python3
"""Process-safe, manager-owned state and JSONL runtime primitives."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None
    import msvcrt


@contextmanager
def locked(path: Path) -> Iterator[None]:
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        else:
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            else:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _require_scope(writer_role: str | None, scope: str | None) -> None:
    if writer_role not in {"manager", "worker"} or scope not in {"global", "task-local"}:
        raise PermissionError("writer_role and scope are required (cooperative runtime guard)")
    if scope == "global" and writer_role != "manager":
        raise PermissionError("global state/trace is manager-owned")
    if scope == "task-local" and writer_role not in {"manager", "worker"}:
        raise PermissionError("invalid task-local writer")


def _write_locked(path: Path, value: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_write_json(path: Path, value: dict[str, Any], *, writer_role: str | None, scope: str | None) -> None:
    _require_scope(writer_role, scope)
    if scope != "global":
        raise PermissionError("JSON state writes are global; task-local workers may append task-local trace only")
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked(path):
        _write_locked(path, value)


def mutate_json(path: str | Path, mutator: Any, *, writer_role: str | None, scope: str | None) -> None:
    _require_scope(writer_role, scope)
    if scope != "global":
        raise PermissionError("JSON state mutations are global; task-local workers may append task-local trace only")
    target = Path(path).expanduser()
    with locked(target):
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(f"state file does not exist: {target}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {target}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"state JSON root must be object: {target}")
        updated = mutator(data)
        _write_locked(target, updated if isinstance(updated, dict) else data)


def update_json(path: str | Path, updates: dict[str, Any], *, writer_role: str | None, scope: str | None) -> None:
    mutate_json(path, lambda data: {**data, **updates}, writer_role=writer_role, scope=scope)


def append_jsonl(path: str | Path, event: dict[str, Any], *, writer_role: str | None, scope: str | None) -> None:
    _require_scope(writer_role, scope)
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    with locked(target):
        with target.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
