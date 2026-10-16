"""The settings of a project, from its atlasmd.toml, and the personal settings of the plugin.

The command line and the hook both use this module, so its names are a contract.
"""
from __future__ import annotations

import os
import pathlib
import re
import tomllib
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
    """The settings of the person, not of the project: settings.toml under the data folder, which
    `amd set` writes, and the environment of the hook, which wins for offer_setup."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    data_dir = pathlib.Path(data) if data else pathlib.Path.home() / ".claude" / "plugins" / "data" / "amd"
    offer, token_chars = True, 2.5
    try:
        with open(data_dir / "settings.toml", "rb") as handle:
            stored = tomllib.load(handle)
        if isinstance(stored.get("offer_setup"), bool):
            offer = stored["offer_setup"]
        number = stored.get("token_chars")
        if isinstance(number, (int, float)) and not isinstance(number, bool) and number > 0:
            token_chars = float(number)
    except (OSError, tomllib.TOMLDecodeError):
        pass
    value = os.environ.get("CLAUDE_PLUGIN_OPTION_OFFER_SETUP")
    if value is not None:
        offer = value.strip().lower() not in ("false", "0", "no", "off", "")
    return {"offer_setup": offer, "data_dir": data_dir, "token_chars": token_chars}


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
# The Markdown files that Claude gets at the start of a session and after each compaction.
dir = "docs/start"                 # Claude gets the Markdown files of this folder, in name order
files = []                         # or a list of paths, in order. When this list has paths, dir is not used
also = []                          # more folders or files, given after the files above. For example, docs/start/ of a second repository
budget = 30000                     # the limit in estimated tokens. Above it, Claude gets the list of the files and a warning, not their text
inject = true                      # false: Claude always gets the list of the files and reads them, never their text from the hook
state = "docs/start/30-state.md"   # the file that says where the work stands. /amd:end writes it again
map = "docs/start/10-map.md"       # the map file. amd map writes every Markdown file and every [[area]] into it. A subagent gets it at its start
line = "Say where things stand."   # the first message that a person sends in a fresh chat. amd end prints it

[guard]
# Before an edit of a file in the paths of an [[area]], the hook looks at which files under pack Claude has read in this session.
mode = "deny"                      # deny: refuse the edit until Claude reads them. remind: permit it and name the files. off: do not look
bash = true                        # true: the hook also looks at the Bash commands that write a file

[agents]
inject = "map"                     # what a subagent gets at its start: map (the file in start.map), start (the files above) or none

[private]
files = []                         # Markdown files that Claude gets at the start but that git never commits. amd init adds them to .git/info/exclude

[naming]
# For each folder, the regular expression that a file name must match. amd check examines these names. The hook does not.
"docs/start" = "^[0-9]{2}-[a-z0-9-]+\\.md$"
"docs/decisions" = "^P[0-9]{3}-[a-z0-9-]+\\.md$"
"docs/notes" = "^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]+\\.md$"
"docs/plans" = "^[a-z0-9-]+\\.md$"

# Each [[area]] lists folders or files under paths, and under pack the files that Claude must read
# before it changes a file in those paths. The hook refuses the edit until Claude reads them in this session.
# A path that ends in / is a folder. A path without / at its end is one file.
# A pack entry can end in #<anchor>. Then the refusal names that section of the file, and a read of the file counts.
# Remove the # signs below to use this example.
#
# [[area]]
# name = "the scrubber"
# paths = ["services/scrubber/scrubber/", "services/scrubber/policy/"]
# pack = ["services/scrubber/README.md", "docs/decisions/P008-default-policy.md", "docs/product-decisions.md#P15"]
'''
