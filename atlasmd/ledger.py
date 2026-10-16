"""What a session and an agent read, the refusals, and the compaction log.

Every file lives under the data folder of the plugin (CLAUDE_PLUGIN_DATA). A ledger is one small
JSON file per key. A lock file keeps two hooks that run at the same time from losing a read.
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import pathlib
import re
import time

from atlasmd.config import norm, personal

KEEP_REFUSALS = 10
MAX_AGE = 14 * 24 * 3600
PRUNE_EVERY = 3600
SEPARATOR = "@"


def data_dir() -> pathlib.Path:
    return personal()["data_dir"]


def _ledgers() -> pathlib.Path:
    return data_dir() / "ledgers"


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def key(data: dict) -> str:
    """The session, and the agent when the call comes from a subagent."""
    session = str(data.get("session_id") or "no-session")
    agent = data.get("agent_id")
    return f"{session}{SEPARATOR}{agent}" if agent else session


def _split(key: str) -> tuple[str, str | None]:
    session, mark, agent = key.partition(SEPARATOR)
    return session, (agent if mark else None)


def _file(key: str) -> pathlib.Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:80]
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return _ledgers() / f"{safe}-{digest}.json"


@contextlib.contextmanager
def _lock(path: pathlib.Path):
    """Hold a lock file next to the ledger. After two seconds, go on without it: a lost read is
    better than a slow tool call."""
    lock = path.with_name(path.name + ".lock")
    held = False
    deadline = time.monotonic() + 2.0
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            held = True
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 5:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                break
            time.sleep(0.01)
    try:
        yield
    finally:
        if held:
            lock.unlink(missing_ok=True)


def _load(path: pathlib.Path, key: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("paths", [])
            data.setdefault("refusals", [])
            return data
    except (FileNotFoundError, ValueError):
        pass
    session, agent = _split(key)
    return {"session_id": session, "agent_id": agent, "paths": [], "refusals": []}


def _save(path: pathlib.Path, data: dict) -> None:
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    for attempt in range(5):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:  # Windows: a reader holds the file open
            time.sleep(0.01 * (attempt + 1))
    temporary.unlink(missing_ok=True)


def _change(key: str, change) -> None:
    path = _file(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock(path):
        data = _load(path, key)
        change(data)
        _save(path, data)


def read_paths(key: str) -> set[str]:
    """The paths that this key read, in the form of config.norm."""
    return set(_load(_file(key), key)["paths"])


def add(key: str, abs_path) -> None:
    path = norm(abs_path)

    def change(data):
        if path not in data["paths"]:
            data["paths"].append(path)

    if path not in read_paths(key):
        _change(key, change)


def clear_session(session_id) -> None:
    """Remove every ledger of the session, the ledgers of its subagents too."""
    folder = _ledgers()
    if not folder.is_dir():
        return
    session_id = str(session_id or "no-session")
    for path in folder.glob("*.json"):
        try:
            with open(path, encoding="utf-8") as handle:
                owner = json.load(handle).get("session_id")
        except (OSError, ValueError, AttributeError):
            continue
        if owner == session_id:
            path.unlink(missing_ok=True)


def record_refusal(key: str, text: str) -> None:
    def change(data):
        data["refusals"] = (data["refusals"] + [{"time": _now(), "text": text}])[-KEEP_REFUSALS:]

    _change(key, change)


def last_refusal(key: str) -> str | None:
    refusals = _load(_file(key), key)["refusals"]
    return refusals[-1]["text"] if refusals else None


def log_compact(cwd, trigger, summary_chars) -> None:
    """One line in compacts.log: the time, the folder, the trigger and the size of the summary, with tabs between them."""
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "compacts.log", "a", encoding="utf-8") as handle:
        handle.write(f"{_now()}\t{cwd}\t{trigger}\t{int(summary_chars)}\n")


def _seen_file() -> pathlib.Path:
    return data_dir() / "seen.json"


def _seen() -> list[str]:
    try:
        with open(_seen_file(), encoding="utf-8") as handle:
            roots = json.load(handle).get("roots", [])
        return roots if isinstance(roots, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def seen_root(root) -> bool:
    """True when the plugin already offered the setup for this folder."""
    return norm(root) in _seen()


def mark_seen(root) -> None:
    roots = _seen()
    target = norm(root)
    if target not in roots:
        _seen_file().parent.mkdir(parents=True, exist_ok=True)
        _save(_seen_file(), {"roots": roots + [target]})


def prune() -> None:
    """Remove ledgers older than 14 days. Do the work at most once an hour."""
    folder = _ledgers()
    stamp = data_dir() / "pruned.stamp"
    now = time.time()
    try:
        if now - stamp.stat().st_mtime < PRUNE_EVERY:
            return
    except FileNotFoundError:
        pass
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        try:
            if now - path.stat().st_mtime > MAX_AGE:
                path.unlink()
        except OSError:
            continue
