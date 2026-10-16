"""The list of the repositories that atlasmd has seen, in <data>/projects.toml.

amd init writes the entry of its repository. The hook writes or refreshes the entry at every session
start in a repository with atlasmd.toml, and amd config writes the entry of the repository where it
runs. An entry whose folder is gone is dropped at the next write.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import tomllib

from atlasmd import config, ledger

HEAD = "# The repositories that atlasmd has seen. amd init, amd config and the hook write this file.\n"
KEYS = ("path", "name", "group", "seen")


def path() -> pathlib.Path:
    return config.data_dir() / "projects.toml"


def load() -> list[dict]:
    """The entries of the list, in the order of the file. An empty list when the file is missing or broken."""
    try:
        with open(path(), "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    result = []
    items = data.get("project", [])
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip():
            folder = item["path"].strip()
            result.append({"path": folder, "name": str(item.get("name") or os.path.basename(folder)),
                           "group": str(item.get("group") or ""), "seen": str(item.get("seen") or "")})
    return result


def _write(entries: list[dict]) -> None:
    text = HEAD + "".join("\n[[project]]\n" + "".join(f"{k} = {json.dumps(e[k], ensure_ascii=False)}\n" for k in KEYS)
                          for e in entries)
    target = path()
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, target)


def touch(root, group: str, started: bool = False) -> None:
    """Write or refresh the entry of one repository, and drop the entries whose folders are gone.
    seen changes only when started is True, at a session start."""
    root = pathlib.Path(os.path.abspath(os.fspath(root)))
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with ledger._lock(target):  # the lock of the ledgers: two session starts at once lose no entry
        own = config.norm(root)
        entries, seen = [], ""
        for e in load():
            if config.norm(e["path"]) == own:
                seen = e["seen"]
            elif os.path.isdir(e["path"]):
                entries.append(e)
        if started:
            seen = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        entries.append({"path": str(root), "name": root.name, "group": group or "", "seen": seen})
        entries.sort(key=lambda e: (e["name"].lower(), e["path"]))
        _write(entries)


def others(cfg: config.Config) -> list[config.Config]:
    """The other repositories of the list whose atlasmd.toml has the group of cfg, in the order of their names.

    The group comes from each atlasmd.toml as it is now, not from the list. A repository whose atlasmd.toml
    is missing or cannot be read is left out. Empty when cfg has no group.
    """
    if not cfg.group:
        return []
    seen, found = {config.norm(cfg.root)}, []
    for entry in sorted(load(), key=lambda e: (e["name"].lower(), e["path"])):
        key = config.norm(entry["path"])
        if key in seen:
            continue
        toml = pathlib.Path(entry["path"]) / config.CONFIG_NAME
        if not toml.is_file():
            continue
        try:
            other = config.load(toml)
        except config.ConfigError:
            continue
        if other.group == cfg.group:
            seen.add(key)
            found.append(other)
    return found
