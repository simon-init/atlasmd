"""One value of atlasmd.toml changed in its text, so that every other line and comment stays as it is.

The key is replaced where it stands in its table. A key that stands as a comment, such as
`# group = "my-project"`, is uncommented and set. A missing key goes after the last key of its table,
and a missing table goes at the end. The table "" is the top of the file, above the first table.
"""
from __future__ import annotations

import json
import re

HEADER = re.compile(r"^\s*\[{1,2}\s*([^\]]+?)\s*\]{1,2}\s*(#.*)?$")
LIST_WIDTH = 96


def literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}" if isinstance(value, float) else str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(literal(v) for v in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _region(lines: list[str], table: str) -> tuple[int, int] | None:
    """The first and the last line + 1 of the keys of a table, or None when the table is missing."""
    headers = [(i, m.group(1), line.lstrip().startswith("[[")) for i, line in enumerate(lines)
               for m in [HEADER.match(line)] if m]
    if not table:
        return 0, headers[0][0] if headers else len(lines)
    for n, (i, name, array) in enumerate(headers):
        if name == table and not array:
            return i + 1, headers[n + 1][0] if n + 1 < len(headers) else len(lines)
    return None


def _value_end(lines: list[str], row: int, col: int) -> tuple[int, int]:
    """The line and the column just after the TOML value that starts at lines[row][col]."""
    text = lines[row]
    if col >= len(text):
        return row, col
    first = text[col]
    if first in "\"'":
        i = col + 1
        while i < len(text):
            if first == '"' and text[i] == "\\":
                i += 2
                continue
            if text[i] == first:
                return row, i + 1
            i += 1
        return row, len(text)
    if first == "[":
        depth, quote, r, i = 0, None, row, col
        while r < len(lines):
            line = lines[r]
            while i < len(line):
                ch = line[i]
                if quote:
                    if ch == "\\" and quote == '"':
                        i += 1
                    elif ch == quote:
                        quote = None
                elif ch in "\"'":
                    quote = ch
                elif ch == "#":
                    break
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        return r, i + 1
                i += 1
            r, i = r + 1, 0
        return row, len(text)
    m = re.match(r"[^\s#]+", text[col:])
    return row, col + (m.end() if m else 0)


def _form(key: str, value) -> list[str]:
    """The lines of key = value. A long list goes on several lines, one item each."""
    line = f"{key} = {literal(value)}"
    if isinstance(value, (list, tuple)) and len(line) > LIST_WIDTH:
        return [f"{key} = ["] + [f"  {json.dumps(v, ensure_ascii=False)}," for v in value] + ["]"]
    return [line]


def _replace(lines: list[str], row: int, prefix: str, start: int, key: str, value) -> None:
    """Put value in place of the value that starts at column start of lines[row], keep the comment after it."""
    end_row, end_col = _value_end(lines, row, start)
    old = lines[row][start:] if end_row != row else lines[row][start:end_col]
    rest = lines[end_row][end_col:]
    form = _form(key, value)
    new = form[-1][len(key) + 3:] if len(form) == 1 else None
    if new is not None:
        gap = len(rest) - len(rest.lstrip())
        if gap and rest.lstrip().startswith("#") and end_row == row:
            rest = " " * max(1, gap - (len(new) - len(old))) + rest.lstrip()
        lines[row:end_row + 1] = [prefix + new + rest]
    else:
        lines[row:end_row + 1] = [prefix + form[0][len(key) + 3:]] + form[1:-1] + [form[-1] + rest]


def set_value(text: str, table: str, key: str, value) -> str:
    lines = text.splitlines()
    region = _region(lines, table)
    if region is None:
        lines += ["", f"[{table}]", *_form(key, value)]
        return "\n".join(lines) + "\n"
    lo, hi = region
    plain = re.compile(r"^(\s*" + re.escape(key) + r"\s*=\s*)")
    commented = re.compile(r"^\s*#\s*(" + re.escape(key) + r"\s*=\s*)")
    for i in range(lo, hi):
        m = plain.match(lines[i])
        if m:
            _replace(lines, i, m.group(1), m.end(), key, value)
            return "\n".join(lines) + "\n"
    for i in range(lo, hi):
        m = commented.match(lines[i])
        if m:
            lines[i] = lines[i][m.start(1):]
            _replace(lines, i, m.group(1), len(m.group(1)), key, value)
            return "\n".join(lines) + "\n"
    keys = [i for i in range(lo, hi) if lines[i].strip() and not lines[i].lstrip().startswith("#")]
    if keys or table:
        at = keys[-1] + 1 if keys else lo
        lines[at:at] = _form(key, value)
    else:
        # the top of a file without keys there: under its first comments, with a blank line on each side
        at = 0
        while at < hi and lines[at].lstrip().startswith("#"):
            at += 1
        block = _form(key, value)
        if at > 0:
            if at < len(lines) and not lines[at].strip():
                at += 1
            else:
                block = [""] + block
        if at < len(lines) and lines[at].strip():
            block = block + [""]
        lines[at:at] = block
    return "\n".join(lines) + "\n"
