"""amd setup: the guided screen. Run it once after the install. It is safe to run again.

Six stations on a route. The route stays at the top. Under it the screen prints each station under the one
before, as a terminal does: a station that is done in the dim color with its answer on one line, the
current station in full with its answers. Up and down move between the answers, Enter picks one, the left
arrow goes back a station, q quits. Nothing is written before the last station, except two things that
the person picks: the link ~/.local/bin/amd on the station The command amd, and the files of amd init on
the station This repository.
"""
import contextlib
import io
import os
import shlex
import shutil
from pathlib import Path

from atlasmd import cli, config, start, tui

STEPS = ["Welcome", "How it works", "The command amd", "You", "This repository", "Done"]
HELP = [("↑↓", "move"), ("enter", "pick"), ("←", "back"), ("q", "quit")]

WELCOME = (
    "Claude starts every session with an empty memory. What it learned in the last session is gone: why a "
    "decision was made, what is open, how you want the work done. The same happens after a compaction. So a "
    "project writes what Claude must know into Markdown files in the repository, and the next session reads "
    "them. These files grow, and a session that reads all of them at every start costs a lot. atlasmd decides "
    "which of these files a session reads at the start, and which of them Claude must read before it changes "
    "a file in a given folder.\n\n"
    "atlasmd is a hook inside Claude Code: a small program that Claude Code runs at the start of a session, "
    "before every edit, and after every compaction.\n\n"
    "## At the start of a session\n"
    f"{cli.WHAT[0]} Those files say what the repository is, what is open, and how to work here. So a new session "
    "knows the repository without reading all of it, and the start costs a few thousand tokens instead "
    "of hundreds of thousands.\n\n"
    "## Before an edit\n"
    f"{cli.WHAT[1]} For example, the README of a folder says how that part works and why. The README of api/ "
    "says that every time is stored as UTC. An agent that did not read it writes local time, and the bug is in "
    "the data for weeks.\n\n"
    "## After a compaction\n"
    "A compaction is what Claude Code does when a chat grows too long: it replaces the chat with a short "
    f"summary. The files that Claude read are then gone from its memory. {cli.WHAT[2]} So you can see what each "
    "compaction costs.\n\n"
    f"This setup has {len(STEPS)} steps. You can change your settings later with amd config or amd set."
)
HOW = (
    "## At the start of a session\n"
    "- The hook reads the Markdown files in docs/start/, in name order, and hands them to Claude.\n"
    "- Claude Code lets a hook hand over at most 10,000 characters at one time.\n"
    "- When the files fit, Claude gets their full text. When they do not, Claude gets the full text of the "
    "first files up to the limit, then the names of the files that did not fit, and reads each of those files "
    "itself, one Read each.\n"
    "- After a compaction the same happens, so a compacted session starts like a fresh one.\n\n"
    "## Before an edit\n"
    "- atlasmd.toml, the settings file of atlasmd at the root of the repository, lists folders. For each folder "
    "it names the files to read before a change there, for example the README of the folder.\n"
    "- Claude is about to change a file in a listed folder. The hook looks up which of the named files "
    "Claude read in this session.\n"
    "- One is missing: the hook refuses the edit and names the files. Claude reads them and edits again.\n\n"
    "## After a compaction\n"
    "- The hook keeps a record of which files each session read, one small file per session, in "
    "~/.claude/plugins/data/amd/ledgers/.\n"
    "- A compaction empties that record, because the files left Claude's memory. So the next edit in a listed "
    "folder reads the files again.\n"
    "- One line goes to compacts.log: date and time, repository folder, manual or automatic, and the "
    "size of the summary."
)
YOU = (
    "Two settings that apply to every repository on this computer.\n\n"
    "1. A repository without atlasmd.toml, that is, a repository where atlasmd is not set up yet. At the start "
    "of a session there, should Claude say once: run /atlasmd:init to set up atlasmd here? Yes or no.\n\n"
    "2. Characters per token. A token is the unit in which the model counts text. atlasmd shows sizes in "
    "tokens, and it counts one token for every 2.5 characters. That fits English text and code. A larger "
    "number gives smaller sizes.\n\n"
    "If you set the option offer_setup in Claude Code with /plugin configure, that value wins over "
    "the first setting here."
)


def short(path):
    text, home = str(path), str(Path.home())
    return "~" + text[len(home):] if text.startswith(home + os.sep) or text == home else text


# ---------------------------------------------------------------- the command amd on the PATH
def plugin_folder():
    """The folder of this plugin: the folder above atlasmd/, with every link resolved."""
    return Path(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def amd_path():
    """bin/amd of this plugin, or bin/amd.cmd on Windows."""
    return plugin_folder() / "bin" / ("amd.cmd" if os.name == "nt" else "amd")


def link_line(home=None):
    """The one command that links ~/.local/bin/amd to bin/amd of this plugin, with mkdir when the folder is missing."""
    line = f"ln -s {shlex.quote(str(amd_path()))} ~/.local/bin/amd"
    folder = Path(home or Path.home()) / ".local" / "bin"
    return line if folder.is_dir() else "mkdir -p ~/.local/bin && " + line


def on_path(folder, path_value=None):
    """True when folder is one of the folders in PATH."""
    value = os.environ.get("PATH", "") if path_value is None else path_value
    target = os.path.normcase(os.path.realpath(folder))
    return any(os.path.normcase(os.path.realpath(os.path.expanduser(p))) == target
               for p in value.split(os.pathsep) if p)


def start_file_line(shell=None):
    """(the start file of the shell in $SHELL, the line there that puts ~/.local/bin on PATH)."""
    name = os.path.basename(os.environ.get("SHELL", "") if shell is None else shell)
    if name == "fish":
        return "~/.config/fish/config.fish", "fish_add_path ~/.local/bin"
    if name == "zsh":
        return "~/.zshrc", 'export PATH="$HOME/.local/bin:$PATH"'
    if name == "bash":
        return "~/.bashrc", 'export PATH="$HOME/.local/bin:$PATH"'
    return "the start file of your shell", 'export PATH="$HOME/.local/bin:$PATH"'


def path_lines(home=None, path_value=None, shell=None):
    """Whether ~/.local/bin is on the PATH of this shell, and when it is not, the line for the start file."""
    folder = Path(home or Path.home()) / ".local" / "bin"
    if on_path(folder, path_value):
        return ["~/.local/bin is on the PATH of this shell, so amd works in this terminal."]
    file, line = start_file_line(shell)
    return [f"~/.local/bin is not on the PATH of this shell. Add this line to {file}, then open a new terminal:",
            "", "    " + line]


def link_amd(home=None, path_value=None, shell=None):
    """Put amd on the PATH: make ~/.local/bin when it is missing, and link ~/.local/bin/amd to bin/amd of this
    plugin. Nothing else in the home folder changes, and an existing ~/.local/bin/amd stays.
    Returns (the answer on one line, the lines to show)."""
    folder = Path(home or Path.home()) / ".local" / "bin"
    link, target = folder / "amd", amd_path()
    if os.path.lexists(link):
        if os.path.realpath(link) == os.path.realpath(target):
            return ("~/.local/bin/amd was there already",
                    [f"~/.local/bin/amd points at {target} already. The setup changed nothing.", ""]
                    + path_lines(home, path_value, shell))
        what = f"a link to {os.readlink(link)}" if link.is_symlink() else "a file"
        return ("~/.local/bin/amd exists, nothing changed",
                [f"~/.local/bin/amd exists, and it is {what}. The setup changed nothing. Remove it and pick this "
                 "answer again, or keep it."])
    ran = []
    try:
        if not folder.is_dir():
            folder.mkdir(parents=True)
            ran.append("mkdir -p ~/.local/bin")
        os.symlink(target, link)
        ran.append(f"ln -s {shlex.quote(str(target))} ~/.local/bin/amd")
    except OSError as exc:
        return ("the link failed",
                [f"The setup could not make the link: {exc.strerror or exc}. Run this command yourself:", "",
                 "    " + link_line(home)])
    return (f"~/.local/bin/amd links to {short(target)}",
            ["The setup ran:", ""] + ["    " + command for command in ran] + [""] + path_lines(home, path_value, shell))


class Setup(tui.Page):
    title = "setup"

    def __init__(self, stdscr, cwd):
        super().__init__(stdscr)
        self.cwd = Path(cwd)
        self.step = 0
        self.cursor = 0
        self.scroll = 0
        self.follow = False
        self.place = True
        self.answers = {}
        self.offer = bool(cli.personal_value("offer_setup"))
        self.chars = float(cli.personal_value("token_chars"))
        self.init_output = None
        self.link_result = None  # (the answer on one line, the lines to show) after a pick on The command amd
        self.saved_to = None
        self.shown = (0, 0)  # the row of the first answer and the rows on the screen, at the last draw

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
        """(markup, [(label, value, hint, action)]) of the current station."""
        if self.step == 0:
            return WELCOME, [("Start", "", "atlasmd saves your answers at the last step", self.next),
                             ("Quit", "", "", self.quit)]
        if self.step == 1:
            return HOW, [("Continue", "", "", self.next)]
        if self.step == 2:
            return self.command_step()
        if self.step == 3:
            return YOU, [
                ("Suggest /atlasmd:init", "yes" if self.offer else "no",
                 "in a repository without atlasmd.toml", self.toggle_offer),
                ("Characters per token, for the sizes", f"{self.chars:g}", "Enter types a number", self.type_chars),
                ("Continue", "", "", self.next),
            ]
        if self.step == 4:
            return self.project_step()
        lines = [
            "## Saved",
            f"- Your settings: {short(self.saved_to)}" if self.saved_to else "- Your settings: not saved",
            f"- Suggest /atlasmd:init in a repository without atlasmd.toml: {'yes' if self.offer else 'no'}",
            f"- Characters per token: {self.chars:g}",
            "",
            "## Three commands to remember",
            "- /atlasmd:init, in a Claude Code session, writes atlasmd.toml, fills docs/start/, and lists which files "
            "Claude reads before it changes a file in each folder.",
            "- amd check, in a terminal, finds problems: docs/start/ over its token limit, files that atlasmd.toml "
            "names but that do not exist, and file names that break the rule of their folder.",
            "- amd why, in a terminal, shows the last edit that the hook refused, and the files that Claude had not read.",
            "",
            "amd config shows every command, the skills and how to set up a repository on its first station, About. "
            "You can run amd setup again at any time.",
        ]
        return "\n".join(lines), [("Finish", "", "", self.quit)]

    def command_step(self):
        target = amd_path()
        why = ("In a Claude Code session, the skills of atlasmd run amd by the full path of the plugin, so Claude "
               "needs nothing more. Your own terminal finds a command only in the folders of your PATH. This step "
               "makes amd work there too.")
        if os.name == "nt":
            text = (f"{why} The setup does not change PATH on Windows. Add this folder to your PATH once. "
                    f"The launcher in it is amd.cmd.\n\n    {target.parent}\n\n"
                    f"Without it, amd works by its full path: {target}")
            return text, [("Continue", "", "", self.next)]
        if self.link_result is not None:
            return "\n".join(self.link_result[1]), [("Continue", "", "", self.next)]
        found = shutil.which("amd")
        if found and os.path.realpath(found) == os.path.realpath(target):
            text = f"amd works in this terminal already: {short(found)} points at {target}."
            return text, [("Continue", "", "", self.next)]
        text = (f"{why} Put amd on my PATH now makes the folder ~/.local/bin when it is missing, and the link "
                f"~/.local/bin/amd to {target}. Nothing else in your home folder changes.\n\n"
                f"Without the link, amd works by its full path: {target}")
        return text, [("Put amd on my PATH now", "", "makes the link now", self.make_link),
                      ("Not now", "", "", self.not_now)]

    def project_step(self):
        cfg, error = self.project()
        root = cli.project_root(self.cwd)
        if self.init_output is not None:
            made = self.init_output.split("Made:", 1)[-1].split("\n\n", 1)[0]
            text = "amd init ran in " + short(root) + ". It made these:\n\n" + "\n".join(
                "- " + line.strip() for line in made.splitlines() if line.strip())
            text += ("\n\nIn a Claude Code session, /atlasmd:init then fills the four files of docs/start/ and "
                     "proposes which files Claude reads before a change in each folder.")
            return text, [("Continue", "", "", self.next)]
        if error:
            return f"atlasmd.toml of this repository has a problem.\n\n{error}", [("Continue", "", "", self.next)]
        if cfg is None:
            text = (f"This folder has no atlasmd.toml: {short(root)}.\n\n"
                    "amd init writes atlasmd.toml, the settings file of atlasmd, four files in docs/start/ with their "
                    "headings and nothing under them, and the empty folders "
                    "docs/decisions/, docs/plans/, docs/notes/ and docs/archive/. It overwrites nothing. In a Claude "
                    "Code session, /atlasmd:init does more: it reads the repository, fills the four files, and proposes "
                    "which files Claude reads before a change in each folder.")
            return text, [("Run amd init now", "", "writes in " + short(root) + " now", self.run_init),
                          ("Skip", "", "", self.next)]
        composed = start.compose(cfg)
        n = len(composed.files)
        lines = [f"The repository: {short(cfg.root)}", "",
                 "## At the start of a session",
                 f"Claude gets {n} file{'s' if n != 1 else ''}, about {composed.tokens:,} tokens. "
                 f"The limit in start.budget is {cfg.start.budget:,}." +
                 (" The files are over this limit." if composed.over_budget else ""), "",
                 "## Before an edit"]
        if not cfg.areas:
            lines.append("atlasmd.toml lists no folders yet. /atlasmd:init in a Claude Code session proposes them.")
        for area in cfg.areas:
            n = len(area.pack)
            p = len(area.paths)
            lines.append(f"- {area.name}: {n} file{'s' if n != 1 else ''} to read before a change in "
                         f"its {p} path{'s' if p != 1 else ''}")
        lines += ["", "amd check shows the details."]
        return "\n".join(lines), [("Continue", "", "", self.next)]

    def answer(self):
        """The answer of the current station, on one line, for the stations that are done."""
        if self.step == 2:
            if os.name == "nt":
                return f"add {amd_path().parent} to PATH"
            return self.link_result[0] if self.link_result else "amd works in this terminal already"
        if self.step == 3:
            return (f"suggest /atlasmd:init: {'yes' if self.offer else 'no'}   "
                    f"characters per token: {self.chars:g}")
        if self.step == 4:
            root = cli.project_root(self.cwd)
            if self.init_output is not None:
                return f"amd init ran in {short(root)}"
            cfg, error = self.project()
            if error:
                return "atlasmd.toml has a problem"
            return f"atlasmd.toml is in {short(cfg.root)}" if cfg else f"skipped, no atlasmd.toml in {short(root)}"
        return "Start" if self.step == 0 else "Continue"

    # ------------------------------------------------------------ actions
    def goto(self, step):
        self.step = step
        self.cursor = 0
        self.follow = False
        self.place = True
        self.say("")

    def next(self):
        self.answers[self.step] = self.answer()
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

    def make_link(self):
        self.link_result = link_amd()
        self.cursor = 0
        self.follow = True

    def not_now(self):
        lines = ["Not now. To put amd on your PATH later, run this command once in a terminal:", "",
                 "    " + link_line(), ""] + path_lines()
        self.link_result = (f"not now. Later: {link_line()}", lines)
        self.cursor = 0
        self.follow = True

    def run_init(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["init"], cwd=str(self.cwd))
        self.init_output = buf.getvalue()
        self.cursor = 0
        self.follow = True
        if code != 0:
            self.say(self.init_output.strip().splitlines()[-1] if self.init_output.strip() else "amd init failed",
                     problem=True)

    def confirm_quit(self):
        if self.step in (0, len(STEPS) - 1):
            return True
        note = "Leave the setup? Your settings are not saved."
        if self.init_output is not None:
            note += " The files that amd init wrote stay."
        if self.link_result is not None and self.link_result[0].startswith("~/.local/bin/amd links"):
            note += " The link ~/.local/bin/amd stays."
        key = self.ask_key(note + "  y leaves, another key stays", HELP)
        self.say("")
        return key in (ord("y"), ord("Y"))

    # ------------------------------------------------------------ drawing
    def stack(self, width):
        """The rows under the route, as a terminal prints them: the logo, one line for each station that is
        done, then the current station in full. Returns (rows, the row of the current heading, the row of its
        first answer, the answers)."""
        h, w = self.scr.getmaxyx()
        rows = []
        if h >= 24 and w >= 40:
            rows += [("logo", line) for line in tui.LOGO] + [("tagline", tui.TAGLINE), ("blank", None)]
        rows += [("done", i) for i in range(self.step)]
        if self.step:
            rows.append(("blank", None))
        head = len(rows)
        rows += [("current", self.step), ("blank", None)]
        body, options = self.content()
        rows += [("text", item) for item in tui.wrap(body, width)] + [("blank", None)]
        first = len(rows)
        rows += [("option", (i, option)) for i, option in enumerate(options)]
        return rows, head, first, options

    def draw(self):
        curses = self.curses
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        self.header(f"step {self.step + 1} of {len(STEPS)}")
        self.draw_route(2, STEPS, self.step)
        top = 5
        rows, head, first, options = self.stack(min(76, max(20, w - 7)))
        self.cursor = max(0, min(self.cursor, len(options) - 1))
        bottom = len(tui.footer_rows(HELP, w)) + 2
        visible = max(1, h - top - bottom)
        if self.place:  # a new station: the stack scrolls up, but never past the heading of the current station
            self.scroll = min(head, max(0, len(rows) - visible)) if self.step else 0
            self.place = False
        if self.follow:
            at = first + self.cursor
            if at < self.scroll:
                self.scroll = at
            elif at >= self.scroll + visible:
                self.scroll = at - visible + 1
            self.follow = False
        self.scroll = max(0, min(self.scroll, max(0, len(rows) - visible)))
        self.shown = (first, visible)
        name_w = max(len(name) for name in STEPS)
        label_w = max([len(o[0]) for o in options if o[1]] or [0])
        y = top
        for kind, data in rows[self.scroll:self.scroll + visible]:
            if kind == "logo":
                self.put(y, 2, data, self.accent())
            elif kind == "tagline":
                self.put(y, 2, data, self.dim())
            elif kind == "done":
                self.put(y, 2, f"{tui.PASSED} {STEPS[data]}", self.dim())
                self.put(y, 4 + name_w + 2, tui.fit(self.answers.get(data, ""), w - name_w - 9), self.dim())
            elif kind == "current":
                self.put(y, 2, f"{tui.CURRENT} {STEPS[data]}", self.accent())
            elif kind == "text":
                style, line = data
                if style == "heading":
                    self.put(y, 4, line, self.accent())
                elif style == "command":
                    self.put(y, 6, line, curses.A_BOLD)
                else:
                    self.put(y, 4, line)
            elif kind == "option":
                i, (label, value, hint, _action) = data
                selected = i == self.cursor
                self.put(y, 4, "›" if selected else " ", self.accent())
                self.put(y, 6, tui.fit(label, w - 10), curses.A_BOLD if selected else 0)
                x = 6 + (max(label_w, len(label)) if value else len(label)) + 2
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

    def answer_shown(self):
        """True when the answer under the cursor was on the screen at the last draw."""
        first, visible = self.shown
        return self.scroll <= first + self.cursor < self.scroll + visible

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
                if not self.answer_shown() and self.scroll < self.shown[0] + self.cursor:
                    self.scroll += 1  # the text first: the answers come into view one row at a time
                elif self.cursor < len(options) - 1:
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
                if not self.answer_shown():
                    self.follow = True  # an answer is picked only when it is on the screen
                elif options[self.cursor][3]() == "quit":
                    return 0


def run(cwd=None):
    import curses
    return curses.wrapper(lambda stdscr: Setup(stdscr, cwd or os.getcwd()).loop())
