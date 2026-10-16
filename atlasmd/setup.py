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
    "atlasmd is a plugin for Claude Code. It gives every session of a project the same small "
    "start reading, at the start and after each compaction. It makes an agent read the guide of an "
    "area before the agent changes the area. After each compaction it writes one line to a log, so "
    "you can see what the compaction cost."
)
HOW = (
    "## The start reading\n"
    "A project keeps the files that every session reads first in one folder, docs/start/, numbered "
    "in the order of the read. At each start and after each compaction, the hook gives these files "
    "to the session, within a budget of tokens. So a fresh session and a compacted session start "
    "with the same reading. Claude Code takes at most 10,000 characters from a hook, so a longer start "
    "reading comes as a list of the files, and the session reads each file.\n\n"
    "## The guard\n"
    "A project names its areas in atlasmd.toml. Each area has code paths and a pack: the Markdown "
    "files to read before a change in the area. The hook refuses an edit or a write in an area "
    "until the agent read every file of the pack in this session.\n\n"
    "## The ledger after a compaction\n"
    "The ledger records the files that each session and each agent read. A compaction removes those "
    "files from the context, so the ledger starts again, and the first change in an area reads the "
    "pack again. The log gets one line for each compaction: the time, the project, the trigger and "
    "the size of the summary."
)
YOU = ("Two settings of your own. They apply to every project on this computer. "
       "When the option offer_setup of the plugin is set in Claude Code, that option wins.")


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
            return WELCOME, [("Start", "", "nothing is written before the last step", self.next),
                             ("Quit", "", "", self.quit)]
        if self.step == 1:
            return HOW, [("Continue", "", "", self.next)]
        if self.step == 2:
            return YOU, [
                ("Offer the setup in a new project", "yes" if self.offer else "no",
                 "Enter switches it", self.toggle_offer),
                ("Characters per token", f"{self.chars:g}", "Enter types a number", self.type_chars),
                ("Continue", "", "", self.next),
            ]
        if self.step == 3:
            return self.project_step()
        lines = [
            "## Saved",
            f"- Your settings: {short(self.saved_to)}" if self.saved_to else "- Your settings: not saved",
            f"- Offer the setup in a new project: {'yes' if self.offer else 'no'}",
            f"- Characters per token: {self.chars:g}",
            "",
            "## Three commands to remember",
            "- /amd:init in a Claude Code session sets up a project: the areas, the start reading and the names.",
            "- amd check in a terminal shows the budget, the packs, the names and the map.",
            "- amd why in a terminal explains the last change that the guard refused.",
            "",
            "Run amd setup again at any time. amd config shows the settings of a project.",
        ]
        return "\n".join(lines), [("Finish", "", "", self.quit)]

    def project_step(self):
        cfg, error = self.project()
        root = cli.project_root(self.cwd)
        if self.init_output is not None:
            made = self.init_output.split("Made:", 1)[-1].split("\n\n", 1)[0]
            text = "amd init ran in " + short(root) + ". It made these:\n\n" + "\n".join(
                "- " + line.strip() for line in made.splitlines() if line.strip())
            text += ("\n\nIn a Claude Code session, /amd:init proposes the areas and fills the four files "
                     "of docs/start/.")
            return text, [("Continue", "", "", self.next)]
        if error:
            return f"atlasmd.toml of this project has a problem.\n\n{error}", [("Continue", "", "", self.next)]
        if cfg is None:
            text = (f"This folder has no atlasmd.toml: {short(root)}.\n\n"
                    "amd init writes atlasmd.toml, the four files of docs/start/ and the folders of the "
                    "convention. It overwrites nothing. In a Claude Code session, /amd:init does more: it reads "
                    "the project, proposes the areas, and fills the four files.")
            return text, [("Run amd init now", "", "writes in " + short(root) + " now", self.run_init),
                          ("Skip", "", "", self.next)]
        composed = start.compose(cfg)
        lines = [f"The project: {short(cfg.root)}", "",
                 "## The start reading",
                 f"About {composed.tokens:,} of {cfg.start.budget:,} tokens, in {len(composed.files)} files." +
                 (" This is over the budget." if composed.over_budget else ""), "", "## The areas"]
        if not cfg.areas:
            lines.append("No areas yet. /amd:init in a session proposes them.")
        for area in cfg.areas:
            n = len(area.pack)
            p = len(area.paths)
            lines.append(f"- {area.name}: {p} code path{'s' if p != 1 else ''}, {n} file{'s' if n != 1 else ''} in the pack")
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
            note += " The files of amd init stay."
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
