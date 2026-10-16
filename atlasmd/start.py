"""The start reading: the files that a session reads at its start, composed into one text, measured, and limited."""
from __future__ import annotations

import math
import os
import pathlib
from dataclasses import dataclass, field

from atlasmd import areas, projects
from atlasmd.config import Config, norm, personal

# Claude Code puts at most 10,000 characters of a hook's additionalContext into the context.
# Above that it writes the text to a file and gives the model a preview of 2,000 characters only.
CONTEXT_LIMIT = 10000

GUARD_LINE = ("Before you change a file in a folder that atlasmd.toml lists, read the files it names for that folder. "
              "Until you do, every Edit and Write of that file is refused. If what you read changes your mind about how to do it, do it the way you now think is right, and say in your report what changed and why. "
              "A new Markdown file takes the name rule of its folder, under [naming] in atlasmd.toml. A new folder "
              "with code gets a README.md and an [[area]] entry in atlasmd.toml in the same commit. A built plan "
              "moves to docs/archive/. An open item is one line that leaves when it closes.")


@dataclass
class Composed:
    text: str                        # what the hook injects. Empty when there is no start reading
    tokens: int                      # the estimated tokens of the files
    over_budget: bool
    files: list[tuple[pathlib.Path, int]] = field(default_factory=list)   # each file with its estimated tokens
    over_limit: bool = False         # the content is longer than CONTEXT_LIMIT, so the text is the list
    others: list[str] = field(default_factory=list)   # the names of the other repositories of the group


def estimate_tokens(text: str, token_chars=2.5) -> int:
    return math.ceil(len(text) / token_chars) if text else 0


def _markdown_in(folder: pathlib.Path) -> list[pathlib.Path]:
    try:
        entries = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".") and p.suffix.lower() == ".md"]
    except OSError:
        return []
    return sorted(entries, key=lambda p: p.name)


def _expand(cfg: Config, entry: str) -> list[pathlib.Path]:
    path = pathlib.Path(os.path.abspath(cfg.root / entry))
    if path.is_dir():
        return _markdown_in(path)
    return [path] if path.is_file() else []


def own_files(cfg: Config) -> list[pathlib.Path]:
    """The files of [start] files, or of the [start] dir folder in name order. Not [start] also."""
    return [p for entry in cfg.start.files for p in _expand(cfg, entry)] if cfg.start.files else _expand(cfg, cfg.start.dir)


def files(cfg: Config) -> list[pathlib.Path]:
    """The start reading in order: the files of [start] files, or of the [start] dir folder in name order, then [start] also."""
    result, seen = [], set()
    for path in own_files(cfg) + [p for entry in cfg.start.also for p in _expand(cfg, entry)]:
        if norm(path) not in seen:
            seen.add(norm(path))
            result.append(path)
    return result


def with_group(cfg: Config) -> tuple[list[pathlib.Path], list[Config]]:
    """The start reading of cfg, then the files of [start] files or [start] dir of every other repository of
    its group, in the order of their names. Each file once. The other repositories come as a second list."""
    result = files(cfg)
    seen = {norm(path) for path in result}
    others = projects.others(cfg)
    for other in others:
        for path in own_files(other):
            if norm(path) not in seen:
                seen.add(norm(path))
                result.append(path)
    return result, others


def _read(path: pathlib.Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read().rstrip()


def _count(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def _head(cfg: Config, count: int, tokens: int, others: list[Config]) -> str:
    if not others:
        return f"atlasmd: {cfg.root.name} has {_count(count)} to read at the start, about {tokens:,} tokens."
    more = "1 more repository" if len(others) == 1 else f"{len(others)} more repositories"
    return (f"atlasmd: {cfg.root.name} and {more} of the group \"{cfg.group}\" have {_count(count)} to read at the "
            f"start, about {tokens:,} tokens.")


def compose(cfg: Config) -> Composed:
    token_chars = personal()["token_chars"]
    paths, others = with_group(cfg)
    names = [other.root.name for other in others]
    contents = [_read(path) for path in paths]
    measured = [(path, estimate_tokens(text, token_chars)) for path, text in zip(paths, contents)]
    tokens = sum(n for _, n in measured)
    over_budget = tokens > cfg.start.budget
    if not paths:
        return Composed(text="", tokens=0, over_budget=False, files=[], others=names)

    head = f"{_head(cfg, len(paths), tokens, others)}\n{GUARD_LINE}"
    full = head + "".join(f"\n\n## {areas.rel(cfg, path)}\n\n{text}" for path, text in zip(paths, contents))
    over_limit = len(full) > CONTEXT_LIMIT
    if cfg.start.inject and not over_budget and not over_limit:
        return Composed(text=full, tokens=tokens, over_budget=False, files=measured, others=names)

    if cfg.start.inject and not over_budget and over_limit:
        # The content of the first files, as far as the limit lets, then the list of the rest.
        body, given = head, []
        for (path, n), text in zip(measured, contents):
            block = f"\n\n## {areas.rel(cfg, path)}\n\n{text}"
            room = CONTEXT_LIMIT - 400 - 120 * (len(measured) - len(given) - 1)
            if len(body) + len(block) > room:
                break
            body += block
            given.append(path)
        rest = [(path, n) for path, n in measured if path not in given]
        if given and rest:
            lines = [body, "", "The files above are in this context. Read the rest now, in this order:"]
            lines += [f"- {areas.rel(cfg, path)}, about {n} tokens" for path, n in rest]
            lines.append(f"All the files have {len(full)} characters, and Claude Code takes at most "
                         f"{CONTEXT_LIMIT} characters from a hook, so the rest comes through your reads.")
            text = "\n".join(lines)
            if len(text) <= CONTEXT_LIMIT:
                return Composed(text=text, tokens=tokens, over_budget=False, files=measured, over_limit=True,
                                others=names)

    lines = [head, "Read these files now, in this order:"]
    lines += [f"- {areas.rel(cfg, path)}, about {n} tokens" for path, n in measured]
    if over_budget:
        lines.append(f"These files have about {tokens:,} tokens, over the budget of {cfg.start.budget:,} in atlasmd.toml. "
                     "Move what is not needed at every start out of docs/start/.")
    elif cfg.start.inject:
        lines.append(f"These files have {len(full)} characters, and Claude Code takes at most {CONTEXT_LIMIT} "
                     "characters from a hook, so you get this list and read the files.")
    return Composed(text="\n".join(lines), tokens=tokens, over_budget=over_budget, files=measured,
                    over_limit=over_limit, others=names)


def compose_map(cfg: Config) -> str:
    """The map alone, for a subagent at its start. Empty when the map file does not exist."""
    path = pathlib.Path(os.path.abspath(cfg.root / cfg.start.map))
    if not path.is_file():
        return ""
    text = _read(path)
    tokens = estimate_tokens(text, personal()["token_chars"])
    head = (f"atlasmd: {areas.rel(cfg, path)} of {cfg.root.name}, about {tokens} tokens. It says what the project is, "
            f"which files to read before a change in each listed folder, and where every Markdown file is.\n{GUARD_LINE}")
    full = f"{head}\n\n## {areas.rel(cfg, path)}\n\n{text}"
    if len(full) <= CONTEXT_LIMIT:
        return full
    return f"{head}\nRead the map now: {areas.rel(cfg, path)}, about {tokens} tokens."
