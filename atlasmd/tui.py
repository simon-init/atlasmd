"""The look of atlasmd, shared by the command line and the two screens.

The motif is a route on a map. Steps and areas are stations on one line:
● a station passed, ◉ the current station, ○ a station ahead, joined by ──.
One accent color for the current station, the headings and the keys. A dim color
for the help and the passed stations. Red only for a problem. Nothing else is colored.

The plain parts (logo, route, fit, wrap, footer rows) need no curses, so the command
line uses them on every system. The Page class needs curses and imports it late.
"""
import os
import sys
import textwrap

LOGO = [
    "     ▄█▄ █                     █",
    "▄▀▀█  █  █  ▄▀▀█ ▄█▀▀ █▀█▀▄ ▄▀▀█",
    "▀▄▄█  ▀▄ ▀▄ ▀▄▄█ ▄▄█▀ █ █ █ ▀▄▄█",
]
TAGLINE = "Read the map, then build."

PASSED, CURRENT, AHEAD = "●", "◉", "○"
LABEL_MAX = 16


# ---------------------------------------------------------------- plain text parts
def fit(text, width):
    """The text cut to width, with an ellipsis when it was cut."""
    text = str(text)
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[:width - 1].rstrip() + "…"


def wrap(markup, width):
    """[(style, line)] for a text with blank lines between paragraphs, '## ' headings, '- ' items and
    commands, which start with four spaces and never wrap. Styles: heading, item, command, plain."""
    out = []
    width = max(12, width)
    for para in markup.split("\n"):
        if not para.strip():
            if out and out[-1][1]:
                out.append(("plain", ""))
            continue
        if para.startswith("    "):
            out.append(("command", para.strip()))
        elif para.startswith("## "):
            out.append(("heading", para[3:].strip()))
        elif para.startswith("- "):
            lines = textwrap.wrap(para[2:], width=width - 2, break_on_hyphens=False) or [""]
            out.append(("item", "· " + lines[0]))
            out.extend(("item", "  " + line) for line in lines[1:])
        else:
            out.extend(("plain", line) for line in
                       textwrap.wrap(para, width=width, break_on_hyphens=False) or [""])
    while out and not out[-1][1]:
        out.pop()
    return out


def route(names, current, width, passed_all_before=True):
    """The route as two rows of segments, ready to draw: (marks, labels).

    Each row is a list of (x, text, kind). kind is passed, current, ahead, line or more.
    current is the index of the current station, or -1 when no station is current.
    When the stations do not fit the width, a window around the current one is shown,
    with an ellipsis at a cut end."""
    labels = [fit(n, LABEL_MAX) for n in names]
    if not labels:
        return [], []
    cols = [len(lab) + 2 for lab in labels]

    def span(lo, hi):
        return sum(cols[lo:hi]) - 2 + (2 if lo > 0 else 0) + (2 if hi < len(labels) else 0)

    lo, hi = 0, len(labels)
    focus = max(0, current)
    while hi - lo > 1 and span(lo, hi) > width:
        # drop the station farthest from the focus
        if focus - lo > hi - 1 - focus:
            lo += 1
        else:
            hi -= 1
    marks, under = [], []
    x = 0
    if lo > 0:
        marks.append((x, "…─", "more"))
        x += 2
    for i in range(lo, hi):
        if current < 0:
            kind = "ahead"
        elif i < current:
            kind = "passed" if passed_all_before else "ahead"
        elif i == current:
            kind = "current"
        else:
            kind = "ahead"
        mark = {"passed": PASSED, "current": CURRENT, "ahead": AHEAD}[kind]
        marks.append((x, mark, kind))
        under.append((x, labels[i], kind))
        if i < hi - 1 or hi < len(labels):
            marks.append((x + 1, "─" * (cols[i] - 1), "line"))
        x += cols[i]
    if hi < len(labels):
        marks.append((x, "…", "more"))
    return marks, under


def footer_rows(keys, width):
    """The key cells packed into as few rows as fit the width. keys is [(key, meaning)]."""
    rows, row, used = [], [], 0
    for key, meaning in keys:
        need = len(key) + 1 + len(meaning) + 3
        if row and used + need > width - 2:
            rows.append(row)
            row, used = [], 0
        row.append((key, meaning))
        used += need
    if row:
        rows.append(row)
    return rows


# ---------------------------------------------------------------- color in plain output
def use_color(stream=None):
    stream = stream or sys.stdout
    return (hasattr(stream, "isatty") and stream.isatty() and os.environ.get("NO_COLOR") is None
            and os.environ.get("TERM") != "dumb" and os.name != "nt")


ANSI = {"accent": "\033[1;33m", "dim": "\033[2m", "problem": "\033[31m", "bold": "\033[1m"}


def paint(text, kind, color):
    if not color or kind not in ANSI:
        return text
    return ANSI[kind] + text + "\033[0m"


def route_text(names, current, width, color=False):
    """The route as two plain strings, for output outside curses."""
    kinds = {"passed": "dim", "current": "accent", "line": "dim", "more": "dim"}
    lines = []
    for row in route(names, current, width):
        parts, used = [], 0
        for x, seg, kind in row:
            parts.append(" " * (x - used) + paint(seg, kinds.get(kind, ""), color))
            used = x + len(seg)
        lines.append("".join(parts))
    return lines


# ---------------------------------------------------------------- curses
class Page:
    """The shared parts of a curses screen: colors, the header, the route, the footer,
    a text input on the status row. A subclass draws the body and runs the loop."""

    title = ""

    def __init__(self, stdscr):
        import curses
        self.curses = curses
        self.scr = stdscr
        self.message = ""
        self.problem = False
        self.colors = False
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                back = -1
            except curses.error:
                back = curses.COLOR_BLACK
            curses.init_pair(1, curses.COLOR_YELLOW, back)
            curses.init_pair(2, curses.COLOR_RED, back)
            self.colors = True

    # attributes
    def accent(self, bold=True):
        a = self.curses.color_pair(1) if self.colors else 0
        return a | (self.curses.A_BOLD if bold else 0)

    def dim(self):
        return self.curses.A_DIM

    def red(self):
        return (self.curses.color_pair(2) if self.colors else 0) | self.curses.A_BOLD

    def put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and 0 <= x < w - 1 and text:
            try:
                self.scr.addnstr(y, x, text, max(0, w - x - 1), attr)
            except self.curses.error:
                pass

    def header(self, right=""):
        """Row 0: the name, the screen's title, and a note on the right."""
        h, w = self.scr.getmaxyx()
        self.put(0, 2, "atlasmd", self.accent())
        self.put(0, 11, self.title, self.dim())
        if right:
            room = w - 11 - len(self.title) - 6
            if room > 8:
                text = fit(right, room)
                self.put(0, w - len(text) - 3, text, self.dim())

    def draw_route(self, y, names, current, x=2):
        h, w = self.scr.getmaxyx()
        marks, under = route(names, current, w - x - 3)
        attrs = {"passed": self.dim(), "current": self.accent(), "ahead": 0,
                 "line": self.dim(), "more": self.dim()}
        for seg_x, text, kind in marks:
            self.put(y, x + seg_x, text, attrs[kind])
        for seg_x, text, kind in under:
            self.put(y + 1, x + seg_x, text, attrs[kind])

    def footer(self, keys):
        """The status row and the key rows at the bottom. Returns the rows they take."""
        h, w = self.scr.getmaxyx()
        rows = footer_rows(keys, w)
        for i, row in enumerate(rows):
            y = h - len(rows) + i
            x = 2
            for key, meaning in row:
                self.put(y, x, key, self.accent())
                x += len(key) + 1
                self.put(y, x, meaning, self.dim())
                x += len(meaning) + 3
        if self.message:
            self.put(h - len(rows) - 2, 2, fit(self.message, w - 5), self.red() if self.problem else 0)
        return len(rows) + 2

    def say(self, text, problem=False):
        self.message, self.problem = text, problem

    def ask_key(self, question, keys):
        """Show a question on the status row and return the next key pressed."""
        h, w = self.scr.getmaxyx()
        y = h - len(footer_rows(keys, w)) - 2
        self.put(y, 0, " " * (w - 1))
        self.put(y, 2, fit(question, w - 5), self.accent())
        self.scr.refresh()
        return self.scr.getch()

    def read_line(self, prompt, y):
        """A line of text typed on row y. Returns the text, or None after Escape."""
        curses = self.curses
        h, w = self.scr.getmaxyx()
        self.put(y, 0, " " * (w - 1))
        self.put(y, 2, prompt, self.accent())
        self.scr.refresh()
        curses.echo()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        try:
            raw = self.scr.getstr(y, 2 + len(prompt), max(1, w - len(prompt) - 5))
        except curses.error:
            raw = b""
        finally:
            curses.noecho()
            try:
                curses.curs_set(0)
            except curses.error:
                pass
        return raw.decode("utf-8", "ignore").strip()


def needs_terminal(name):
    """The message for a screen that runs without a terminal. None when there is one."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        return None
    return f"amd {name} is a screen and needs a terminal. Open a terminal and run: amd {name}"
