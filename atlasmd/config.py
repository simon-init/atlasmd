"""The settings of a project, from its atlasmd.toml, and the personal settings of the plugin.

The command line and the hook both use this module, so its names are a contract.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass, field

CONFIG_NAME = "atlasmd.toml"

DEFAULT_NAMING = {
    "docs/start": r"^[0-9]{2}-[a-z0-9-]+\.md$",
    "docs/decisions": r"^P[0-9]{3}-[a-z0-9-]+\.md$",
    "docs/notes": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+\.md$",
    "docs/plans": r"^[a-z0-9-]+\.md$",
}

GUARD_MODES = ("deny", "remind", "off")
AGENT_INJECT = ("map", "start", "none")


class ConfigError(Exception):
    """atlasmd.toml cannot be used. The message is one plain sentence for a person."""


@dataclass
class Start:
    dir: str = "docs/start"
    files: list[str] = field(default_factory=list)
    also: list[str] = field(default_factory=list)
    budget: int = 30000
    inject: bool = True
    state: str = "docs/start/30-state.md"
    map: str = "docs/start/10-map.md"
    line: str = "Say where things stand."


@dataclass
class Guard:
    mode: str = "deny"
    bash: bool = True


@dataclass
class Agents:
    inject: str = "map"


@dataclass
class Area:
    name: str
    paths: list[str] = field(default_factory=list)
    pack: list[str] = field(default_factory=list)


@dataclass
class Config:
    root: pathlib.Path
    path: pathlib.Path
    start: Start = field(default_factory=Start)
    guard: Guard = field(default_factory=Guard)
    agents: Agents = field(default_factory=Agents)
    private: list[str] = field(default_factory=list)
    naming: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_NAMING))
    areas: list[Area] = field(default_factory=list)


def norm(path: str | os.PathLike) -> str:
    """One form of a path for comparison: absolute, links resolved, and on Windows in lower case."""
    return os.path.normcase(os.path.realpath(os.path.expanduser(os.fspath(path))))


def find(path: str | os.PathLike) -> pathlib.Path | None:
    """The nearest atlasmd.toml upward from a file or folder, then the one in CLAUDE_PROJECT_DIR, else None.

    The path does not have to exist: a Write can create a new file.
    """
    start = pathlib.Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    if not start.is_dir():
        start = start.parent
    for folder in (start, *start.parents):
        candidate = folder / CONFIG_NAME
        if candidate.is_file():
            return candidate
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        candidate = pathlib.Path(project) / CONFIG_NAME
        if candidate.is_file():
            return pathlib.Path(os.path.abspath(candidate))
    return None


def personal() -> dict:
    """The settings of the person, not of the project: from the environment of the hook."""
    value = os.environ.get("CLAUDE_PLUGIN_OPTION_OFFER_SETUP")
    offer = True if value is None else value.strip().lower() not in ("false", "0", "no", "off", "")
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    data_dir = pathlib.Path(data) if data else pathlib.Path.home() / ".claude" / "plugins" / "data" / "amd"
    return {"offer_setup": offer, "data_dir": data_dir, "token_chars": 2.5}


# --- loading -----------------------------------------------------------------------------------

_KEYS = {
    "start": {"dir", "files", "also", "budget", "inject", "state", "map", "line"},
    "guard": {"mode", "bash"},
    "agents": {"inject"},
    "private": {"files"},
    "naming": None,  # any folder can be a key
    "area": {"name", "paths", "pack"},
}


def _string(value, where: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"In {CONFIG_NAME}, {where} must be text in quotes.")
    return value


def _path(value, where: str) -> str:
    text = _string(value, where).strip()
    if not text:
        raise ConfigError(f"In {CONFIG_NAME}, {where} is empty.")
    if "\\" in text:
        raise ConfigError(f"In {CONFIG_NAME}, {where} must use / as the separator: \"{text}\".")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise ConfigError(f"In {CONFIG_NAME}, {where} must be relative to the folder of {CONFIG_NAME}: \"{text}\".")
    while text.startswith("./"):
        text = text[2:]
    return text


def _paths(value, where: str) -> list[str]:
    if not isinstance(value, list):
        raise ConfigError(f"In {CONFIG_NAME}, {where} must be a list of paths in square brackets.")
    return [_path(item, where) for item in value]


def _bool(value, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"In {CONFIG_NAME}, {where} must be true or false.")
    return value


def _choice(value, where: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        names = ", ".join(choices[:-1]) + " or " + choices[-1]
        raise ConfigError(f"In {CONFIG_NAME}, {where} must be {names}, not \"{value}\".")
    return value


def _table(data: dict, name: str) -> dict:
    table = data.get(name, {})
    if not isinstance(table, dict):
        raise ConfigError(f"In {CONFIG_NAME}, [{name}] must be a table.")
    allowed = _KEYS[name]
    if allowed is not None:
        for key in table:
            if key not in allowed:
                raise ConfigError(f"In {CONFIG_NAME}, the key \"{key}\" in [{name}] is not known.")
    return table


def load(config_path: str | os.PathLike) -> Config:
    """Read atlasmd.toml. Raise ConfigError with a plain sentence when the file cannot be used."""
    try:
        import tomllib
    except ImportError:  # Python 3.10 or older
        raise ConfigError("atlasmd needs Python 3.11 or newer to read atlasmd.toml.") from None
    path = pathlib.Path(os.path.abspath(os.fspath(config_path)))
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"There is no {CONFIG_NAME} at {path}.") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_NAME} at {path} is not valid TOML: {exc}.") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"atlasmd cannot read {path}: {exc}.") from None

    for name in data:
        if name not in _KEYS:
            raise ConfigError(f"In {CONFIG_NAME}, the table [{name}] is not known.")

    cfg = Config(root=path.parent, path=path)

    table = _table(data, "start")
    start = cfg.start
    if "dir" in table:
        start.dir = _path(table["dir"], "[start] dir")
    if "files" in table:
        start.files = _paths(table["files"], "[start] files")
    if "also" in table:
        start.also = _paths(table["also"], "[start] also")
    if "budget" in table:
        budget = table["budget"]
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise ConfigError(f"In {CONFIG_NAME}, [start] budget must be a whole number above 0.")
        start.budget = budget
    if "inject" in table:
        start.inject = _bool(table["inject"], "[start] inject")
    for key in ("state", "map"):
        if key in table:
            setattr(start, key, _path(table[key], f"[start] {key}"))
    if "line" in table:
        start.line = _string(table["line"], "[start] line")

    table = _table(data, "guard")
    if "mode" in table:
        cfg.guard.mode = _choice(table["mode"], "[guard] mode", GUARD_MODES)
    if "bash" in table:
        cfg.guard.bash = _bool(table["bash"], "[guard] bash")

    table = _table(data, "agents")
    if "inject" in table:
        cfg.agents.inject = _choice(table["inject"], "[agents] inject", AGENT_INJECT)

    table = _table(data, "private")
    if "files" in table:
        cfg.private = _paths(table["files"], "[private] files")

    if "naming" in data:
        table = _table(data, "naming")
        naming = {}
        for folder, pattern in table.items():
            where = f"[naming] \"{folder}\""
            _string(pattern, where)
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f"In {CONFIG_NAME}, {where} is not a valid regular expression: {exc}.") from None
            naming[folder.strip("/")] = pattern
        cfg.naming = naming

    areas = data.get("area", [])
    if not isinstance(areas, list):
        raise ConfigError(f"In {CONFIG_NAME}, each area must start with [[area]], with two square brackets.")
    seen = set()
    for number, item in enumerate(areas, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"In {CONFIG_NAME}, area {number} must be a table under [[area]].")
        for key in item:
            if key not in _KEYS["area"]:
                raise ConfigError(f"In {CONFIG_NAME}, the key \"{key}\" in area {number} is not known.")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"In {CONFIG_NAME}, area {number} has no name.")
        name = name.strip()
        if name in seen:
            raise ConfigError(f"In {CONFIG_NAME}, two areas have the name \"{name}\".")
        seen.add(name)
        where = f"the area \"{name}\""
        paths = _paths(item.get("paths", []), f"paths of {where}")
        pack = _paths(item.get("pack", []), f"pack of {where}")
        cfg.areas.append(Area(name=name, paths=paths, pack=pack))
    return cfg


def defaults_text() -> str:
    """The text of a default atlasmd.toml, which `amd init` writes."""
    return _DEFAULTS_TEXT


_DEFAULTS_TEXT = r'''# The settings of atlasmd for this project.
# Every path is relative to the folder of this file, with / as the separator.

[start]
# The start reading: the files that a session reads at its start and after each compaction.
dir = "docs/start"                 # the files of this folder, in name order, are the start reading
files = []                         # or a list of paths, in order. When this list has paths, dir is not used
also = []                          # more folders or files, read after the files above. For example, the start folder of a second repository
budget = 30000                     # the limit in tokens, estimated. Above it, the hook gives the list of files and a warning, not their content
inject = true                      # false: the hook gives the list of files and tells the agent to read them, never their content
state = "docs/start/30-state.md"   # the file that the ending writes again
map = "docs/start/10-map.md"       # the map, which a subagent gets at its start
line = "Say where things stand."   # the message that a person sends to a fresh chat

[guard]
mode = "deny"                      # deny, remind or off
bash = true                        # true: the guard also looks at the Bash commands that write a file

[agents]
inject = "map"                     # map, start or none: what a subagent gets at its start

[private]
files = []                         # Markdown files of the start reading that git never commits

[naming]
# For each folder, the regular expression that a file name must match. The command line examines these names, the hook does not.
"docs/start" = "^[0-9]{2}-[a-z0-9-]+\\.md$"
"docs/decisions" = "^P[0-9]{3}-[a-z0-9-]+\\.md$"
"docs/notes" = "^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+\\.md$"
"docs/plans" = "^[a-z0-9-]+\\.md$"

# An area is one part of the project. It has code paths and a pack.
# The pack is the list of files to read before a change in the area.
# A path that ends in / is a folder. A path without / at its end is one file.
# A pack entry can end in #<anchor>. Then it names one section of the file.
# Remove the # signs below to use this example.
#
# [[area]]
# name = "the scrubber"
# paths = ["services/scrubber/scrubber/", "services/scrubber/policy/"]
# pack = ["services/scrubber/README.md", "docs/decisions/P008-default-policy.md", "docs/product-decisions.md#P15"]
'''
