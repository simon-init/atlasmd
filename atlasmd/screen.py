"""amd config: the settings screen of the project and of the person.

The project's [start], [guard] and [agents] values, the areas with their packs, and the
personal settings under them. The budget, the two inject values, the guard mode and the
personal settings can change here. Every other value and the areas are read only.
The areas stand on a route, one station each. s saves, q quits.
"""
import os
import re
import tempfile
from pathlib import Path

from atlasmd import areas as areas_mod
from atlasmd import cli, config, tui

HELP = [("↑↓", "move"), ("←→", "change"), ("enter", "change or type"), ("s", "save"), ("q", "quit")]

CHOICES = {
    ("guard", "mode"): list(config.GUARD_MODES),
    ("agents", "inject"): list(config.AGENT_INJECT),
    ("start", "inject"): [True, False],
    ("you", "offer_setup"): [True, False],
}
NUMBERS = {("start", "budget"): (1000, 1000, 10_000_000), ("you", "token_chars"): (0.1, 0.5, 100)}
HINTS = {
    ("start", "budget"): "token limit for these files",
    ("start", "inject"): {True: "Claude gets the text of the files", False: "Claude gets only a list of files"},
    ("start", "dir"): "its Markdown files, in name order",
    ("start", "files"): "if not empty, dir is not used",
    ("start", "also"): "Claude gets these after dir",
    ("start", "state"): "says where the work stands",
    ("start", "map"): "a subagent gets it at its start",
    ("start", "line"): "first message for a fresh chat",
    ("guard", "mode"): {"deny": "no edit until Claude reads pack",
                        "remind": "permit it and name the files",
                        "off": "do not look at edits"},
    ("guard", "bash"): "also look at Bash file writes",
    ("agents", "inject"): {"map": "a subagent gets start.map",
                           "start": "a subagent gets the files above",
                           "none": "a subagent gets nothing"},
    ("you", "offer_setup"): "offer /amd:init without atlasmd.toml",
    ("you", "token_chars"): "characters per estimated token",
}
LABELS = {("you", "offer_setup"): "offer setup", ("you", "token_chars"): "token chars"}


def show(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if isinstance(value, list):
        return ", ".join(value) if value else "none"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


HEADER = re.compile(r"^\s*\[{1,2}\s*([^\]]+?)\s*\]{1,2}\s*(#.*)?$")


def set_toml_value(text, table, key, value):
    """The text of a TOML file with one scalar value changed in place. The comment after the
    value stays. A missing key goes at the end of its table, a missing table at the end."""
    lines = text.splitlines()
    start = end = None
    for i, line in enumerate(lines):
        m = HEADER.match(line)
        if m:
            if start is not None and end is None:
                end = i
            if m.group(1) == table and not line.lstrip().startswith("[["):
                start = i
    if start is not None and end is None:
        end = len(lines)
    pattern = re.compile(r"^(\s*" + re.escape(key) + r"\s*=\s*)(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s#]+)(.*)$")
    if start is None:
        lines += ["", f"[{table}]", f"{key} = {literal(value)}"]
    else:
        for i in range(start + 1, end):
            m = pattern.match(lines[i])
            if m:
                new, rest = literal(value), m.group(3)
                gap = len(rest) - len(rest.lstrip())
                if gap and rest.lstrip().startswith("#"):
                    # keep the comment in its column when there is room
                    rest = " " * max(1, gap - (len(new) - len(m.group(2)))) + rest.lstrip()
                lines[i] = m.group(1) + new + rest
                break
        else:
            last = start
            for i in range(start + 1, end):
                if lines[i].strip() and not lines[i].lstrip().startswith("#"):
                    last = i
            lines.insert(last + 1, f"{key} = {literal(value)}")
    return "\n".join(lines) + "\n"


class Settings(tui.Page):
    title = "settings"

    def __init__(self, stdscr, cwd):
        super().__init__(stdscr)
        self.cwd = Path(cwd)
        self.cfg, self.error = None, None
        path = config.find(self.cwd)
        if path:
            try:
                self.cfg = config.load(path)
            except config.ConfigError as exc:
                self.error = str(exc)
        self.values = {}
        if self.cfg:
            s, g, a = self.cfg.start, self.cfg.guard, self.cfg.agents
            for key in ("budget", "inject", "dir", "files", "also", "state", "map", "line"):
                self.values[("start", key)] = getattr(s, key)
            self.values[("guard", "mode")] = g.mode
            self.values[("guard", "bash")] = g.bash
            self.values[("agents", "inject")] = a.inject
        self.values[("you", "offer_setup")] = bool(cli.personal_value("offer_setup"))
        self.values[("you", "token_chars")] = float(cli.personal_value("token_chars"))
        self.saved = dict(self.values)
        self.cursor = 0
        self.scroll = 0
        if self.error:
            self.say(self.error, problem=True)
        elif not self.cfg:
            self.say("No atlasmd.toml here or above, so this screen shows your own settings only.")

    # ------------------------------------------------------------ rows
    def editable(self, ident):
        return ident in CHOICES or ident in NUMBERS

    def rows(self):
        """[(kind, ident, extra)] in the order they are drawn. Selectable kinds: value, area."""
        out = []
        if self.cfg:
            for table, keys, title in (("start", ("budget", "inject", "dir", "files", "also", "state", "map", "line"),
                                        "[start]  what Claude gets at the start of a session"),
                                       ("guard", ("mode", "bash"), "[guard]  when the hook refuses an edit"),
                                       ("agents", ("inject",), "[agents]  what a subagent gets at its start")):
                out.append(("heading", None, title))
                for key in keys:
                    out.append(("value", (table, key), None))
                out.append(("blank", None, None))
            out.append(("heading", None, "[[area]]  folders, and the files to read before a change there"))
            if self.cfg.areas:
                out.append(("route", None, None))
                out.append(("route2", None, None))
                out.append(("blank", None, None))
                current = self.current_area()
                for i, _area in enumerate(self.cfg.areas):
                    out.append(("area", ("area", i), None))
                    if i == current:
                        out.extend(self.area_detail(i))
            else:
                out.append(("note", None, "atlasmd.toml lists no folders yet. /amd:init in a Claude Code session "
                                          "proposes them."))
            out.append(("blank", None, None))
        out.append(("heading", None, "your own settings, for every project"))
        out.append(("value", ("you", "offer_setup"), None))
        out.append(("value", ("you", "token_chars"), None))
        return out

    def selectable(self):
        """The rows the cursor visits, in the order they are drawn."""
        ids = []
        if self.cfg:
            ids += [("start", "budget"), ("start", "inject"), ("guard", "mode"), ("agents", "inject")]
            ids += [("area", i) for i in range(len(self.cfg.areas))]
        return ids + [("you", "offer_setup"), ("you", "token_chars")]

    def current_area(self):
        sel = self.selectable()
        if not sel:
            return -1
        ident = sel[min(self.cursor, len(sel) - 1)]
        return ident[1] if ident[0] == "area" else -1

    def area_detail(self, i):
        area = self.cfg.areas[i]
        out = [("detail", None, ("paths", ", ".join(area.paths) or "none", False))]
        pack = areas_mod.pack_of(self.cfg, area)
        if not pack:
            out.append(("detail", None, ("pack", "empty, so the hook refuses no edit here", True)))
        for n, (path, anchor) in enumerate(pack):
            name = cli.rel(self.cfg.root, path) + (f"#{anchor}" if anchor else "")
            missing = not path.is_file()
            out.append(("detail", None, ("pack" if n == 0 else "", name + ("  does not exist" if missing else ""),
                                         missing)))
        return out

    # ------------------------------------------------------------ actions
    def selected(self):
        sel = self.selectable()
        return sel[min(self.cursor, len(sel) - 1)] if sel else None

    def change(self, step):
        ident = self.selected()
        if ident is None or ident[0] == "area":
            if ident is not None:
                self.say("Change [[area]] entries in atlasmd.toml. This screen cannot change them.")
            return
        if ident in CHOICES:
            options = CHOICES[ident]
            now = self.values[ident]
            self.values[ident] = options[(options.index(now) + step) % len(options)]
        elif ident in NUMBERS:
            small, _big, top = NUMBERS[ident]
            value = self.values[ident] + step * small
            if isinstance(small, float):
                value = round(value, 2)
            if 0 < value <= top:
                self.values[ident] = value
        self.say(f"{self.label(ident)} = {show(self.values[ident])}   s saves")

    def type_value(self):
        ident = self.selected()
        if ident not in NUMBERS:
            self.change(1)
            return
        h, w = self.scr.getmaxyx()
        y = h - len(tui.footer_rows(HELP, w)) - 2
        text = self.read_line(f"{self.label(ident)}: ", y)
        if not text:
            return
        try:
            if ident == ("you", "token_chars"):
                value = cli.parse_personal("token_chars", text)
            else:
                value = int(text.replace(",", "").replace("_", ""))
                if not 0 < value <= NUMBERS[ident][2]:
                    raise ValueError
        except (ValueError, cli.Problem):
            self.say(f"{text} is not a number for {self.label(ident)}.", problem=True)
            return
        self.values[ident] = value
        self.say(f"{self.label(ident)} = {show(value)}   s saves")

    def dirty(self):
        return self.values != self.saved

    def save(self):
        changed = [k for k in self.values if self.values[k] != self.saved[k]]
        project = [k for k in changed if k[0] != "you"]
        if project and self.cfg:
            text = self.cfg.path.read_text(encoding="utf-8")
            for table, key in project:
                text = set_toml_value(text, table, key, self.values[(table, key)])
            with tempfile.TemporaryDirectory() as tmp:
                probe = Path(tmp) / config.CONFIG_NAME
                probe.write_text(text, encoding="utf-8")
                try:
                    config.load(probe)
                except config.ConfigError as exc:
                    self.say(f"Not saved: {exc}", problem=True)
                    return False
            with open(self.cfg.path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        mine = {k[1]: self.values[k] for k in changed if k[0] == "you"}
        if mine:
            cli.save_personal(mine)
        self.saved = dict(self.values)
        self.say("Saved. The hook uses the new values from the next tool call." if changed else "Nothing changed.")
        return True

    def confirm_quit(self):
        if not self.dirty():
            return True
        key = self.ask_key("Not saved.  s saves and quits, d quits without a save, another key stays", HELP)
        if key in (ord("s"), ord("S")):
            return self.save()
        if key in (ord("d"), ord("D")):
            return True
        self.say("")
        return False

    # ------------------------------------------------------------ drawing
    def label(self, ident):
        return LABELS.get(ident, ident[1])

    def hint(self, ident):
        h = HINTS.get(ident, "")
        return h.get(self.values[ident], "") if isinstance(h, dict) else h

    def draw(self):
        curses = self.curses
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        right = cli.rel(Path.home(), self.cfg.path) if self.cfg else ""
        if self.cfg and not right.startswith("/") and ":" not in right:
            right = "~/" + right
        self.header(right + ("   not saved" if self.dirty() else ""))
        rows = self.rows()
        sel = self.selectable()
        self.cursor = max(0, min(self.cursor, len(sel) - 1)) if sel else 0
        current = sel[self.cursor] if sel else None
        bottom = len(tui.footer_rows(HELP, w)) + 2
        top = 2
        visible = max(1, h - top - bottom)
        at = next((i for i, r in enumerate(rows) if r[1] == current and r[0] in ("value", "area")), 0)
        if at < self.scroll + 1:
            self.scroll = max(0, at - 3)
        elif at >= self.scroll + visible - 1:
            self.scroll = at - visible + 4
        self.scroll = max(0, min(self.scroll, max(0, len(rows) - visible)))
        names = [a.name for a in self.cfg.areas] if self.cfg else []
        area_now = self.current_area()
        label_w = 14
        y = top
        for kind, ident, extra in rows[self.scroll:self.scroll + visible]:
            if kind == "heading":
                self.put(y, 2, extra, self.accent())
            elif kind == "note":
                self.put(y, 4, tui.fit(extra, w - 7), self.dim())
            elif kind == "route":
                marks, under = tui.route(names, area_now, w - 8)
                attrs = {"passed": self.dim(), "current": self.accent(), "ahead": 0, "line": self.dim(),
                         "more": self.dim()}
                for x, text, k in marks:
                    self.put(y, 4 + x, text, attrs[k])
                for x, text, k in under:
                    self.put(y + 1, 4 + x, text, attrs[k])
            elif kind == "value":
                chosen = ident == current
                editable = self.editable(ident)
                self.put(y, 2, "›" if chosen else " ", self.accent())
                self.put(y, 4, self.label(ident), curses.A_BOLD if chosen else (0 if editable else self.dim()))
                value = show(self.values[ident])
                vw = 24 if w >= 72 else 12
                self.put(y, 4 + label_w, tui.fit(value, vw), curses.A_BOLD if editable else self.dim())
                x = 4 + label_w + vw + 2
                hint = self.hint(ident)
                if hint and x < w - 10:
                    self.put(y, x, tui.fit(hint, w - x - 3), self.dim())
            elif kind == "area":
                i = ident[1]
                area = self.cfg.areas[i]
                chosen = ident == current
                self.put(y, 2, "›" if chosen else " ", self.accent())
                nw = min(28, max(len(a.name) for a in self.cfg.areas))
                self.put(y, 4, tui.fit(area.name, nw), curses.A_BOLD if chosen else 0)
                n = len(area.pack)
                p = len(area.paths)
                info = f"{p} path{'s' if p != 1 else ''}, {n} file{'s' if n != 1 else ''} to read first"
                self.put(y, 4 + nw + 2, tui.fit(info, w - nw - 9), self.dim())
            elif kind == "detail":
                name, text, bad = extra
                self.put(y, 6, name, self.dim())
                self.put(y, 13, tui.fit(text, w - 16), self.red() if bad else 0)
            y += 1
        if self.scroll > 0:
            self.put(top - 1, max(2, w - 10), "↑ more", self.dim())
        if self.scroll + visible < len(rows):
            self.put(h - bottom, max(2, w - 10), "↓ more", self.dim())
        self.footer(HELP)
        self.scr.refresh()

    def loop(self):
        curses = self.curses
        while True:
            self.draw()
            key = self.scr.getch()
            n = len(self.selectable())
            if key == curses.KEY_RESIZE:
                self.scr.clear()
            elif key in (ord("q"), ord("Q")):
                if self.confirm_quit():
                    return 0
            elif key in (ord("s"), ord("S")):
                self.save()
            elif key in (curses.KEY_UP, ord("k")):
                self.cursor = max(0, self.cursor - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                self.cursor = min(max(0, n - 1), self.cursor + 1)
            elif key in (curses.KEY_RIGHT, ord("l"), ord("+")):
                self.change(1)
            elif key in (curses.KEY_LEFT, ord("h"), ord("-")):
                self.change(-1)
            elif key in (curses.KEY_ENTER, 10, 13, ord(" ")):
                self.type_value()


def run(cwd=None):
    import curses
    return curses.wrapper(lambda stdscr: Settings(stdscr, cwd or os.getcwd()).loop())
