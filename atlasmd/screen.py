"""amd config: the screen of your repositories, and of the settings and the Markdown files of each one.

Three stations on a route. Repositories: a table of every repository in <data>/projects.toml. On a row,
g, m, i and b change the group, guard.mode, start.inject and start.budget, and enter opens the row.
The settings of one repository: the values of its atlasmd.toml, its [[area]] entries and your own
settings, as in 0.2. The budget, the two inject values, the guard mode and your own settings change
there. Files: the Markdown files of the repository as a tree. p adds a file to [private] files or
removes it. tab and shift-tab go from station to station. s saves, q quits.
"""
import os
from pathlib import Path

from atlasmd import areas as areas_mod
from atlasmd import cli, config, projects, scan, tomledit, tui

set_toml_value = tomledit.set_value  # the names of 0.2
literal = tomledit.literal

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
START_KEYS = ("budget", "inject", "dir", "files", "also", "state", "map", "line")

HELP = {
    0: [("↑↓", "move"), ("enter", "open"), ("g", "group"), ("m", "guard.mode"), ("i", "start.inject"),
        ("b", "start.budget"), ("tab", "next station"), ("s", "save"), ("q", "quit")],
    1: [("↑↓", "move"), ("←→", "change"), ("enter", "change or type"), ("tab", "next station"), ("s", "save"),
        ("q", "quit")],
    2: [("↑↓", "move"), ("p", "private or not"), ("tab", "next station"), ("s", "save"), ("q", "quit")],
}
TAB, BACKTAB, ESCAPE = 9, 353, 27


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


# ---------------------------------------------------------------- what the screen changes
class Repo:
    """One repository of the list: its atlasmd.toml, its values as the screen shows them, and as saved."""

    def __init__(self, path, name=None):
        self.path = Path(path)
        self.name = name or self.path.name
        self.info = None
        self.load()

    def load(self):
        self.cfg, self.error = None, None
        toml = self.path / config.CONFIG_NAME
        if not self.path.is_dir():
            self.error = "the folder does not exist"
        elif not toml.is_file():
            self.error = "no atlasmd.toml"
        else:
            try:
                self.cfg = config.load(toml)
            except config.ConfigError as exc:
                self.error = str(exc)
        self.values = {}
        if self.cfg:
            self.values[("", "group")] = self.cfg.group
            for key in START_KEYS:
                self.values[("start", key)] = getattr(self.cfg.start, key)
            self.values[("guard", "mode")] = self.cfg.guard.mode
            self.values[("guard", "bash")] = self.cfg.guard.bash
            self.values[("agents", "inject")] = self.cfg.agents.inject
        self.saved = dict(self.values)

    def row(self):
        if self.info is None:
            self.info = cli.repository_info({"path": str(self.path), "name": self.name, "group": ""})
        return self.info

    def dirty(self):
        return self.values != self.saved

    def changed(self):
        return {k: v for k, v in self.values.items() if v != self.saved.get(k)}

    def save(self):
        changed = self.changed()
        if changed:
            self.cfg = cli.write_values(self.cfg.path, changed)
            self.saved = dict(self.values)
            self.info = None
        return len(changed)


class Mine:
    """Your own settings, for every project."""

    def __init__(self):
        self.values = {"offer_setup": bool(cli.personal_value("offer_setup")),
                       "token_chars": float(cli.personal_value("token_chars"))}
        self.saved = dict(self.values)

    def dirty(self):
        return self.values != self.saved

    def save(self):
        changed = {k: v for k, v in self.values.items() if v != self.saved[k]}
        if changed:
            cli.save_personal(changed)
            self.saved = dict(self.values)
        return len(changed)


# ---------------------------------------------------------------- station 1: the repositories
class Repositories:
    def __init__(self, screen):
        self.s = screen
        self.cursor = 0
        self.scroll = 0

    def columns(self, cells, width):
        """The indexes of the columns that fit the width. The path goes first, then the counts."""
        shown = list(range(len(cli.REPO_HEAD)))
        for drop in (1, 8, 7, 6):
            widths = [max(len(str(r[i])) for r in cells) for i in shown]
            if sum(widths) + 2 * (len(shown) - 1) <= width:
                break
            shown.remove(drop)
        return shown

    def draw(self, top):
        s = self.s
        h, w = s.scr.getmaxyx()
        repos = s.repos
        if not repos:
            s.put(top, 4, tui.fit("atlasmd knows no repository yet. amd init, amd config and the hook at a session start "
                                  "add the repository where they run.", w - 7), s.dim())
            return
        rows = [cli.repository_cells(r.row(), r.values) for r in repos]
        cells = [cli.REPO_HEAD] + rows
        shown = self.columns(cells, w - 8)
        widths = {i: max(len(str(r[i])) for r in cells) for i in shown}
        keys = {2: ("", "group"), 3: ("guard", "mode"), 4: ("start", "inject"), 5: ("start", "budget")}

        def put_row(y, row, attr, repo=None):
            x = 4
            for i in shown:
                text = str(row[i])
                cell = text.rjust(widths[i]) if cli.REPO_RIGHT[i] else text.ljust(widths[i])
                a = attr
                if repo is not None and i in keys and repo.values.get(keys[i]) != repo.saved.get(keys[i]):
                    a = s.accent()
                s.put(y, x, cell, a)
                x += widths[i] + 2

        put_row(top, cli.REPO_HEAD, s.dim())
        bottom = len(tui.footer_rows(HELP[0], w)) + 2
        visible = max(1, h - top - 1 - bottom - 2)
        self.cursor = max(0, min(self.cursor, len(repos) - 1))
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + visible:
            self.scroll = self.cursor - visible + 1
        y = top + 1
        for n in range(self.scroll, min(len(repos), self.scroll + visible)):
            repo = repos[n]
            chosen = n == self.cursor
            s.put(y, 2, "›" if chosen else " ", s.accent())
            if repo.error:
                put_row(y, rows[n], s.dim())
                x = 4 + widths[0] + 2 + (widths[1] + 2 if 1 in shown else 0)
                s.put(y, x, tui.fit(repo.error, w - x - 3), s.red() if chosen else s.dim())
            else:
                put_row(y, rows[n], s.curses.A_BOLD if chosen else 0, repo)
            y += 1
        if self.scroll > 0:
            s.put(top, max(2, w - 10), "↑ more", s.dim())
        if self.scroll + visible < len(repos):
            s.put(y, max(2, w - 10), "↓ more", s.dim())
        y += 1
        s.put(y, 4, tui.fit(f"From {cli.tilde(projects.path())}. Repositories with the same group share their "
                            "docs/start/ at a session's start.", w - 7), s.dim())

    def selected(self):
        return self.s.repos[self.cursor] if self.s.repos else None

    def key(self, key):
        s, curses = self.s, self.s.curses
        repo = self.selected()
        if key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = min(max(0, len(s.repos) - 1), self.cursor + 1)
        elif repo is None:
            return
        elif key in (curses.KEY_ENTER, 10, 13, ord(" ")):
            s.open(self.cursor, 1)
        elif key in (ord("g"), ord("m"), ord("i"), ord("b")) and repo.error:
            s.say(f"{repo.name}: {repo.error}. This screen changes a repository with a valid atlasmd.toml.", problem=True)
        elif key == ord("g"):
            text = s.ask_line(f"group of {repo.name}, letters, digits and hyphens, empty for none: ")
            if text is None:
                return
            if not config.GROUP_NAME.match(text):
                s.say(f"{text} is not a group name. Use letters, digits and hyphens, for example my-project.",
                      problem=True)
                return
            repo.values[("", "group")] = text
            s.say(f"{repo.name}: group = {text or 'none'}   s saves")
        elif key == ord("m"):
            modes = list(config.GUARD_MODES)
            now = repo.values[("guard", "mode")]
            repo.values[("guard", "mode")] = modes[(modes.index(now) + 1) % len(modes)]
            s.say(f"{repo.name}: guard.mode = {repo.values[('guard', 'mode')]}   s saves")
        elif key == ord("i"):
            repo.values[("start", "inject")] = not repo.values[("start", "inject")]
            s.say(f"{repo.name}: start.inject = {'true' if repo.values[('start', 'inject')] else 'false'}   s saves")
        elif key == ord("b"):
            text = s.ask_line(f"start.budget of {repo.name}, in tokens: ")
            if not text:
                return
            try:
                value = cli.parse_value("start.budget", text)
            except cli.Problem as exc:
                s.say(str(exc), problem=True)
                return
            repo.values[("start", "budget")] = value
            s.say(f"{repo.name}: start.budget = {value:,}   s saves")


# ---------------------------------------------------------------- station 2: the settings of one repository
class Settings:
    def __init__(self, screen, repo):
        self.s = screen
        self.repo = repo
        self.cursor = 0
        self.scroll = 0

    @property
    def cfg(self):
        return self.repo.cfg

    def get(self, ident):
        return self.s.mine.values[ident[1]] if ident[0] == "you" else self.repo.values[ident]

    def set(self, ident, value):
        if ident[0] == "you":
            self.s.mine.values[ident[1]] = value
        else:
            self.repo.values[ident] = value

    def saved(self, ident):
        return self.s.mine.saved[ident[1]] if ident[0] == "you" else self.repo.saved.get(ident)

    def editable(self, ident):
        return ident in CHOICES or ident in NUMBERS

    def rows(self):
        """[(kind, ident, extra)] in the order they are drawn. Selectable kinds: value, area."""
        out = []
        if self.cfg:
            for table, keys, title in (("start", START_KEYS, "[start]  what Claude gets at the start of a session"),
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
        else:
            out.append(("note", None, f"{self.repo.name}: {self.repo.error}."))
            out.append(("blank", None, None))
        out.append(("heading", None, "your own settings, for every project"))
        out.append(("value", ("you", "offer_setup"), None))
        out.append(("value", ("you", "token_chars"), None))
        return out

    def selectable(self):
        ids = []
        if self.cfg:
            ids += [("start", "budget"), ("start", "inject"), ("guard", "mode"), ("agents", "inject")]
            ids += [("area", i) for i in range(len(self.cfg.areas))]
        return ids + [("you", "offer_setup"), ("you", "token_chars")]

    def selected(self):
        sel = self.selectable()
        return sel[min(self.cursor, len(sel) - 1)] if sel else None

    def current_area(self):
        ident = self.selected()
        return ident[1] if ident and ident[0] == "area" else -1

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

    def label(self, ident):
        return LABELS.get(ident, ident[1])

    def hint(self, ident):
        h = HINTS.get(ident, "")
        return h.get(self.get(ident), "") if isinstance(h, dict) else h

    def change(self, step):
        s = self.s
        ident = self.selected()
        if ident is None or ident[0] == "area":
            if ident is not None:
                s.say("Change [[area]] entries in atlasmd.toml. This screen cannot change them.")
            return
        if ident in CHOICES:
            options = CHOICES[ident]
            self.set(ident, options[(options.index(self.get(ident)) + step) % len(options)])
        elif ident in NUMBERS:
            small, _big, top = NUMBERS[ident]
            value = self.get(ident) + step * small
            if isinstance(small, float):
                value = round(value, 2)
            if 0 < value <= top:
                self.set(ident, value)
        s.say(f"{self.label(ident)} = {show(self.get(ident))}   s saves")

    def type_value(self):
        s = self.s
        ident = self.selected()
        if ident not in NUMBERS:
            self.change(1)
            return
        text = s.ask_line(f"{self.label(ident)}: ")
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
            s.say(f"{text} is not a number for {self.label(ident)}.", problem=True)
            return
        self.set(ident, value)
        s.say(f"{self.label(ident)} = {show(value)}   s saves")

    def key(self, key):
        curses = self.s.curses
        n = len(self.selectable())
        if key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = min(max(0, n - 1), self.cursor + 1)
        elif key in (curses.KEY_RIGHT, ord("l"), ord("+")):
            self.change(1)
        elif key in (curses.KEY_LEFT, ord("h"), ord("-")):
            self.change(-1)
        elif key in (curses.KEY_ENTER, 10, 13, ord(" ")):
            self.type_value()

    def draw(self, top):
        s, curses = self.s, self.s.curses
        h, w = s.scr.getmaxyx()
        rows = self.rows()
        sel = self.selectable()
        self.cursor = max(0, min(self.cursor, len(sel) - 1)) if sel else 0
        current = sel[self.cursor] if sel else None
        bottom = len(tui.footer_rows(HELP[1], w)) + 2
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
                s.put(y, 2, extra, s.accent())
            elif kind == "note":
                s.put(y, 4, tui.fit(extra, w - 7), s.dim())
            elif kind == "route":
                marks, under = tui.route(names, area_now, w - 8)
                attrs = {"passed": s.dim(), "current": s.accent(), "ahead": 0, "line": s.dim(), "more": s.dim()}
                for x, text, k in marks:
                    s.put(y, 4 + x, text, attrs[k])
                for x, text, k in under:
                    s.put(y + 1, 4 + x, text, attrs[k])
            elif kind == "value":
                chosen = ident == current
                editable = self.editable(ident)
                s.put(y, 2, "›" if chosen else " ", s.accent())
                s.put(y, 4, self.label(ident), curses.A_BOLD if chosen else (0 if editable else s.dim()))
                value = show(self.get(ident))
                vw = 24 if w >= 72 else 12
                attr = s.accent() if self.get(ident) != self.saved(ident) else (curses.A_BOLD if editable else s.dim())
                s.put(y, 4 + label_w, tui.fit(value, vw), attr)
                x = 4 + label_w + vw + 2
                hint = self.hint(ident)
                if hint and x < w - 10:
                    s.put(y, x, tui.fit(hint, w - x - 3), s.dim())
            elif kind == "area":
                area = self.cfg.areas[ident[1]]
                chosen = ident == current
                s.put(y, 2, "›" if chosen else " ", s.accent())
                nw = min(28, max(len(a.name) for a in self.cfg.areas))
                s.put(y, 4, tui.fit(area.name, nw), curses.A_BOLD if chosen else 0)
                n, p = len(area.pack), len(area.paths)
                info = f"{p} path{'s' if p != 1 else ''}, {n} file{'s' if n != 1 else ''} to read first"
                s.put(y, 4 + nw + 2, tui.fit(info, w - nw - 9), s.dim())
            elif kind == "detail":
                name, text, bad = extra
                s.put(y, 6, name, s.dim())
                s.put(y, 13, tui.fit(text, w - 16), s.red() if bad else 0)
            y += 1
        if self.scroll > 0:
            s.put(top - 1, max(2, w - 10), "↑ more", s.dim())
        if self.scroll + visible < len(rows):
            s.put(h - bottom, max(2, w - 10), "↓ more", s.dim())


# ---------------------------------------------------------------- station 3: the Markdown files of one repository
class Files:
    NOTE = ("p adds the file to [private] files in atlasmd.toml and to .git/info/exclude, so git does not commit "
            "it. p on a private file removes it from both.")

    def __init__(self, screen, repo):
        self.s = screen
        self.repo = repo
        self.cursor = 0
        self.scroll = 0
        self.rows = None

    def load(self):
        root = self.repo.path
        entries = scan.scan(root)["files"]
        listed = {e["path"] for e in entries}
        for rel in self.repo.cfg.private if self.repo.cfg else []:
            if rel not in listed and (root / rel).is_file():
                entries.append(scan.file_entry(root, rel))
        entries.sort(key=lambda e: e["path"])
        self.rows = scan.tree_rows(entries)

    def files(self):
        return [i for i, (_name, entry) in enumerate(self.rows) if entry]

    def key(self, key):
        s, curses = self.s, self.s.curses
        files = self.files()
        if key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = min(max(0, len(files) - 1), self.cursor + 1)
        elif key in (ord("p"), ord("P")) and files:
            if not self.repo.cfg:
                s.say(f"{self.repo.name}: {self.repo.error}.", problem=True)
                return
            entry = self.rows[files[self.cursor]][1]
            try:
                s.say(cli.toggle_private(self.repo.cfg, entry["path"]))
            except (cli.Problem, OSError) as exc:
                s.say(str(exc), problem=True)
                return
            self.repo.cfg = config.load(self.repo.cfg.path)
            self.repo.info = None

    def draw(self, top):
        s, curses = self.s, self.s.curses
        h, w = s.scr.getmaxyx()
        if not self.repo.cfg:
            s.put(top, 4, tui.fit(f"{self.repo.name}: {self.repo.error}.", w - 7), s.dim())
            return
        if self.rows is None:
            self.load()
        files = self.files()
        private = set(self.repo.cfg.private)
        name_w = min(max([len(n) for n, _e in self.rows] + [4]), max(20, w - 30))
        tok_w = max([len("tokens")] + [len(f"{e['tokens']:,}") for _n, e in self.rows if e])
        s.put(top, 4, "file".ljust(name_w) + "  " + "tokens".rjust(tok_w), s.dim())
        if not files:
            s.put(top + 1, 4, "This repository has no Markdown files.", s.dim())
            return
        bottom = len(tui.footer_rows(HELP[2], w)) + 2
        visible = max(1, h - top - 1 - bottom - 2)
        self.cursor = max(0, min(self.cursor, len(files) - 1))
        at = files[self.cursor]
        if at < self.scroll:
            self.scroll = max(0, at - 1)
        elif at >= self.scroll + visible:
            self.scroll = at - visible + 1
        y = top + 1
        for i in range(self.scroll, min(len(self.rows), self.scroll + visible)):
            name, entry = self.rows[i]
            chosen = i == at
            if entry is None:
                s.put(y, 4, tui.fit(name, name_w), s.dim())
            else:
                s.put(y, 2, "›" if chosen else " ", s.accent())
                s.put(y, 4, tui.fit(name, name_w), curses.A_BOLD if chosen else 0)
                s.put(y, 4 + name_w + 2, f"{entry['tokens']:,}".rjust(tok_w), s.dim())
                if entry["path"] in private:
                    s.put(y, 4 + name_w + 2 + tok_w + 2, "private", s.accent())
            y += 1
        if self.scroll > 0:
            s.put(top, max(2, w - 10), "↑ more", s.dim())
        if self.scroll + visible < len(self.rows):
            s.put(y, max(2, w - 10), "↓ more", s.dim())
        s.put(y + 1, 4, tui.fit(self.NOTE, w - 7), s.dim())


# ---------------------------------------------------------------- the screen
class Config(tui.Page):
    title = "config"

    def __init__(self, stdscr, cwd):
        super().__init__(stdscr)
        cli.register_here(cwd)
        here = config.find(cwd)
        self.repos = [Repo(e["path"], e["name"]) for e in projects.load()]
        self.mine = Mine()
        self.station = 0
        self.repositories = Repositories(self)
        self.views = {}
        if here is not None:
            own = config.norm(here.parent)
            found = next((i for i, r in enumerate(self.repos) if config.norm(r.path) == own), None)
            if found is None:  # an atlasmd.toml that cannot be read is not in the list
                self.repos.append(Repo(here.parent))
                self.repos.sort(key=lambda r: (r.name.lower(), str(r.path)))
                found = next(i for i, r in enumerate(self.repos) if config.norm(r.path) == own)
            self.repositories.cursor = found
            self.station = 1
            if self.repos[found].error:
                self.say(f"{self.repos[found].name}: {self.repos[found].error}", problem=True)

    # ------------------------------------------------------------ stations
    def repo(self):
        return self.repositories.selected()

    def view(self, station):
        repo = self.repo()
        key = (station, str(repo.path))
        if key not in self.views:
            self.views[key] = Settings(self, repo) if station == 1 else Files(self, repo)
        return self.views[key]

    def open(self, index, station):
        self.repositories.cursor = index
        self.station = station
        self.say("")

    def names(self):
        repo = self.repo()
        return ["Repositories"] + ([repo.name, "Files"] if repo else [])

    def ask_line(self, prompt):
        h, w = self.scr.getmaxyx()
        y = h - len(tui.footer_rows(HELP[self.station], w)) - 2
        return self.read_line(prompt, y)

    # ------------------------------------------------------------ saving
    def dirty(self):
        return self.mine.dirty() or any(r.dirty() for r in self.repos)

    def save(self):
        count = 0
        for repo in self.repos:
            if repo.dirty():
                try:
                    count += repo.save()
                except (cli.Problem, OSError) as exc:
                    self.say(f"{repo.name}: {exc}", problem=True)
                    return False
        count += self.mine.save()
        self.say("Saved. The hook uses the new values from the next tool call." if count else "Nothing changed.")
        return True

    def confirm_quit(self):
        if not self.dirty():
            return True
        key = self.ask_key("Not saved.  s saves and quits, d quits without a save, another key stays",
                           HELP[self.station])
        if key in (ord("s"), ord("S")):
            return self.save()
        if key in (ord("d"), ord("D")):
            return True
        self.say("")
        return False

    # ------------------------------------------------------------ drawing
    def draw(self):
        self.scr.erase()
        repo = self.repo()
        right = cli.tilde(repo.path) if repo and self.station else cli.tilde(projects.path())
        self.header(right + ("   not saved" if self.dirty() else ""))
        self.draw_route(2, self.names(), self.station)
        if self.station == 0:
            self.repositories.draw(5)
        else:
            self.view(self.station).draw(5)
        self.footer(HELP[self.station])
        self.scr.refresh()

    def loop(self):
        curses = self.curses
        while True:
            self.draw()
            key = self.scr.getch()
            stations = len(self.names())
            if key == curses.KEY_RESIZE:
                self.scr.clear()
            elif key in (ord("q"), ord("Q")):
                if self.confirm_quit():
                    return 0
            elif key in (ord("s"), ord("S")):
                self.save()
            elif key in (TAB, getattr(curses, "KEY_BTAB", BACKTAB), ESCAPE):
                step = 1 if key == TAB else -1
                self.station = 0 if key == ESCAPE else (self.station + step) % stations
                self.say("")
            elif self.station == 0:
                self.repositories.key(key)
            else:
                self.view(self.station).key(key)


def run(cwd=None):
    import curses
    os.environ.setdefault("ESCDELAY", "25")
    return curses.wrapper(lambda stdscr: Config(stdscr, cwd or os.getcwd()).loop())
