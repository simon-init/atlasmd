"""The checks of amd check that keep the Markdown files in their places, under [check] of atlasmd.toml.

Growth: a folder with source files and no README.md or no [[area]] entry, an [[area]] path that does not
exist, and a README under pack that did not change while its folder changed. Cleaning: a dead path in the
open items, a plan or a note that nothing names, a decision without its line in the index, and a state
file that did not change. The checks name files. They move and delete nothing.
"""
from __future__ import annotations

import datetime
import os
import re
from pathlib import Path

from atlasmd import areas, mapping, scan

SKIPPED = {"node_modules", ".venv", "tests", "test"}


# --- the folders ---------------------------------------------------------------------------------

def skipped(folder: str) -> bool:
    """True for docs/, a folder whose name starts with a dot, node_modules, .venv, tests and test, and the folders below them."""
    parts = folder.split("/")
    return parts[0] == "docs" or any(p.startswith(".") or p in SKIPPED for p in parts)


def is_source(path) -> bool:
    return Path(str(path)).suffix.lower() in scan.SOURCE_EXT


def _folder(rel: str) -> str:
    return rel.rsplit("/", 1)[0] if "/" in rel else ""


def _ancestors(folder: str) -> list[str]:
    """The folder and the folders above it, below the root, the folder first."""
    parts = folder.split("/")
    return ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]


def _tops(folders) -> list[str]:
    """The folders without a folder of the same set above them."""
    found = set(folders)
    return sorted(f for f in found if not any(a in found for a in _ancestors(f)[1:]))


def no_readme(files) -> list[str]:
    """The folders that hold a source file and have no README.md in them or in a folder above them below the root."""
    readmes = {_folder(f) for f in files if "/" in f and f.rsplit("/", 1)[1].lower() == "readme.md"}
    folders = {_folder(f) for f in files if "/" in f and is_source(f)}
    return _tops(f for f in folders if not skipped(f) and not any(a in readmes for a in _ancestors(f)))


def no_entry(cfg, files) -> list[str]:
    """The folders that hold a source file that the paths of no [[area]] entry hold."""
    folders = set()
    for f in files:
        folder = _folder(f)
        if folder and is_source(f) and not skipped(folder) and areas.area_of(cfg, cfg.root / f) is None:
            folders.add(folder)
    return _tops(folders)


def new_folder(cfg, abs_path) -> str | None:
    """For a new source file, the folder to name: the first folder that the Write makes, else the folder of the
    file. None when the file is at the root or outside it, or in a skipped folder."""
    rel = areas.rel(cfg, abs_path)
    folder = _folder(rel)
    if not folder or rel.startswith("../") or skipped(folder):
        return None
    named = folder
    for candidate in _ancestors(folder):
        if (cfg.root / candidate).is_dir():
            break
        named = candidate
    return named


def holders(cfg, folder: str) -> list[tuple[str, str]]:
    """(name, path) of each [[area]] path that holds the folder, or that lies inside it."""
    found = []
    for area in cfg.areas:
        for path in area.paths:
            bare = path.rstrip("/")
            if (path.endswith("/") and (folder + "/").startswith(bare + "/")) or bare.startswith(folder + "/"):
                found.append((area.name, path))
    return found


# --- growth --------------------------------------------------------------------------------------

def _commits(root, since: str, paths: list[str]) -> int:
    out = scan.git(root, "rev-list", "--count", f"{since}..HEAD", "--", *paths)
    return int(out.strip()) if out and out.strip().isdigit() else 0


def _last(root, path: str, fmt: str) -> str | None:
    out = scan.git(root, "log", "-1", f"--format={fmt}", "--", path)
    return out.strip() if out and out.strip() else None


def _either(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def stale_readmes(cfg, limit: int):
    """(README, count, the folders counted) for each README.md under pack that did not change in the last
    `limit` commits that changed its folder. The folder counts when the paths of the entry hold it. When the
    paths of the entry lie inside the folder, those paths count."""
    seen, found = set(), []
    for area in cfg.areas:
        for path, _anchor in areas.pack_of(cfg, area):
            rel = areas.rel(cfg, path)
            folder = _folder(rel)
            if rel in seen or path.name.lower() != "readme.md" or not folder or not path.is_file():
                continue
            seen.add(rel)
            held = [p for p in area.paths if p.endswith("/") and (folder + "/").startswith(p)]
            counted = [folder + "/"] if held else [p for p in area.paths if p.startswith(folder + "/")]
            if not counted:
                continue
            since = _last(cfg.root, rel, "%H")
            if since is None:
                continue
            n = _commits(cfg.root, since, counted)
            if n >= limit:
                found.append((rel, n, counted))
    return found


# --- cleaning ------------------------------------------------------------------------------------

def convention(cfg, name: str) -> str | None:
    """The folder under [naming] whose last part is name, for example docs/plans, when it exists."""
    for key in cfg.naming:
        folder = key.strip("/")
        if folder.rsplit("/", 1)[-1] == name and (cfg.root / folder).is_dir():
            return folder
    return None


_SPAN = re.compile(r"`([^`\n]+)`")


def pointers(text: str) -> list[str]:
    """The paths in backticks of a text: a string with a / or ending in .md, without spaces, without a URL,
    and not an absolute path, because /opt/... or ~/... names a machine and not this repository."""
    found = []
    for m in _SPAN.finditer(text):
        span = m.group(1).strip().split("#", 1)[0]
        if (not span or any(c.isspace() for c in span) or "://" in span or any(c in span for c in "<>*{}$")
                or span.startswith(("/", "~", "\\"))  # a path of a machine, not of this repository
                or not ("/" in span or span.lower().endswith(".md"))):
            continue
        if span not in found:
            found.append(span)
    return found


def names(name: str, text: str) -> bool:
    """True when the text names the file name, alone or at the end of a path."""
    return re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", text) is not None


def _inside(rel: str, folder: str) -> bool:
    return rel.startswith(folder + "/") and rel.lower().endswith(".md") and rel.rsplit("/", 1)[1] != "README.md"


def _texts(cfg, files) -> dict[str, str]:
    """The text of every Markdown file outside docs/archive/, without the list that amd map writes."""
    texts = {}
    for f in scan.markdown_files(cfg.root, files):
        if f.startswith(mapping.ARCHIVE):
            continue
        text = scan.read_text(cfg.root / f)
        span = mapping.find_block(text, mapping.TREE)
        texts[f] = text[:span[0]] + text[span[1]:] if span else text
    return texts


def _age(cfg, rel: str, today: datetime.date) -> int | None:
    m = re.match(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})", rel.rsplit("/", 1)[-1])
    if m:
        try:
            return (today - datetime.date(*map(int, m.groups()))).days
        except ValueError:
            pass
    stamp = _last(cfg.root, rel, "%at")
    if stamp is None or not stamp.isdigit():
        return None
    return (today - datetime.datetime.fromtimestamp(int(stamp)).date()).days


def _indexed(name: str, index: str) -> bool:
    m = re.match(r"^([A-Za-z]*)([0-9]+)", name)
    if not m:
        return names(name, index)
    prefix, digits = m.groups()
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(prefix)}0*{int(digits)}(?![0-9])", index) is not None


# --- the run -------------------------------------------------------------------------------------

def run(cfg, files, today: datetime.date | None = None):
    """(findings, checks). A finding is (kind, path, text). A check is (section, kind, the sentence when the
    check finds nothing), one for each check that ran: a check that [check] turns off, or whose folder does not
    exist, does not run."""
    today = today or datetime.date.today()
    root, c, items = cfg.root, cfg.check, cfg.start.items
    findings, checks = [], []
    in_git = scan.git(root, "rev-parse", "HEAD") is not None

    if c.folders:
        for folder in no_readme(files):
            findings.append(("no-readme", folder + "/", f"{folder}/ has source files and no README.md. "
                                                        f"Write one, or run /amd:area {folder}."))
        for folder in no_entry(cfg, files):
            findings.append(("no-entry", folder + "/", f"{folder}/ has source files and no [[area]] entry in "
                                                       f"atlasmd.toml lists it. Run /amd:area {folder}."))
        for area in cfg.areas:
            for path in area.paths:
                if not (root / path.rstrip("/")).exists():
                    findings.append(("dead-entry", path, f"the [[area]] \"{area.name}\" lists {path}, which does "
                                                         "not exist. Remove it or fix the path."))
        checks += [("growth", "no-readme", "every folder with source files has a README.md, in it or in a folder above it"),
                   ("growth", "no-entry", "every folder with source files is in the paths of an [[area]] entry"),
                   ("growth", "dead-entry", "every path of every [[area]] entry exists")]
    if c.stale_readme and in_git:
        for readme, n, counted in stale_readmes(cfg, c.stale_readme):
            findings.append(("stale-readme", readme, f"{readme} did not change in the last {n} commits that changed "
                                                     f"{_either(counted)}. Update its State section."))
        checks.append(("growth", "stale-readme",
                       f"every README.md under pack changed within the last {c.stale_readme} commits of its folder"))

    items_path = root / items
    items_text = scan.read_text(items_path) if items_path.is_file() else ""
    if c.dead_pointers and items_path.is_file():
        for span in pointers(items_text):
            target = Path(os.path.expanduser(span))
            if not (target if target.is_absolute() else root / target).exists():
                findings.append(("dead-pointer", span, f"{items} names {span}, which does not exist. "
                                                       "Fix the line or remove it."))
        checks.append(("cleaning", "dead-pointer", f"every path in backticks in {items} exists"))
    plans = convention(cfg, "plans") if c.plans else None
    if plans:
        for f in files:
            if _inside(f, plans) and not names(f.rsplit("/", 1)[1], items_text):
                findings.append(("orphan-plan", f, f"{f} is named by no line of {items}. Add a line, or move the "
                                                   f"plan to {mapping.ARCHIVE} if it is built."))
        checks.append(("cleaning", "orphan-plan", f"{items} names every plan in {plans}/"))
    notes = convention(cfg, "notes") if c.notes else None
    if notes:
        texts = _texts(cfg, files)
        for f in files:
            if not _inside(f, notes):
                continue
            name = f.rsplit("/", 1)[1]
            if any(names(name, text) for other, text in texts.items() if other != f):
                continue
            age = _age(cfg, f, today)
            if age is not None and age > c.notes:
                findings.append(("orphan-note", f, f"{f} is named by no Markdown file and is {age} days old. "
                                                   f"Point at it, or move it to {mapping.ARCHIVE}."))
        checks.append(("cleaning", "orphan-note",
                       f"a Markdown file outside {mapping.ARCHIVE} names every note in {notes}/ that is older "
                       f"than {c.notes} days"))
    decisions = convention(cfg, "decisions") if c.decisions else None
    if decisions:
        index_rel = f"{decisions}/README.md"
        index = scan.read_text(root / index_rel) if (root / index_rel).is_file() else ""
        for f in files:
            if _inside(f, decisions) and not _indexed(f.rsplit("/", 1)[1], index):
                findings.append(("no-index-line", f, f"{f} has no line in {index_rel}. Add the line."))
        checks.append(("cleaning", "no-index-line", f"{index_rel} has a line for every file in {decisions}/"))
    if c.stale_state and in_git:
        since = _last(root, cfg.start.state, "%H")
        if since is not None:
            n = _commits(root, since, [])
            if n >= c.stale_state:
                findings.append(("stale-state", cfg.start.state, f"{cfg.start.state} did not change in the last "
                                                                 f"{n} commits. Rewrite it with /amd:end."))
            checks.append(("cleaning", "stale-state",
                           f"{cfg.start.state} changed within the last {c.stale_state} commits"))
    return findings, checks
