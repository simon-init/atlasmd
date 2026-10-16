"""The meter: the tokens of each session, from the usage that Claude Code writes into the transcript.

One record per session, in <data>/meter/<session_id>.json. At every hook event, the hook reads the lines
that the transcript got after the byte offset in the record, adds the usage of each new request, and writes
the record. It reads the counts, the model, the compaction lines and the names of the tools, never the text.

A token count here is the sum of the four counts of a request: input_tokens, cache_read_input_tokens,
cache_creation_input_tokens and output_tokens. Claude Code writes one line for each block of a message,
and each line repeats the usage of the request, so a request counts once, by its message id.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import re
import time

from atlasmd import config, ledger, tui

COUNTS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
EDITS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
KEEP_IDS = 16
WINDOWS = (200_000, 1_000_000)


def folder() -> pathlib.Path:
    return config.data_dir() / "meter"


def _file(session_id) -> pathlib.Path:
    return folder() / (re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id))[:100] + ".json")


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _zero() -> dict:
    return {k: 0 for k in COUNTS}


def _cycle() -> dict:
    return {"requests": 0, "totals": _zero(), "context": 0, "peak": 0, "given": 0}


def tokens(counts: dict) -> int:
    return sum(int(counts.get(k) or 0) for k in COUNTS)


def new_record(session_id, transcript, root, group: str, on: bool) -> dict:
    root = pathlib.Path(root)
    now = _now()
    return {"session_id": str(session_id), "transcript": str(transcript), "offset": 0, "root": str(root),
            "name": root.name, "group": group, "on": bool(on), "started": now, "updated": now, "model": "",
            "window": 0, "requests": 0, "totals": _zero(), "start_tokens": 0, "start_requests": 0,
            "edited": False, "compactions": 0, "cycles": [_cycle()], "ids": []}


# ---------------------------------------------------------------- reading the transcript
def _counts(usage) -> dict:
    result = _zero()
    if isinstance(usage, dict):
        for k in COUNTS:
            value = usage.get(k)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                result[k] = value
    return result


def _first(record: dict, stamp) -> None:
    """The start of the record is the time of the first request when that is earlier, as for a session
    that ran before its first hook event."""
    try:
        first = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone()
        if first < datetime.datetime.fromisoformat(record["started"]):
            record["started"] = first.isoformat(timespec="seconds")
    except (TypeError, ValueError, KeyError):
        pass


def _add(into: dict, counts: dict) -> None:
    for k in COUNTS:
        into[k] = int(into.get(k) or 0) + counts[k]


def _line(record: dict, raw: bytes) -> None:
    if b'"assistant"' not in raw and b'"compact_boundary"' not in raw:
        return
    try:
        data = json.loads(raw)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    kind = data.get("type")
    if kind == "system" and data.get("subtype") == "compact_boundary":
        record["compactions"] += 1
        record["cycles"].append(_cycle())
        return
    if kind != "assistant" or data.get("isSidechain"):
        return
    message = data.get("message")
    if not isinstance(message, dict):
        return
    model = message.get("model")
    ident = message.get("id") or data.get("requestId") or data.get("uuid")
    if ident not in record["ids"] and not (isinstance(model, str) and model.startswith("<")):
        record["ids"] = (record["ids"] + [ident])[-KEEP_IDS:]
        counts = _counts(message.get("usage"))
        cycle = record["cycles"][-1]
        if not record["requests"]:
            _first(record, data.get("timestamp"))
        record["requests"] += 1
        cycle["requests"] += 1
        _add(record["totals"], counts)
        _add(cycle["totals"], counts)
        cycle["context"] = counts["input_tokens"] + counts["cache_read_input_tokens"] + counts["cache_creation_input_tokens"]
        cycle["peak"] = max(cycle["peak"], cycle["context"])
        if not record["edited"]:
            record["start_tokens"] += tokens(counts)
            record["start_requests"] += 1
        if isinstance(model, str) and model:
            record["model"] = model
    if not record["edited"]:
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in EDITS:
                record["edited"] = True
                break


def read_new(record: dict) -> bool:
    """Add the whole lines that the transcript got after the offset of the record. True when it read some."""
    path = record.get("transcript") or ""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    offset = int(record.get("offset") or 0)
    if size < offset:  # the file is shorter than at the last read: count it again from its start
        fresh = new_record(record["session_id"], path, record["root"], record.get("group", ""), record.get("on", True))
        fresh.update({k: record[k] for k in ("started", "window") if k in record})
        record.clear()
        record.update(fresh)
        offset = 0
    if size == offset:
        return False
    position = offset
    with open(path, "rb") as handle:
        handle.seek(offset)
        for raw in handle:
            if not raw.endswith(b"\n"):
                break  # Claude Code is still writing this line. The next read takes it.
            position += len(raw)
            _line(record, raw)
    changed = position != offset
    record["offset"] = position
    return changed


# ---------------------------------------------------------------- records
@contextlib.contextmanager
def _held(path: pathlib.Path):
    """A lock file next to the record. Yields False when another hook holds it for longer than a second:
    then this event leaves the record alone, and the next event reads the same lines."""
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + 1.0
    held = False
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            held = True
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 10:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                break
            time.sleep(0.01)
    try:
        yield held
    finally:
        if held:
            lock.unlink(missing_ok=True)


def load(session_id) -> dict | None:
    try:
        with open(_file(session_id), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("session_id") else None


def update(data: dict, on: bool, given: int | None = None) -> dict | None:
    """Read the new lines of the transcript of a hook event into the record of its session, and write it.

    A record starts at the first event of a session in a project with atlasmd.toml. An event of a
    subagent starts no record, and an event with another transcript than the record's changes nothing.
    given is the estimated tokens of the files that the hook gave at a session start.
    """
    session, transcript = data.get("session_id"), data.get("transcript_path")
    if not session or not transcript:
        return None
    path = _file(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _held(path) as held:
        if not held:
            return None
        record = load(session)
        if record is None:
            if data.get("agent_id"):
                return None
            found = config.find(data.get("cwd") or os.getcwd())
            if found is None:
                return None
            try:
                group = config.load(found).group
            except config.ConfigError:
                group = ""
            record = new_record(session, transcript, found.parent, group, on)
        elif config.norm(record.get("transcript") or "") != config.norm(transcript):
            return record
        read_new(record)
        if given is not None:
            record["cycles"][-1]["given"] = int(given)
        record["updated"] = _now()
        ledger._save(path, record)
    return record


def refresh(record: dict, window: int | None = None) -> dict:
    """The record with the lines that its transcript got since the last hook event, for amd meter and
    amd statusline. window is the size of the context window that Claude Code gives a status line."""
    try:
        grown = os.path.getsize(record.get("transcript") or "") > int(record.get("offset") or 0)
    except OSError:
        grown = False
    if not grown and not (window and window != record.get("window")):
        return record
    path = _file(record["session_id"])
    with _held(path) as held:
        if not held:
            return record
        fresh = load(record["session_id"]) or record
        read_new(fresh)
        if window:
            fresh["window"] = int(window)
        ledger._save(path, fresh)
    return fresh


def records(root=None) -> list[dict]:
    """Every record, or the records of one repository, the newest start first."""
    found = []
    target = config.norm(root) if root is not None else None
    if folder().is_dir():
        for path in folder().glob("*.json"):
            try:
                with open(path, encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or not data.get("session_id") or not isinstance(data.get("totals"), dict):
                continue
            if target is None or config.norm(data.get("root") or "") == target:
                found.append(data)
    found.sort(key=lambda r: (r.get("started") or "", r.get("updated") or ""), reverse=True)
    return found


def pick(found: list[dict], ident: str) -> dict | None:
    """The record whose session id is ident or starts with it, when only one does."""
    exact = [r for r in found if r["session_id"] == ident]
    if exact:
        return exact[0]
    hits = [r for r in found if r["session_id"].startswith(ident)]
    return hits[0] if len(hits) == 1 else None


# ---------------------------------------------------------------- what the screen and the lines show
def short(record: dict) -> str:
    return record["session_id"][:8]


def when(record: dict) -> str:
    try:
        return datetime.datetime.fromisoformat(record.get("started") or "").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return "?"


def mode(record: dict) -> str:
    return "on" if record.get("on", True) else "off"


def window(record: dict) -> int:
    """The context window: from the status line when it ran, else 1,000,000 when a request held more than
    200,000 tokens, else 200,000."""
    if record.get("window"):
        return int(record["window"])
    peak = max([c.get("peak", 0) for c in record.get("cycles", [])] or [0])
    return WINDOWS[1] if peak > WINDOWS[0] else WINDOWS[0]


def summary(record: dict) -> dict:
    cycles = record.get("cycles") or [_cycle()]
    return {"session_id": record["session_id"], "started": record.get("started"), "on": record.get("on", True),
            "root": record.get("root"), "group": record.get("group", ""), "model": record.get("model", ""),
            "requests": record.get("requests", 0), "totals": record.get("totals", _zero()),
            "tokens": tokens(record.get("totals", {})), "start_tokens": record.get("start_tokens", 0),
            "start_requests": record.get("start_requests", 0), "edited": record.get("edited", False),
            "compactions": record.get("compactions", 0), "cycle": len(cycles), "context": cycles[-1].get("context", 0),
            "window": window(record), "given": cycles[-1].get("given", 0),
            "cycles": [{"requests": c.get("requests", 0), "tokens": tokens(c.get("totals", {})),
                        "totals": c.get("totals", _zero()), "peak": c.get("peak", 0), "given": c.get("given", 0)}
                       for c in cycles]}


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def status_line(record: dict | None, color: bool = False) -> str:
    name = tui.paint("atlasmd", "accent", color)
    if record is None:
        return f"{name} · no record of this session yet"
    return (f"{name} {mode(record)} · start {record.get('start_tokens', 0):,} · session "
            f"{tokens(record.get('totals', {})):,} · {plural(record.get('compactions', 0), 'compaction')}")


BAR = 20


def bar(value: int, limit: int, width: int = BAR) -> tuple[str, str]:
    """The filled part and the empty part of a meter bar."""
    filled = width if limit <= 0 or value >= limit else round(width * value / limit)
    if value > 0 and filled == 0:
        filled = 1
    return "━" * filled, "─" * (width - filled)


def live_rows(record: dict, budget: int) -> list[tuple]:
    """The rows of the live session: (label, bar or None, text). A bar is (value, limit)."""
    s = summary(record)
    if s["on"]:
        given = (s["given"], budget, f"{s['given']:,} of {budget:,} in start.budget")
    else:
        given = (0, budget, "atlasmd was off, the hook gave nothing")
    edit = "to the first Edit or Write" if s["edited"] else "and no Edit or Write yet"
    return [
        ("docs/start/", (given[0], given[1]), given[2]),
        (f"cycle {s['cycle']}", (s["context"], s["window"]), f"{s['context']:,} of {s['window']:,} in the context"),
        ("start", None, f"{s['start_tokens']:,} tokens in {plural(s['start_requests'], 'request')} {edit}"),
        ("session", None, f"{s['tokens']:,} tokens in {plural(s['requests'], 'request')}, "
                          f"{plural(s['compactions'], 'compaction')}"),
    ]


HISTORY_HEAD = ("session", "date", "atlasmd", "start", "total", "compactions")
RIGHT = (False, False, False, True, True, True)


def history_cells(record: dict) -> tuple[str, ...]:
    start = f"{record.get('start_tokens', 0):,}" if record.get("edited") else "no edit"
    return (short(record), when(record), mode(record), start, f"{tokens(record.get('totals', {})):,}",
            f"{record.get('compactions', 0):,}")


def table(head: tuple, rows: list[tuple], right: tuple) -> list[str]:
    """Rows of text with two spaces between the columns, numbers on the right."""
    widths = [max(len(str(r[i])) for r in [head, *rows]) for i in range(len(head))]
    lines = []
    for r in [head, *rows]:
        cells = [str(c).rjust(w) if right[i] else str(c).ljust(w) for i, (c, w) in enumerate(zip(r, widths))]
        lines.append("  ".join(cells).rstrip())
    return lines


def compare_rows(a: dict, b: dict) -> tuple[tuple, list[tuple]]:
    """The comparison of two records: the head and the rows. The off session comes first when the two differ."""
    if a.get("on", True) and not b.get("on", True):
        a, b = b, a
    names = (mode(a), mode(b)) if mode(a) != mode(b) else (short(a), short(b))
    head = ("", names[0], names[1], "difference", "")
    rows = []
    both = a.get("edited") and b.get("edited")
    for label, x, y in (("start", a.get("start_tokens", 0), b.get("start_tokens", 0)),
                        ("total", tokens(a.get("totals", {})), tokens(b.get("totals", {}))),
                        ("requests", a.get("requests", 0), b.get("requests", 0)),
                        ("compactions", a.get("compactions", 0), b.get("compactions", 0))):
        if label == "start" and not both:
            rows.append((label, f"{x:,}" if a.get("edited") else "no edit", f"{y:,}" if b.get("edited") else "no edit",
                         "", ""))
            continue
        diff = y - x
        if x:
            share = round(abs(diff) * 100 / x)
            note = f"{share}% saved" if diff < 0 else (f"{share}% more" if diff > 0 else "the same")
        else:
            note = "the same" if not diff else ""
        rows.append((label, f"{x:,}", f"{y:,}", f"{diff:+,}" if diff else "0", note))
    return head, rows


def render_compare(a: dict, b: dict) -> list[str]:
    if a.get("on", True) and not b.get("on", True):
        a, b = b, a
    head, rows = compare_rows(a, b)
    lines = [f"{short(a)}  {when(a)}  atlasmd {mode(a)}", f"{short(b)}  {when(b)}  atlasmd {mode(b)}", ""]
    return lines + table(head, rows, (False, True, True, True, False))


def render(root, found: list[dict], budget: int, color: bool = False) -> list[str]:
    """amd meter --list: the live session, then the history of the repository."""
    lines = [f"atlasmd meter  {root}", ""]
    if not found:
        return lines + ["No session is recorded for this repository yet. The hook records each session that "
                        "starts here, from its first hook event."]
    live = found[0]
    lines.append(f"The newest session  {short(live)}  {when(live)}  atlasmd {mode(live)}"
                 + (f"  {live['model']}" if live.get("model") else ""))
    rows = live_rows(live, budget)
    width = max(len(label) for label, _b, _t in rows)
    for label, meter_bar, text in rows:
        if meter_bar:
            filled, empty = bar(*meter_bar)
            text = tui.paint(filled, "accent", color) + tui.paint(empty, "dim", color) + "  " + text
        lines.append(f"  {label.ljust(width)}  {text}")
    lines += ["", f"History  {plural(len(found), 'session')}, the newest first", ""]
    lines += ["  " + line for line in table(HISTORY_HEAD, [history_cells(r) for r in found], RIGHT)]
    lines += ["", "amd meter --compare <session> <session> compares two sessions, for example an off session with "
                  "an on session."]
    return lines


def render_all(found: list[dict]) -> list[str]:
    """amd meter --list outside a repository: the sessions of every repository, the newest first."""
    where = str(folder()).replace(str(pathlib.Path.home()), "~", 1)
    lines = [f"atlasmd meter  every repository, from {where}", ""]
    if not found:
        return lines + ["No session is recorded yet. The hook records each session that starts in a repository "
                        "with atlasmd.toml."]
    lines += ["This folder has no atlasmd.toml above it, so amd meter --list shows the sessions of every repository, "
              f"the newest first: {plural(len(found), 'session')}.", ""]
    rows = [(pathlib.Path(r.get("root") or "").name or "none",) + history_cells(r) for r in found]
    lines += ["  " + line for line in table(("repository",) + HISTORY_HEAD, rows, (False,) + RIGHT)]
    lines += ["", "amd meter in a repository shows its newest session with bars. amd meter --compare <session> "
                  "<session> compares two sessions."]
    return lines


# ---------------------------------------------------------------- the screen
HELP = [("↑↓", "move"), ("enter", "pick two sessions"), ("c", "compare with the newest of the other kind"),
        ("q", "quit")]
BACK = [("←", "back"), ("q", "quit")]


class Screen(tui.Page):
    title = "meter"

    def __init__(self, stdscr, root, found, budget):
        super().__init__(stdscr)
        self.root, self.found, self.budget = root, found, budget
        self.cursor = 0
        self.scroll = 0
        self.marked = None
        self.pair = None

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self.header(str(self.root).replace(str(pathlib.Path.home()), "~", 1))
        if self.pair:
            self.draw_compare()
        else:
            self.draw_list()
        self.scr.refresh()

    def draw_list(self):
        h, w = self.scr.getmaxyx()
        y = 2
        live = self.found[0]
        self.put(y, 2, "The newest session", self.accent())
        self.put(y, 22, tui.fit(f"{short(live)}  {when(live)}  atlasmd {mode(live)}  {live.get('model', '')}", w - 25),
                 self.dim())
        y += 2
        rows = live_rows(live, self.budget)
        width = max(len(label) for label, _b, _t in rows)
        for label, meter_bar, text in rows:
            self.put(y, 4, label, self.dim())
            x = 4 + width + 2
            if meter_bar:
                filled, empty = bar(*meter_bar)
                self.put(y, x, filled, self.accent())
                self.put(y, x + len(filled), empty, self.dim())
                x += BAR + 2
            self.put(y, x, tui.fit(text, w - x - 2))
            y += 1
        y += 1
        self.put(y, 2, "History", self.accent())
        self.put(y, 11, tui.fit(f"{plural(len(self.found), 'session')} of {self.root.name}, the newest first", w - 14),
                 self.dim())
        y += 2
        lines = table(HISTORY_HEAD, [history_cells(r) for r in self.found], RIGHT)
        if len(lines[0]) > w - 7:  # a narrow terminal: the screen needs no session id, enter and c pick the rows
            lines = table(HISTORY_HEAD[1:], [history_cells(r)[1:] for r in self.found], RIGHT[1:])
        self.put(y, 4, tui.fit(lines[0], w - 7), self.dim())
        y += 1
        bottom = len(tui.footer_rows(HELP, w)) + 2
        visible = max(1, h - y - bottom)
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + visible:
            self.scroll = self.cursor - visible + 1
        for i in range(self.scroll, min(len(self.found), self.scroll + visible)):
            chosen = i == self.cursor
            self.put(y, 2, "›" if chosen else " ", self.accent())
            if i == self.marked:
                self.put(y, 3, "●", self.accent())
            self.put(y, 4, tui.fit(lines[i + 1], w - 7), self.curses.A_BOLD if chosen else 0)
            y += 1
        self.footer(HELP)

    def draw_compare(self):
        h, w = self.scr.getmaxyx()
        a, b = self.pair
        lines = render_compare(a, b)
        self.put(2, 2, "Compare", self.accent())
        y = 4
        for i, line in enumerate(lines):
            self.put(y, 4, tui.fit(line, w - 7), self.dim() if i == 3 else 0)
            y += 1
        self.footer(BACK)

    def loop(self):
        curses = self.curses
        while True:
            self.draw()
            key = self.scr.getch()
            if key == curses.KEY_RESIZE:
                self.scr.clear()
            elif key in (ord("q"), ord("Q")):
                return 0
            elif self.pair:
                if key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8, 27, ord("h"), 10, 13, curses.KEY_ENTER):
                    self.pair = None
                    self.say("")
            elif key in (curses.KEY_UP, ord("k")):
                self.cursor = max(0, self.cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                self.cursor = min(len(self.found) - 1, self.cursor + 1)
            elif key in (curses.KEY_ENTER, 10, 13, ord(" ")):
                if self.marked is None or self.marked == self.cursor:
                    self.marked = None if self.marked == self.cursor else self.cursor
                    self.say("Pick the second session with enter." if self.marked is not None else "")
                else:
                    self.pair = (self.found[self.marked], self.found[self.cursor])
                    self.marked = None
            elif key in (ord("c"), ord("C")):
                one = self.found[self.cursor]
                other = next((r for r in self.found if r.get("on", True) != one.get("on", True)), None)
                if other is None:
                    kind = "off" if one.get("on", True) else "on"
                    self.say(f"No session of this repository ran with atlasmd {kind}. "
                             + ("Start one with ATLASMD=off claude." if kind == "off" else ""))
                else:
                    self.pair = (one, other)


def run(root, found, budget):
    import curses
    return curses.wrapper(lambda stdscr: Screen(stdscr, pathlib.Path(root), found, budget).loop())
