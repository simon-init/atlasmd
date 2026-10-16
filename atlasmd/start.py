"""The start reading: the files that a session reads at its start, composed into one text, measured, and limited."""
from __future__ import annotations

import math
import os
import pathlib
from dataclasses import dataclass, field

from atlasmd import areas
from atlasmd.config import Config, norm, personal

# Claude Code puts at most 10,000 characters of a hook's additionalContext into the context.
# Above that it writes the text to a file and gives the model a preview of 2,000 characters only.
CONTEXT_LIMIT = 10000

GUARD_LINE = ("Read an area's guide before you change the area: the guard refuses an edit until the guide was read. "
              "When a file you read for an area changes what you were about to do, do what you read and say so in your report.")


@dataclass
class Composed:
    text: str                        # what the hook injects. Empty when there is no start reading
    tokens: int                      # the estimated tokens of the files
    over_budget: bool
    files: list[tuple[pathlib.Path, int]] = field(default_factory=list)   # each file with its estimated tokens
    over_limit: bool = False         # the content is longer than CONTEXT_LIMIT, so the text is the list


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


def files(cfg: Config) -> list[pathlib.Path]:
    """The start reading in order: the files of [start] files, or of the [start] dir folder in name order, then [start] also."""
    first = [p for entry in cfg.start.files for p in _expand(cfg, entry)] if cfg.start.files else _expand(cfg, cfg.start.dir)
    result, seen = [], set()
    for path in first + [p for entry in cfg.start.also for p in _expand(cfg, entry)]:
        if norm(path) not in seen:
            seen.add(norm(path))
            result.append(path)
    return result


def _read(path: pathlib.Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read().rstrip()


def _count(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def compose(cfg: Config) -> Composed:
    token_chars = personal()["token_chars"]
    paths = files(cfg)
    contents = [_read(path) for path in paths]
    measured = [(path, estimate_tokens(text, token_chars)) for path, text in zip(paths, contents)]
    tokens = sum(n for _, n in measured)
    over_budget = tokens > cfg.start.budget
    if not paths:
        return Composed(text="", tokens=0, over_budget=False, files=[])

    head = f"atlasmd: the start reading of {cfg.root.name}, {_count(len(paths))}, about {tokens} tokens.\n{GUARD_LINE}"
    full = head + "".join(f"\n\n## {areas.rel(cfg, path)}\n\n{text}" for path, text in zip(paths, contents))
    over_limit = len(full) > CONTEXT_LIMIT
    if cfg.start.inject and not over_budget and not over_limit:
        return Composed(text=full, tokens=tokens, over_budget=False, files=measured)

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
            lines.append(f"The whole start reading has {len(full)} characters, and Claude Code takes at most "
                         f"{CONTEXT_LIMIT} characters from a hook.")
            text = "\n".join(lines)
            if len(text) <= CONTEXT_LIMIT:
                return Composed(text=text, tokens=tokens, over_budget=False, files=measured, over_limit=True)

    lines = [head, "Read these files now, in this order:"]
    lines += [f"- {areas.rel(cfg, path)}, about {n} tokens" for path, n in measured]
    if over_budget:
        lines.append(f"The start reading is over its budget of {cfg.start.budget} tokens: {tokens}. "
                     "Move what is not needed at every start out of the start folder.")
    elif cfg.start.inject:
        lines.append(f"The start reading has {len(full)} characters. Claude Code takes at most {CONTEXT_LIMIT} "
                     "characters from a hook, so this list replaces the content.")
    return Composed(text="\n".join(lines), tokens=tokens, over_budget=over_budget, files=measured,
                    over_limit=over_limit)


def compose_map(cfg: Config) -> str:
    """The map alone, for a subagent at its start. Empty when the map file does not exist."""
    path = pathlib.Path(os.path.abspath(cfg.root / cfg.start.map))
    if not path.is_file():
        return ""
    text = _read(path)
    tokens = estimate_tokens(text, personal()["token_chars"])
    head = f"atlasmd: the map of {cfg.root.name}, about {tokens} tokens.\n{GUARD_LINE}"
    full = f"{head}\n\n## {areas.rel(cfg, path)}\n\n{text}"
    if len(full) <= CONTEXT_LIMIT:
        return full
    return f"{head}\nRead the map now: {areas.rel(cfg, path)}, about {tokens} tokens."
