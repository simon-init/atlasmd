"""amd setup: the guided screen. Run it once after the install. It is safe to run again.

Five steps, drawn as stations on a route. Up and down move between the answers, Enter
picks one, the left arrow goes back a step, q quits. Nothing is written before the last
step, except the files of amd init when the person runs it on the step This project.
"""
import contextlib
import io
import os
from pathlib import Path

from atlasmd import cli, config, start, tui

STEPS = ["Welcome", "How it works", "You", "This project", "Done"]
HELP = [("↑↓", "move"), ("enter", "pick"), ("←", "back"), ("q", "quit")]

WELCOME = (
    "atlasmd is a hook inside Claude Code. It runs at the start of a session, before every edit, "
    "and after every compaction.\n\n"
    "## At the start of a session\n"
    "It gives Claude the Markdown files in docs/start/ of your project, and nothing else. Those files "
    "say what the project is, what is open, and how to work here. So a new session knows the project "
    "without reading the whole repository, and the start costs a few thousand tokens instead of "
    "hundreds of thousands.\n\n"
    "## Before an edit\n"
    "When the file is in a folder that atlasmd.toml lists, it refuses the edit until Claude has read "
    "the files listed for that folder, for example the folder's README. The README says how that part "
    "works and why. For example: the README of api/ says that every time is stored as UTC. An agent "
    "that did not read it writes local time, and the bug is in the data for weeks.\n\n"
    "## After a compaction\n"
    "A compaction removes the files Claude read from its context. So atlasmd makes Claude read the "
    "listed files again before its next edit, and it writes the date, the project folder and the size "
    "of the summary to compacts.log, so you can see what each compaction costs.\n\n"
    "This setup has five steps. Every answer can be changed later with amd config or amd set."
)
HOW = (
    "## At the start of a session\n"
    "- The hook reads the Markdown files in docs/start/, in name order, and hands them to Claude.\n"
    "- A hook can hand over at most 10,000 characters.\n"
    "- Shorter: Claude gets the text. Longer: Claude gets the list and reads each file, one Read each.\n"
    "- After a compaction the same happens, so a compacted session starts like a fresh one.\n\n"
    "## Before an edit\n"
    "- atlasmd.toml lists folders. For each folder it lists the files to read before a change there.\n"
    "- Claude is about to change a file in a listed folder. The hook looks up which listed files "
    "Claude read in this session.\n"
    "- One is missing: the hook refuses the edit and names the files. Claude reads them and edits again.\n\n"
    "## After a compaction\n"
    "- The hook keeps the list of files each session read, in ~/.claude/plugins/data/amd/ledgers/.\n"
    "- A compaction empties that list, so the next edit in a listed folder reads the files again.\n"
    "- One line goes to compacts.log: date and time, project folder, manual or automatic, and the "
    "size of the summary."
)
YOU = (
    "Two settings that apply to every project on this computer.\n\n"
    "1. A project without atlasmd.toml. At the start of a session there, should Claude say once: "
    "run /amd:init to set up atlasmd here? Yes or no.\n\n"
    "2. Characters per token. atlasmd shows sizes in tokens, and it counts one token for every "
    "2.5 characters. That fits English text and code. A larger number gives smaller sizes.\n\n"
    "If you set the option offer_setup in Claude Code with /plugin configure, that value wins over "
    "the first setting here."
)


def short(path):
    text, home = str(path), str(Path.home())
    return "~" + text[len(home):] if text.startswith(home + os.sep) or text == home else text


class Setup(tui.Page):
    title = "setup"

    def __init__(self, stdscr, cwd):
        super().__init__(stdscr)
        self.cwd = Path(cwd)
        self.step = 0
        self.cursor = 0
        self.scroll = 0
        self.follow = False
        self.offer = bool(cli.personal_value("offer_setup"))
        self.chars = float(cli.personal_value("token_chars"))
        self.init_output = None
        self.saved_to = None

    # ------------------------------------------------------------ content
    def project(self):
        path = config.find(self.cwd)
        if path is None:
            return None, None
        try:
            return config.load(path), None
        except config.ConfigError as exc:
            return None, str(exc)

    def content(self):
        """(markup, [(label, value, hint, action)]) of the current step."""
        if self.step == 0:
            return WELCOME, [("Start", "", "atlasmd saves your answers at the last step", self.next),
                             ("Quit", "", "", self.quit)]
        if self.step == 1:
            return HOW, [("Continue", "", "", self.next)]
        if self.step == 2:
            return YOU, [
                ("Suggest /amd:init", "yes" if self.offer else "no",
                 "in a project without atlasmd.toml", self.toggle_offer),
                ("Characters per token, for the sizes", f"{self.chars:g}", "Enter types a number", self.type_chars),
                ("Continue", "", "", self.next),
            ]
        if self.step == 3:
            return self.project_step()
        lines = [
            "## Saved",
            f"- Your settings: {short(self.saved_to)}" if self.saved_to else "- Your settings: not saved",
            f"- Suggest /amd:init in a project without atlasmd.toml: {'yes' if self.offer else 'no'}",
            f"- Characters per token: {self.chars:g}",
            "",
            "## Three commands to remember",
            "- /amd:init, in a Claude Code session, writes atlasmd.toml, fills docs/start/, and lists which files "
            "Claude reads before it changes a file in each folder.",
            "- amd check, in a terminal, finds problems: docs/start/ over its token limit, listed files that do not "
            "exist, and file names that break the rule of their folder.",
            "- amd why, in a terminal, shows the last edit that the hook refused, and the files that Claude had not read.",
            "",
            "You can run amd setup again at any time. amd config shows and changes atlasmd.toml of a project.",
        ]
        return "\n".join(lines), [("Finish", "", "", self.quit)]

    def project_step(self):
        cfg, error = self.project()
        root = cli.project_root(self.cwd)
        if self.init_output is not None:
            made = self.init_output.split("Made:", 1)[-1].split("\n\n", 1)[0]
            text = "amd init ran in " + short(root) + ". It made these:\n\n" + "\n".join(
                "- " + line.strip() for line in made.splitlines() if line.strip())
            text += ("\n\nIn a Claude Code session, /amd:init then fills the four files of docs/start/ and "
                     "proposes which files Claude reads before a change in each folder.")
            return text, [("Continue", "", "", self.next)]
        if error:
            return f"atlasmd.toml of this project has a problem.\n\n{error}", [("Continue", "", "", self.next)]
        if cfg is None:
            text = (f"This folder has no atlasmd.toml: {short(root)}.\n\n"
                    "amd init writes atlasmd.toml, four template files in docs/start/, and the empty folders "
                    "docs/decisions/, docs/plans/, docs/notes/ and docs/archive/. It overwrites nothing. In a Claude "
                    "Code session, /amd:init does more: it reads the project, fills the four files, and proposes "
                    "which files Claude reads before a change in each folder.")
            return text, [("Run amd init now", "", "writes in " + short(root) + " now", self.run_init),
                          ("Skip", "", "", self.next)]
        composed = start.compose(cfg)
        n = len(composed.files)
        lines = [f"The project: {short(cfg.root)}", "",
                 "## At the start of a session",
                 f"Claude gets {n} file{'s' if n != 1 else ''}, about {composed.tokens:,} tokens. "
                 f"The limit in start.budget is {cfg.start.budget:,}." +
                 (" The files are over this limit." if composed.over_budget else ""), "",
                 "## Before an edit"]
        if not cfg.areas:
            lines.append("atlasmd.toml lists no folders yet. /amd:init in a Claude Code session proposes them.")
        for area in cfg.areas:
            n = len(area.pack)
            p = len(area.paths)
            lines.append(f"- {area.name}: {n} file{'s' if n != 1 else ''} to read before a change in "
                         f"its {p} path{'s' if p != 1 else ''}")
        lines += ["", "amd check shows the details."]
        return "\n".join(lines), [("Continue", "", "", self.next)]

    # ------------------------------------------------------------ actions
    def goto(self, step):
        self.step = step
        self.cursor = 0
        self.scroll = 0
        self.follow = False
        self.say("")
        self.scr.clear()

    def next(self):
        if self.step == len(STEPS) - 2:
            self.saved_to = cli.save_personal({"offer_setup": self.offer, "token_chars": round(self.chars, 2)})
        self.goto(self.step + 1)

    def back(self):
        if 0 < self.step < len(STEPS) - 1:
            self.goto(self.step - 1)

    def quit(self):
        return "quit"

    def toggle_offer(self):
        self.offer = not self.offer

    def type_chars(self):
        h, w = self.scr.getmaxyx()
        y = h - len(tui.footer_rows(HELP, w)) - 2
        text = self.read_line("Characters per token, for example 2.5: ", y)
        if not text:
            return
        try:
            self.chars = cli.parse_personal("token_chars", text)
        except cli.Problem as exc:
            self.say(str(exc), problem=True)

    def run_init(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["init"], cwd=str(self.cwd))
        self.init_output = buf.getvalue()
        self.cursor = 0
        if code != 0:
            self.say(self.init_output.strip().splitlines()[-1] if self.init_output.strip() else "amd init failed",
                     problem=True)

    def confirm_quit(self):
        if self.step in (0, len(STEPS) - 1):
            return True
        note = "Leave the setup? Nothing is saved."
        if self.init_output is not None:
            note += " The files that amd init wrote stay."
        key = self.ask_key(note + "  y leaves, another key stays", HELP)
        self.say("")
        return key in (ord("y"), ord("Y"))

    # ------------------------------------------------------------ drawing
    def draw(self):
        curses = self.curses
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self.header(f"step {self.step + 1} of {len(STEPS)}")
        y = 2
        if self.step == 0 and h >= 24 and w >= 40:
            for line in tui.LOGO:
                self.put(y, 2, line, self.accent())
                y += 1
            self.put(y, 2, tui.TAGLINE, self.dim())
            y += 2
        self.draw_route(y, STEPS, self.step)
        y += 3
        self.put(y, 2, tui.fit(STEPS[self.step], w - 5), self.accent())
        y += 2
        width = min(76, max(20, w - 5))
        body, options = self.content()
        self.cursor = max(0, min(self.cursor, len(options) - 1))
        rows = [("text", style, line) for style, line in tui.wrap(body, width)] + [("text", "plain", "")]
        first = len(rows)
        rows += [("option", i, opt) for i, opt in enumerate(options)]
        bottom = len(tui.footer_rows(HELP, w)) + 2
        visible = max(1, h - y - bottom)
        if self.follow:
            at = first + self.cursor
            if at < self.scroll:
                self.scroll = at
            elif at >= self.scroll + visible:
                self.scroll = at - visible + 1
            self.follow = False
        self.scroll = max(0, min(self.scroll, max(0, len(rows) - visible)))
        top = y
        label_w = max([len(o[0]) for o in options if o[1]] or [0])
        for row in rows[self.scroll:self.scroll + visible]:
            if row[0] == "text":
                _, style, line = row
                attr = self.accent() if style == "heading" else 0
                self.put(y, 2, line, attr)
            else:
                _, i, (label, value, hint, _action) = row
                selected = i == self.cursor
                self.put(y, 2, "›" if selected else " ", self.accent())
                self.put(y, 4, tui.fit(label, w - 8), curses.A_BOLD if selected else 0)
                x = 4 + (max(label_w, len(label)) if value else len(label)) + 2
                if value:
                    self.put(y, x, value, curses.A_BOLD)
                    x += len(value) + 2
                if hint and x < w - 8:
                    self.put(y, x, tui.fit(hint, w - x - 3), self.dim())
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
            options = self.content()[1]
            if key == curses.KEY_RESIZE:
                self.scr.clear()
            elif key in (ord("q"), ord("Q")):
                if self.confirm_quit():
                    return 0
            elif key in (curses.KEY_UP, ord("k")):
                if self.cursor > 0:
                    self.cursor, self.follow = self.cursor - 1, True
                else:
                    self.scroll -= 1
            elif key in (curses.KEY_DOWN, ord("j")):
                if self.cursor < len(options) - 1:
                    self.cursor, self.follow = self.cursor + 1, True
                else:
                    self.scroll += 1
            elif key == curses.KEY_PPAGE:
                self.scroll -= 5
            elif key == curses.KEY_NPAGE:
                self.scroll += 5
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8, ord("h")):
                self.back()
            elif key in (curses.KEY_ENTER, 10, 13, ord(" ")):
                self.cursor = max(0, min(self.cursor, len(options) - 1))
                if options[self.cursor][3]() == "quit":
                    return 0


def run(cwd=None):
    import curses
    return curses.wrapper(lambda stdscr: Setup(stdscr, cwd or os.getcwd()).loop())
