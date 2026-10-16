#!/usr/bin/env python3
"""The command line of atlasmd: amd <command>.

Every command except setup and config prints plain text, and Claude can run it. setup
and config are screens and need a terminal. The launcher bin/amd runs this file.
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if sys.path and os.path.abspath(sys.path[0] or os.curdir) == _HERE:
    sys.path[0] = os.path.dirname(_HERE)      # run as a script: import the package, not its files
elif os.path.dirname(_HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(_HERE))

from atlasmd import __version__, areas, config, ledger, mapping, naming, scan, start, tui  # noqa: E402

COMMANDS = [
    ("setup", "set up atlasmd on a screen with five steps"),
    ("config", "show and change atlasmd.toml and your own settings"),
    ("scan", "list every Markdown file with its size in tokens"),
    ("init", "write atlasmd.toml and docs/start/, overwrite nothing"),
    ("check", "find problems in docs/start/, atlasmd.toml, file names"),
    ("map", "list every Markdown file in docs/start/10-map.md"),
    ("status", "show what this session read, and the last compaction"),
    ("why", "show the last edit that the hook refused, and why"),
    ("end", "show what is not committed or not pushed"),
    ("set <key> <value>", "write offer_setup or token_chars to your settings"),
    ("version", "print the version of atlasmd"),
]
OPTIONS = [
    ("scan --json", "the same as JSON, for a skill"),
    ("check --json", "the same as JSON, for a skill"),
    ("init --areas-json <file>", "add the [[area]] entries of a JSON file"),
    ("init --dry-run", "show what init writes, and write nothing"),
    ("status --session <id>", "the files that one session read"),
    ("status --agent <id>", "the files that a subagent of that session read"),
    ("why --session <id>", "the last refused edit of one session"),
]
ABOUT = ("atlasmd tells Claude which Markdown files to read at the start of a session, and refuses a change "
         "to a file in a listed folder until Claude has read the files listed for that folder.")

TEMPLATES = {
    "map": """# What this project is, and where its files are

One paragraph on what this project is, for a reader who knows nothing about it.

## Files to read before a change in each folder

<!-- atlasmd:areas -->
<!-- /atlasmd:areas -->

## Where each kind of fact lives

| Fact | Its place |
|---|---|
| a decision and its reason | `docs/decisions/`, one file per decision |
| the state of the work | `docs/start/20-open-items.md`, one line per item, with the path of the file that holds the details |
| a plan for work that a person asked for | `docs/plans/` |
| a dated note or a measurement | `docs/notes/` |

## Every Markdown file

<!-- atlasmd:tree -->
<!-- /atlasmd:tree -->
""",
    "open-items": """# Open items

One line per open item, with the path of the file that holds its details. Remove the line in the commit that closes the item.

- 
""",
    "state": """# Where things stand

Claude writes this file again at the end of every session, with /amd:end.

## Done since the last /amd:end

## What to look at

## Waiting on a person

## Next
""",
    "way-of-work": """# How to work in this project

The rules that Claude follows in every session of this project. Keep only what every session needs.

- Before you change a file in a folder that atlasmd.toml lists, read the files listed for that folder. The hook refuses the edit until you read them.
- If a file you read changes what you planned to do, follow the file and say so in your report.
""",
}
FOLDERS = ["docs/decisions", "docs/plans", "docs/notes", "docs/archive"]
HOST_NAMES = {"CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "SKILL.md"}
PERSONAL_KEYS = {"offer_setup": "yes or no", "token_chars": "a number above 0, for example 2.5"}


class Problem(Exception):
    """A plain sentence for the person, and the exit code."""

    def __init__(self, text, code=2):
        super().__init__(text)
        self.code = code


# ---------------------------------------------------------------- shared parts
def out(text=""):
    print(text)


def color():
    return tui.use_color()


def mark(ok):
    return tui.paint("✓", "accent", color()) if ok else tui.paint("✗", "problem", color())


def number(n):
    return f"{n:,}"


def load_config(cwd):
    """The configuration for cwd. Problem when there is none or it cannot be used."""
    path = config.find(cwd)
    if path is None:
        raise Problem(f"There is no atlasmd.toml in {cwd} or above it. Run amd init, or /amd:init in a session.", 1)
    try:
        return config.load(path)
    except config.ConfigError as exc:
        raise Problem(str(exc), 2)


def project_root(cwd):
    """The folder of atlasmd.toml, else the top of the git repository, else cwd."""
    path = config.find(cwd)
    if path is not None:
        return path.parent
    return scan.git_root(cwd) or Path(cwd)


def rel(root, path):
    """path relative to root, with / as the separator. Links and short names are resolved
    when the plain paths do not match, as /var and /private/var on macOS."""
    for resolve in (os.path.abspath, os.path.realpath):
        try:
            return Path(resolve(path)).relative_to(Path(resolve(root))).as_posix()
        except ValueError:
            continue
    return Path(path).as_posix()


def parse(args, flags=(), values=()):
    """(options, rest). flags take no value, values take one."""
    opts, rest, i = {}, [], 0
    while i < len(args):
        a = args[i]
        if a in flags:
            opts[a] = True
        elif a in values:
            if i + 1 >= len(args):
                raise Problem(f"{a} needs a value.")
            opts[a] = args[i + 1]
            i += 1
        elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in values:
            k, v = a.split("=", 1)
            opts[k] = v
        elif a.startswith("-"):
            raise Problem(f"The option {a} is not known here. Run amd for the commands.")
        else:
            rest.append(a)
        i += 1
    return opts, rest


# ---------------------------------------------------------------- personal settings
def personal_path():
    return Path(config.personal()["data_dir"]) / "settings.toml"


def read_personal():
    """The values in the personal settings file, or an empty dict."""
    import tomllib
    try:
        with open(personal_path(), "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return {k: v for k, v in data.items() if k in PERSONAL_KEYS}


def personal_value(key):
    """The value of a personal setting: the file first, then the default of config.personal()."""
    values = read_personal()
    return values[key] if key in values else config.personal()[key]


def parse_personal(key, value):
    if key not in PERSONAL_KEYS:
        raise Problem(f"The key {key} is not known. The keys are {' and '.join(PERSONAL_KEYS)}.")
    text = str(value).strip().lower()
    if key == "offer_setup":
        if text in ("yes", "true", "on", "1"):
            return True
        if text in ("no", "false", "off", "0"):
            return False
    else:
        try:
            n = float(text)
        except ValueError:
            n = 0
        if 0 < n <= 100:
            return round(n, 2)
    raise Problem(f"The value of {key} must be {PERSONAL_KEYS[key]}, not {value}.")


def save_personal(updates):
    values = read_personal()
    values.update(updates)
    path = personal_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# The personal settings of atlasmd. The command amd set <key> <value> writes this file."]
    for key in PERSONAL_KEYS:
        if key in values:
            v = values[key]
            lines.append(f"{key} = {'true' if v is True else 'false' if v is False else v}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------- help
def cmd_help():
    c = color()
    for line in tui.LOGO:
        out("  " + tui.paint(line, "accent", c))
    out("  " + tui.paint(tui.TAGLINE, "dim", c))
    out()
    for line in tui.textwrap.wrap(ABOUT, 76):
        out("  " + line)
    out()
    width = max(len("amd " + name) for name, _ in COMMANDS)
    for name, text in COMMANDS:
        out(f"  {tui.paint(('amd ' + name).ljust(width), 'bold', c)}  {text}")
    out()
    width = max(len("amd " + name) for name, _ in OPTIONS)
    for name, text in OPTIONS:
        out(f"  {('amd ' + name).ljust(width)}  {text}")
    out()
    out("  The skills in a Claude Code session:")
    out("  /amd:init  /amd:check  /amd:map  /amd:status  /amd:why  /amd:end")
    return 0


# ---------------------------------------------------------------- scan
def cmd_scan(cwd, args):
    opts, _ = parse(args, flags=("--json",))
    data = scan.scan(project_root(cwd))
    out(json.dumps(data, indent=2, ensure_ascii=False) if opts.get("--json") else scan.render(data))
    return 0


# ---------------------------------------------------------------- init
def load_areas(path, cwd):
    p = Path(path) if os.path.isabs(path) else Path(cwd) / path
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise Problem(f"atlasmd cannot read {p}: {exc.strerror or exc}.")
    except ValueError as exc:
        raise Problem(f"{p} is not valid JSON: {exc}.")
    if not isinstance(data, list):
        raise Problem(f"{p} must hold a JSON list of [[area]] entries, each with name, paths and pack.")
    result = []
    for n, item in enumerate(data, 1):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise Problem(f"Entry {n} in {p} must be an object with a name.")
        for key in ("paths", "pack"):
            value = item.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise Problem(f"In {p}, {key} of \"{item['name']}\" must be a list of paths.")
        extra = set(item) - {"name", "paths", "pack"}
        if extra:
            raise Problem(f"In {p}, \"{item['name']}\" has keys that are not known: {', '.join(sorted(extra))}.")
        result.append({"name": item["name"].strip(), "paths": item.get("paths", []), "pack": item.get("pack", [])})
    return result


def _toml_list(key, values):
    items = [json.dumps(v, ensure_ascii=False) for v in values]
    inline = f"{key} = [{', '.join(items)}]"
    if len(inline) <= 96:
        return inline
    return f"{key} = [\n" + "".join(f"  {i},\n" for i in items) + "]"


def areas_toml(items):
    blocks = []
    for a in items:
        blocks.append("\n".join(["[[area]]", f"name = {json.dumps(a['name'], ensure_ascii=False)}",
                                 _toml_list("paths", a["paths"]), _toml_list("pack", a["pack"])]))
    return "\n\n".join(blocks)


def exclude_file(root):
    """The info/exclude file of the git repository that holds root, or None."""
    out_ = scan.git(root, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    if out_ and out_.strip():
        return Path(out_.strip())
    git_dir = Path(root) / ".git"
    return git_dir / "info" / "exclude" if git_dir.is_dir() else None


def cmd_init(cwd, args):
    opts, _ = parse(args, flags=("--dry-run",), values=("--areas-json",))
    dry = bool(opts.get("--dry-run"))
    items = load_areas(opts["--areas-json"], cwd) if "--areas-json" in opts else []
    existing = config.find(cwd)
    root = existing.parent if existing else (scan.git_root(cwd) or Path(cwd))
    toml_path = root / config.CONFIG_NAME
    made, kept, notes = [], [], []

    if toml_path.is_file():
        try:
            cfg = config.load(toml_path)
        except config.ConfigError as exc:
            raise Problem(str(exc))
        kept.append(config.CONFIG_NAME)
        if items:
            notes.append(f"atlasmd.toml exists, so init did not add the {len(items)} [[area]] entries. "
                         "Copy them into atlasmd.toml by hand:\n\n" + areas_toml(items))
        new_text = None
    else:
        new_text = config.defaults_text().rstrip("\n") + "\n"
        if items:
            new_text += "\n" + areas_toml(items) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / config.CONFIG_NAME
            probe.write_text(new_text, encoding="utf-8")
            try:
                cfg = config.load(probe)
            except config.ConfigError as exc:
                raise Problem(f"With these [[area]] entries, atlasmd.toml is not valid, so init wrote nothing. {exc}")
        cfg.root, cfg.path = root, toml_path
        made.append(config.CONFIG_NAME + (f" with {len(items)} [[area]] entries" if items else ""))

    writes = []  # (path, text or None for a folder)
    if new_text is not None:
        writes.append((toml_path, new_text))
    start_dir = root / cfg.start.dir
    if start_dir.is_dir():
        kept.append(cfg.start.dir + "/")
    else:
        made.append(cfg.start.dir + "/")
    for target, name in ((cfg.start.map, "map"), (f"{cfg.start.dir}/20-open-items.md", "open-items"),
                         (cfg.start.state, "state"), (f"{cfg.start.dir}/40-way-of-work.md", "way-of-work")):
        path = root / target
        if path.exists():
            kept.append(target)
        else:
            made.append(target)
            writes.append((path, TEMPLATES[name]))
    for folder in FOLDERS:
        path = root / folder
        if path.is_dir():
            kept.append(folder + "/")
        else:
            made.append(folder + "/")
            writes.append((path, None))

    exclude_add = []
    if cfg.private:
        exclude = exclude_file(root)
        top = scan.git_root(root)
        if exclude is None or top is None:
            notes.append("This folder is not in a git repository, so init did not add the files under [private] "
                         "to .git/info/exclude.")
        else:
            present = set(exclude.read_text(encoding="utf-8").splitlines()) if exclude.is_file() else set()
            for p in cfg.private:
                line = "/" + rel(top, root / p)
                if line in present:
                    kept.append(f"{line} in {exclude.name}")
                else:
                    exclude_add.append(line)
                    made.append(f"{line} in {rel(root, exclude)}")

    if not dry:
        for path, text in writes:
            if text is None:
                path.mkdir(parents=True, exist_ok=True)
            elif not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
        if exclude_add:
            exclude = exclude_file(root)
            exclude.parent.mkdir(parents=True, exist_ok=True)
            before = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
            with open(exclude, "a", encoding="utf-8", newline="\n") as fh:
                if before and not before.endswith("\n"):
                    fh.write("\n")
                fh.write("# atlasmd: the files under [private] in atlasmd.toml\n" + "\n".join(exclude_add) + "\n")

    out(f"atlasmd init  {root}" + ("  (dry run: nothing written)" if dry else ""))
    out()
    out("To make:" if dry else "Made:")
    for m in made or ["nothing"]:
        out(f"  {m}")
    out()
    out("Left as it was:")
    for k in kept or ["nothing"]:
        out(f"  {k}")
    for note in notes:
        out()
        out(note)
    out()
    out(f"Next: write the text of the files in {cfg.start.dir}/, then run amd map and amd check.")
    return 0


# ---------------------------------------------------------------- check
def _prefix(path):
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    for i, ch in enumerate(p):
        if ch in "*?[":
            p = p[:i]
            break
    return p.rstrip("/")


def overlaps(cfg):
    found = []
    for i, a in enumerate(cfg.areas):
        for b in cfg.areas[i + 1:]:
            for pa in a.paths:
                for pb in b.paths:
                    x, y = _prefix(pa), _prefix(pb)
                    if x == y or not x or not y or x.startswith(y + "/") or y.startswith(x + "/"):
                        found.append((a.name, b.name, pa, pb))
    return found


def unread(cfg, md):
    """The Markdown files that no folder rule, no pack and no start reading covers."""
    root = cfg.root
    covered = {rel(root, p) for p in start.files(cfg)}
    for area in cfg.areas:
        covered.update(rel(root, p) for p, _anchor in areas.pack_of(cfg, area))
    covered.update(p.strip("/") for p in cfg.private)
    covered.add(cfg.start.map)
    covered.add(cfg.start.state)
    result = []
    for f in md:
        name = f.rsplit("/", 1)[-1]
        parts = f.split("/")
        if (f in covered or len(parts) == 1 or name in HOST_NAMES or any(p.startswith(".") for p in parts[:-1])
                or f.startswith(mapping.ARCHIVE) or naming.rule_for(cfg.naming, f)):
            continue
        result.append(f)
    return result


def map_outside(cfg):
    """True when start.map points at a file outside this project, such as another repository's map."""
    root = Path(cfg.root).resolve()
    target = (Path(cfg.root) / cfg.start.map).resolve()
    return root != target and root not in target.parents


def run_check(cfg):
    root = cfg.root
    findings = []

    def add(kind, text, path="", area=""):
        findings.append({"kind": kind, "path": path, "area": area, "text": text})

    composed = start.compose(cfg)
    chars = sum(len(scan.read_text(p).rstrip()) for p, _t in composed.files)
    given = sum(1 for p, _t in composed.files if f"\n\n## {areas.rel(cfg, p)}\n\n" in composed.text)
    budget = {"tokens": composed.tokens, "budget": cfg.start.budget, "over": composed.over_budget,
              "chars": chars, "char_limit": start.CONTEXT_LIMIT, "over_limit": bool(composed.over_limit),
              "inject": cfg.start.inject, "given": given,
              "files": [{"path": rel(root, p), "tokens": t} for p, t in composed.files]}
    if not composed.files and not cfg.start.also:
        where = "none of the files in start.files exists" if cfg.start.files else f"{cfg.start.dir}/ has no Markdown files"
        add("start", f"{where}, so Claude gets nothing at the start of a session. "
                     f"Run amd init, or list the {cfg.start.dir}/ folder of another project under start.also.",
            cfg.start.dir)
    if composed.over_budget:
        add("budget", f"the files that Claude gets at the start have about {number(composed.tokens)} tokens, more than "
                      f"the {number(cfg.start.budget)} in start.budget. So the hook gives Claude their list, not their text.")
    for area in cfg.areas:
        pack = areas.pack_of(cfg, area)
        if not pack:
            add("empty-pack", f"[[area]] \"{area.name}\" lists no files under pack, so the hook refuses no edit in its paths",
                area=area.name)
        for path, anchor in pack:
            if not path.is_file():
                add("missing-pack", f"{rel(root, path)} does not exist, but [[area]] \"{area.name}\" lists it under pack. "
                                    "The hook does not ask for a file that does not exist.",
                    rel(root, path), area.name)
    for a, b, pa, pb in overlaps(cfg):
        add("overlap", f"[[area]] \"{a}\" lists {pa} and [[area]] \"{b}\" lists {pb}. These paths overlap, so for a "
                       "file in both, the hook asks only for the files under pack of one of them", area=f"{a}, {b}")
    files = scan.all_files(root)
    md = scan.markdown_files(root, files)
    for f in naming.check(cfg.naming, md):
        add("naming", f"{f['path']}: {f['text']}" if f["path"] else f["text"], f["path"])
    for f in unread(cfg, md):
        add("unread", f"{f}: no rule says when Claude reads this file. It is not in {cfg.start.dir}/, not under pack, "
                      "and not in a folder under [naming]", f)
    map_file = root / cfg.start.map
    if map_outside(cfg):
        pass  # the map file belongs to another project, which checks it
    elif not map_file.is_file():
        add("map", f"{cfg.start.map}, the file in start.map, does not exist. Run amd init to make it.", cfg.start.map)
    else:
        for block in mapping.stale(cfg, files):
            what = "table of the [[area]] entries" if block == "areas" else "list of the Markdown files"
            add("map", f"the {what} in {cfg.start.map} is out of date. Run amd map.", cfg.start.map)
    return {"root": str(root), "ok": not findings, "problems": len(findings), "budget": budget, "findings": findings}


SECTIONS = [
    ("start", ("start", "budget")),
    ("folders", ("empty-pack", "missing-pack")),
    ("overlap", ("overlap",)),
    ("file names", ("naming",)),
    ("not read", ("unread",)),
    ("map file", ("map",)),
]
GOOD = {
    "folders": "every listed folder has files to read before a change there, and every one of those files exists",
    "overlap": "no file is under the paths of two [[area]] entries",
    "file names": "every file name matches the rule of its folder under [naming]",
    "not read": "every Markdown file in a subfolder is in {start}/, under pack, in a folder under [naming], "
                "or in docs/archive/",
    "map file": "{map} lists the Markdown files and the [[area]] entries as they are now",
}


def cmd_check(cwd, args):
    opts, _ = parse(args, flags=("--json",))
    cfg = load_config(cwd)
    result = run_check(cfg)
    if opts.get("--json"):
        out(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1
    b = result["budget"]
    label_w = max(len(s) for s, _ in SECTIONS)
    out(f"atlasmd check  {result['root']}")
    out()
    for section, kinds in SECTIONS:
        hits = [f for f in result["findings"] if f["kind"] in kinds]
        if section == "start":
            ok = not hits
            n = len(b["files"])
            out(f"{mark(ok)} {section.ljust(label_w)}  Claude gets {n} file{'s' if n != 1 else ''} at the start of a "
                "session" + (", some from start.also" if cfg.start.also else "") +
                f", about {number(b['tokens'])} tokens. start.budget is {number(b['budget'])}.")
            if not b["files"] and not hits:
                out(f"    Claude gets nothing at the start: {cfg.start.dir}/ and start.also hold no Markdown files.")
            if b["files"]:
                w = max(len(f["path"]) for f in b["files"])
                tw = max(len(number(f["tokens"])) for f in b["files"])
                for f in b["files"]:
                    out(f"    {f['path'].ljust(w)}  {number(f['tokens']).rjust(tw)}")
            if b["files"]:
                out(f"{mark(True)} {'characters'.ljust(label_w)}  {number(b['chars'])} in these files. "
                    f"Claude Code takes at most {number(b['char_limit'])} from a hook.")
                g = b["given"]
                if not b["inject"]:
                    out("    start.inject is false, so the hook gives Claude the list of the files, "
                        "and Claude reads each file with one Read.")
                elif g == n:
                    out("    So the hook gives Claude the text of every file.")
                elif g:
                    first = f"first {g} files" if g != 1 else "first file"
                    out(f"    So the hook gives Claude the text of the {first} and the list of the rest. "
                        "Claude reads each file of the list with one Read.")
                else:
                    out("    So the hook gives Claude the list of the files, and Claude reads each file with one Read.")
            for f in hits:
                out(f"{mark(False)} {section.ljust(label_w)}  {f['text']}")
            continue
        if not hits:
            if section == "folders" and not cfg.areas:
                out(f"{mark(True)} {section.ljust(label_w)}  atlasmd.toml has no [[area]] entries yet, "
                    "so the hook refuses no edit")
            elif section == "map file" and map_outside(cfg):
                out(f"{mark(True)} {section.ljust(label_w)}  {cfg.start.map} is in another project. Run amd check there.")
            else:
                out(f"{mark(True)} {section.ljust(label_w)}  "
                    f"{GOOD[section].format(start=cfg.start.dir, map=cfg.start.map)}")
        for f in hits:
            out(f"{mark(False)} {section.ljust(label_w)}  {f['text']}")
    out()
    n = result["problems"]
    out("No problems." if n == 0 else f"{n} problem{'s' if n != 1 else ''}.")
    return 0 if result["ok"] else 1


# ---------------------------------------------------------------- map
def cmd_map(cwd, args):
    parse(args)
    cfg = load_config(cwd)
    if map_outside(cfg):
        raise Problem(f"The map file of this project, {cfg.start.map}, is in another project. Run amd map there.")
    files = scan.all_files(cfg.root)
    result = mapping.write(cfg, files)
    md = [f for f in scan.markdown_files(cfg.root, files)]
    where = rel(cfg.root, result["path"])
    if result["changed"]:
        out(f"{mark(True)} wrote the list of {len(md)} Markdown files and the table of {len(cfg.areas)} [[area]] entries "
            f"into {where}")
    else:
        out(f"{mark(True)} {where} already has the list of {len(md)} Markdown files and the table of "
            f"{len(cfg.areas)} [[area]] entries. Nothing changed.")
    for m in result["added"]:
        out(f"  The marker {m} was missing, so amd map added both markers and the text between them "
            "at the end of the file.")
    return 0


# ---------------------------------------------------------------- ledgers
def _when(text):
    try:
        return datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def ledgers():
    """[(mtime, data)] of every ledger file, newest first."""
    folder = Path(ledger.data_dir()) / "ledgers"
    found = []
    if folder.is_dir():
        for path in folder.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    found.append((path.stat().st_mtime, data))
            except (OSError, ValueError):
                continue
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def select_ledger(opts):
    """The key and data of the ledger that --session and --agent name, else of the newest."""
    session, agent = opts.get("--session"), opts.get("--agent")
    if session:
        key = ledger.key({"session_id": session, "agent_id": agent})
        for _mtime, data in ledgers():
            if data.get("session_id") == session and (data.get("agent_id") or None) == (agent or None):
                return key, data
        return key, None
    found = ledgers()
    if not found:
        return None, None
    data = found[0][1]
    return ledger.key({"session_id": data.get("session_id"), "agent_id": data.get("agent_id")}), data


def last_compaction(root=None):
    path = Path(ledger.data_dir()) / "compacts.log"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    fallback = None
    for line in reversed(lines):
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        entry = {"time": parts[0], "cwd": parts[1], "trigger": parts[2], "chars": parts[3]}
        fallback = fallback or entry
        if root is None or config.norm(parts[1]).startswith(config.norm(root)):
            return entry
    return fallback if root is None else None


def cmd_status(cwd, args):
    opts, _ = parse(args, values=("--session", "--agent"))
    key, data = select_ledger(opts)
    path = config.find(cwd)
    cfg = None
    if path:
        try:
            cfg = config.load(path)
        except config.ConfigError as exc:
            raise Problem(str(exc))
    if key is None:
        out("No session has read a file yet. The hook starts the list of read files at the first Read of a session.")
    elif data is None:
        out(f"The hook has no list of read files for the session {opts.get('--session')}" +
            (f" and the agent {opts.get('--agent')}." if opts.get("--agent") else "."))
    else:
        who = f"session {data.get('session_id')}" + (f", agent {data.get('agent_id')}" if data.get("agent_id") else "")
        out(f"atlasmd status  {who}" + ("" if opts.get("--session") else "  (the last session that read a file)"))
        out()
        read = ledger.read_paths(key)
        if cfg is None:
            out(f"There is no atlasmd.toml in {cwd} or above it, so there are no listed folders to show.")
        elif not cfg.areas:
            out("atlasmd.toml has no [[area]] entries yet, so the hook refuses no edit.")
        else:
            full, part, none = [], [], []
            for area in cfg.areas:
                pack = [p for p, _a in areas.pack_of(cfg, area) if p.is_file()]  # as the guard counts it
                missing = [p for p in pack if config.norm(p) not in read]
                if not pack:
                    continue
                if not missing:
                    full.append((area, pack, missing))
                elif len(missing) < len(pack):
                    part.append((area, pack, missing))
                else:
                    none.append((area, pack, missing))
            w = max(len(a.name) for a in cfg.areas)
            out("Each [[area]] in atlasmd.toml lists under pack the files to read before an edit in its paths.")
            out()
            out("Read all files under pack")
            for area, pack, _m in full or []:
                out(f"  {mark(True)} {area.name.ljust(w)}  {len(pack)} file{'s' if len(pack) != 1 else ''}")
            if not full:
                out("  none")
            out("Read some files under pack")
            for area, pack, missing in part:
                out(f"  {mark(False)} {area.name.ljust(w)}  {len(pack) - len(missing)} of {len(pack)} files. Not read:")
                for p in missing:
                    out(f"      {rel(cfg.root, p)}")
            if not part:
                out("  none")
            out("Read no file under pack")
            out("  " + (", ".join(a.name for a, _p, _m in none) if none else "none"))
            touched = []
            refusals = " ".join(r.get("text", "") for r in data.get("refusals", []) if isinstance(r, dict))
            for area in cfg.areas:
                in_code = any(areas.area_of(cfg, p) is area for p in read)
                if in_code or f"\"{area.name}\"" in refusals or f" {area.name}" in refusals:
                    touched.append(area.name)
            out("[[area]] entries with a file read in their paths, or with a refused edit")
            out("  " + (", ".join(touched) if touched else "none"))
        n = len(data.get("refusals", []))
        out(f"Refused edits  {n}" + ("  (amd why shows the last one)" if n else ""))
    c = last_compaction(cfg.root if cfg else None)
    out()
    if c:
        out(f"Last compaction  {c['time']}  {c['trigger']}  a summary of {number(int(c['chars']) if c['chars'].isdigit() else 0)} characters")
    else:
        out("Last compaction  none in compacts.log" + (" for this project" if cfg else ""))
    return 0


def cmd_why(cwd, args):
    opts, _ = parse(args, values=("--session", "--agent"))
    candidates = []
    for _mtime, data in ledgers():
        if opts.get("--session") and data.get("session_id") != opts["--session"]:
            continue
        if opts.get("--agent") and data.get("agent_id") != opts["--agent"]:
            continue
        refusals = [r for r in data.get("refusals", []) if isinstance(r, dict) and r.get("text")]
        if refusals:
            candidates.append((_when(refusals[-1].get("time")), data))
    if not candidates:
        where = f" for the session {opts['--session']}" if opts.get("--session") else ""
        out(f"No refused edit{where} in the last 14 days. The hook keeps the lists of read files and refused edits "
            "for 14 days.")
        return 0
    candidates.sort(key=lambda c: c[0].timestamp() if c[0] else 0, reverse=True)
    data = candidates[0][1]
    key = ledger.key({"session_id": data.get("session_id"), "agent_id": data.get("agent_id")})
    text = ledger.last_refusal(key) or data["refusals"][-1]["text"]
    who = f"session {data.get('session_id')}" + (f", agent {data.get('agent_id')}" if data.get("agent_id") else "")
    out(f"The last refused edit  {data['refusals'][-1].get('time', '')}  {who}")
    out()
    out(text)
    out()
    path = config.find(cwd)
    mode = ""
    if path:
        try:
            mode = config.load(path).guard.mode
        except config.ConfigError:
            mode = ""
    out(f"guard.mode in atlasmd.toml is {mode}." if mode else "guard.mode in atlasmd.toml sets what the hook does.")
    out("With deny, the hook refuses the edit. With remind, it permits the edit and tells Claude the files to read. "
        "With off, it does not look at edits.")
    return 0


# ---------------------------------------------------------------- end
def cmd_end(cwd, args):
    parse(args)
    root = scan.git_root(cwd)
    if root is None:
        raise Problem(f"{cwd} is not in a git repository, so amd end has nothing to show.", 1)
    problems = 0
    out(f"atlasmd end  {root}")
    out()
    status = [line for line in (scan.git(root, "status", "--short") or "").splitlines() if line.strip()]
    if status:
        problems += 1
        out(f"{mark(False)} not committed  {len(status)} change{'s' if len(status) != 1 else ''}")
        for line in status:
            out(f"    {line}")
    else:
        out(f"{mark(True)} committed      every change is committed")
    upstream = scan.git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream is None:
        remotes = (scan.git(root, "remote") or "").split()
        branch = (scan.git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
        if remotes:
            problems += 1
            remote = "origin" if "origin" in remotes else remotes[0]
            out(f"{mark(False)} not pushed     the branch {branch} has no upstream branch. Push it with:")
            out(f"    git push -u {remote} {branch}")
        else:
            out(f"{mark(True)} pushed         the repository has no remote, so there is nothing to push")
    else:
        log = [line for line in (scan.git(root, "log", "--oneline", "@{u}..") or "").splitlines() if line.strip()]
        if log:
            problems += 1
            out(f"{mark(False)} not pushed     {len(log)} commit{'s' if len(log) != 1 else ''} not on {upstream.strip()}")
            for line in log:
                out(f"    {line}")
        else:
            out(f"{mark(True)} pushed         every commit is on {upstream.strip()}")
    out()
    path = config.find(cwd)
    if path:
        try:
            cfg = config.load(path)
        except config.ConfigError as exc:
            raise Problem(str(exc))
        out("The first message for a fresh chat, from start.line in atlasmd.toml:")
        out()
        out(cfg.start.line)
        out()
        out(f"The file that says where the work stands, from start.state: "
            f"{Path(os.path.abspath(cfg.root / cfg.start.state))}")
    else:
        out("There is no atlasmd.toml here, so there is no first message from start.line. Run amd init.")
    return 1 if problems else 0


# ---------------------------------------------------------------- set
def cmd_set(cwd, args):
    _, rest = parse(args)
    if len(rest) != 2:
        raise Problem("amd set takes a key and a value: amd set offer_setup no, or amd set token_chars 2.5.")
    key, value = rest[0], parse_personal(rest[0], rest[1])
    path = save_personal({key: value})
    shown = "yes" if value is True else "no" if value is False else value
    out(f"{key} = {shown}  (saved to {path})")
    return 0


# ---------------------------------------------------------------- screens
def cmd_screen(name):
    try:
        import curses  # noqa: F401
    except ImportError as exc:
        out(f"amd setup and amd config need the curses module, and this Python has none ({exc}).")
        out("On Windows, run: pip install windows-curses. Every other command of amd works without it.")
        return 2
    message = tui.needs_terminal(name)
    if message:
        out(message)
        return 2
    if name == "setup":
        from atlasmd import setup
        return setup.run()
    from atlasmd import screen
    return screen.run()


# ---------------------------------------------------------------- main
def main(argv=None, cwd=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cwd = Path(os.path.abspath(cwd or os.getcwd()))
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(errors="replace")
            except (AttributeError, ValueError):
                pass
    if not argv or argv[0] in ("-h", "--help", "help"):
        return cmd_help()
    cmd, args = argv[0], argv[1:]
    handlers = {"scan": cmd_scan, "init": cmd_init, "check": cmd_check, "map": cmd_map, "status": cmd_status,
                "why": cmd_why, "end": cmd_end, "set": cmd_set}
    try:
        if cmd in handlers:
            return handlers[cmd](cwd, args)
        if cmd in ("setup", "config"):
            parse(args)
            return cmd_screen(cmd)
        if cmd in ("version", "--version"):
            out(__version__)
            return 0
        raise Problem(f"amd has no command {cmd}. Run amd for the commands.")
    except Problem as exc:
        print(str(exc), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
