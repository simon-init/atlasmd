"""The areas of a project: the area of a path, the pack of an area, and the paths that are always free."""
from __future__ import annotations

import os
import pathlib

from atlasmd.config import Area, Config, norm


def _under(target: str, folder: str) -> bool:
    folder = folder.rstrip(os.sep)
    return target == folder or target.startswith(folder + os.sep)


def area_of(cfg: Config, abs_path) -> Area | None:
    """The area whose code path is the longest prefix of the path, or None when the path is free."""
    target = norm(abs_path)
    best, best_length = None, -1
    for area in cfg.areas:
        for entry in area.paths:
            base = norm(cfg.root / entry.rstrip("/"))
            hit = _under(target, base) if entry.endswith("/") else target == base
            if hit and len(base) > best_length:
                best, best_length = area, len(base)
    return best


def split_anchor(entry: str) -> tuple[str, str | None]:
    """A pack entry without and with its #anchor."""
    path, mark, anchor = entry.partition("#")
    return path, (anchor.strip() or None) if mark else None


def pack_of(cfg: Config, area: Area) -> list[tuple[pathlib.Path, str | None]]:
    """The files of the pack of an area, as absolute paths, each with its anchor or None."""
    result, seen = [], set()
    for entry in area.pack:
        path, anchor = split_anchor(entry)
        item = (pathlib.Path(os.path.abspath(cfg.root / path)), anchor)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def is_free(cfg: Config, abs_path) -> bool:
    """True for atlasmd.toml, the start reading and its folders, the state and the map, and every pack file."""
    target = norm(abs_path)
    if target == norm(cfg.path):
        return True
    start = cfg.start
    if _under(target, norm(cfg.root / start.dir)):
        return True
    for entry in [*start.files, *start.also, start.state, start.map, *cfg.private]:
        base = norm(cfg.root / entry.rstrip("/"))
        is_folder = entry.endswith("/") or os.path.isdir(base)
        if target == base or (is_folder and _under(target, base)):
            return True
    for area in cfg.areas:
        for entry in area.pack:
            if target == norm(cfg.root / split_anchor(entry)[0]):
                return True
    return False


def rel(cfg: Config, path) -> str:
    """The path relative to the folder of atlasmd.toml, with / as the separator."""
    path = pathlib.Path(os.path.abspath(os.fspath(path)))
    try:
        return path.relative_to(cfg.root).as_posix()
    except ValueError:
        try:
            return os.path.relpath(path, cfg.root).replace(os.sep, "/")
        except ValueError:  # another drive on Windows
            return path.as_posix()
