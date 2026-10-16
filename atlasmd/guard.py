"""The decision on a tool call, and the files that a Bash command writes or reads.

The Bash parser catches the common forms only. A form that it does not know passes.
"""
from __future__ import annotations

import datetime
import glob
import os
import re
import shlex
from dataclasses import dataclass, field

from atlasmd import areas, config, ledger, naming, upkeep

EDIT_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}

EXTENSIONS = {
    "md", "markdown", "txt", "rst", "py", "pyi", "ipynb", "js", "mjs", "cjs", "ts", "tsx", "jsx", "json", "jsonl",
    "toml", "yaml", "yml", "ini", "cfg", "conf", "env", "sh", "bash", "zsh", "fish", "ps1", "html", "htm", "css",
    "scss", "svg", "xml", "csv", "tsv", "sql", "rs", "go", "java", "kt", "swift", "c", "h", "cc", "cpp", "hpp",
    "cs", "rb", "php", "lua", "r", "vue", "svelte", "lock", "gitignore", "dockerfile",
}

_PUNCTUATION = "();<>|&\n"
_HEREDOC = re.compile(r"(?<!<)<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_PREFIXES = {"sudo", "env", "command", "nohup", "time", "nice", "exec", "!", "{", "}", "then", "do", "else",
             "if", "elif", "while", "until"}
_PYTHON = re.compile(r"^python[0-9.]*$")
_PYTHON_WRITES = re.compile(r"write_text|write_bytes|\.write\(|open\([^)]*['\"][wax]|shutil\.(copy|move)|"
                            r"os\.(remove|rename|replace|unlink)|\.unlink\(|\.rename\(|\.touch\(|\.mkdir\(")
_QUOTED = re.compile(r"(['\"])([^'\"\n]+?)\1")


@dataclass
class _Command:
    words: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)      # targets of > and >>
    inputs: list[str] = field(default_factory=list)      # targets of <
    heredocs: list[str] = field(default_factory=list)
    cwd: str = ""


def _split_heredocs(command: str) -> tuple[str, list[str]]:
    """The command without the bodies of its heredocs, and the bodies in order."""
    lines = command.replace("\r\n", "\n").split("\n")
    kept, bodies, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for match in _HEREDOC.finditer(line):
            marker, dash = match.group(2), match.group(0).startswith("<<-")
            body = []
            while i < len(lines):
                current = lines[i]
                i += 1
                if (current.lstrip("\t") if dash else current).rstrip() == marker:
                    break
                body.append(current)
            bodies.append("\n".join(body))
    return "\n".join(kept), bodies


def _tokens(text: str) -> list[str]:
    text = text.replace("\\\n", " ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=_PUNCTUATION)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:  # an open quote: fall back to the words between spaces
        return text.split()


def _is_punctuation(token: str) -> bool:
    return bool(token) and all(c in _PUNCTUATION for c in token)


def _resolve(token: str, cwd: str) -> str | None:
    if not token or "$" in token or "`" in token or token.startswith("-"):
        return None
    path = os.path.expanduser(token)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normpath(path)


def _commands(command: str, cwd: str) -> list[_Command]:
    text, bodies = _split_heredocs(command)
    tokens = _tokens(text)
    body_queue = list(bodies)
    result, current = [], _Command(cwd=cwd)

    def finish():
        nonlocal current, cwd
        words = _strip_prefixes(current.words)
        if words and os.path.basename(words[0]) == "cd":
            target = words[1] if len(words) > 1 else "~"
            resolved = _resolve(target, cwd)
            if resolved:
                cwd = resolved
        if current.words or current.writes or current.inputs or current.heredocs:
            result.append(current)
        current = _Command(cwd=cwd)

    i = 0
    while i < len(tokens):
        token = tokens[i]
        following = tokens[i + 1] if i + 1 < len(tokens) else None
        if not _is_punctuation(token):
            if token.startswith("#"):  # a comment, up to the next separator
                while i < len(tokens) and not _is_punctuation(tokens[i]):
                    i += 1
                continue
            current.words.append(token)
            i += 1
            continue
        if ">" in token:
            if current.words and current.words[-1].isdigit():  # the 2 of 2>
                current.words.pop()
            if token.endswith("&") and following is not None and (following.isdigit() or following == "-"):
                i += 2
                continue
            if following is not None and not _is_punctuation(following):
                current.writes.append(following)
                i += 2
                continue
            i += 1
            continue
        if "<" in token:
            if token.startswith("<<") and token != "<<<":
                if body_queue:
                    current.heredocs.append(body_queue.pop(0))
                i += 2 if following is not None and not _is_punctuation(following) else 1
                continue
            if token == "<" and following is not None and not _is_punctuation(following):
                current.inputs.append(following)
                i += 2
                continue
            i += 1
            continue
        finish()
        i += 1
    finish()
    return result


def _strip_prefixes(words: list[str]) -> list[str]:
    i = 0
    while i < len(words):
        word = words[i]
        if word in _PREFIXES or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word):
            i += 1
        elif i > 0 and words[i - 1] in ("env", "sudo", "nice") and word.startswith("-"):
            i += 1
        else:
            break
    return words[i:]


def _operands(args: list[str]) -> list[str]:
    """The arguments that are not options. After -- every argument is an operand."""
    result, options = [], True
    for arg in args:
        if options and arg == "--":
            options = False
        elif options and arg.startswith("-") and arg != "-":
            continue
        else:
            result.append(arg)
    return result


def _sed_files(args: list[str]) -> list[str]:
    in_place, script, files, i = False, False, [], 0
    while i < len(args):
        arg = args[i]
        if arg in ("-e", "--expression", "-f", "--file"):
            script, i = True, i + 2
            continue
        if arg.startswith(("--expression=", "--file=")):
            script = True
        elif arg.startswith("--in-place"):
            in_place = True
        elif arg.startswith("--"):
            pass
        elif arg.startswith("-") and len(arg) > 1:
            flags = arg[1:]
            if flags[0] in "ef":
                script = True
                if len(flags) == 1:
                    i += 1
            elif "i" in flags:
                in_place = True
                following = args[i + 1] if i + 1 < len(args) else None
                if flags == "i" and following is not None and (following == "" or
                                                               (following.startswith(".") and "/" not in following)):
                    i += 1  # the suffix of the macOS form: sed -i '' or sed -i .bak
        elif not script:
            script = True
        else:
            files.append(arg)
        i += 1
    return files if in_place else []


def _perl_files(args: list[str]) -> list[str]:
    in_place, script, files, i = False, False, [], 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("-") and len(arg) > 1 and not arg.startswith("--"):
            for position, char in enumerate(arg[1:], start=1):
                if char in "eE":
                    script = True
                    if position == len(arg) - 1:
                        i += 1
                    break
                if char == "i":
                    in_place = True
                    break
                if char in "MmIFxCd":
                    break
        elif not script:
            script = True
        else:
            files.append(arg)
        i += 1
    return files if in_place else []


def _copy_targets(name: str, args: list[str], cwd: str) -> list[str]:
    targets = []
    for i, arg in enumerate(args):
        if arg in ("-t", "--target-directory") and i + 1 < len(args):
            targets.append(args[i + 1])
        elif arg.startswith("--target-directory="):
            targets.append(arg.split("=", 1)[1])
    operands = [a for a in _operands(args) if a not in targets]
    if not targets and len(operands) >= 2:
        targets, operands = [operands[-1]], operands[:-1]
    written = []
    for target in targets:
        folder = _resolve(target, cwd)
        if folder and os.path.isdir(folder) and operands:
            written += [os.path.join(target, os.path.basename(source.rstrip("/"))) for source in operands]
        else:
            written.append(target)
    if name == "mv":  # a move changes the folder of its sources too
        written += operands
    return written


def _looks_like_path(token: str) -> bool:
    if "://" in token or "{" in token or "$" in token or "\n" in token:
        return False
    base = token.rsplit("/", 1)[-1]
    return "/" in token or ("." in base and base.rsplit(".", 1)[-1].lower() in EXTENSIONS)


def _python_files(command: _Command) -> list[str]:
    code = list(command.heredocs)
    args = command.words[1:]
    for i, arg in enumerate(args):
        if arg == "-c" and i + 1 < len(args):
            code.append(args[i + 1])
    found = []
    for text in code:
        if _PYTHON_WRITES.search(text):
            found += [m.group(2) for m in _QUOTED.finditer(text) if _looks_like_path(m.group(2))]
    return found


def bash_writes(command: str, cwd: str) -> list[str]:
    """The absolute paths that a Bash command writes, for the common forms."""
    found: list[str] = []
    for cmd in _commands(command or "", cwd):
        tokens = list(cmd.writes)
        words = _strip_prefixes(cmd.words)
        if words:
            name, args = os.path.basename(words[0]), words[1:]
            if name == "sed":
                tokens += _sed_files(args)
            elif name == "perl":
                tokens += _perl_files(args)
            elif name == "tee":
                tokens += _operands(args)
            elif name in ("cp", "mv"):
                tokens += _copy_targets(name, args, cmd.cwd)
            elif name == "rm":
                tokens += _operands(args)
            elif _PYTHON.match(name):
                tokens += _python_files(_Command(words=words, heredocs=cmd.heredocs))
        for token in tokens:
            path = _resolve(token, cmd.cwd)
            if path and path not in found:
                found.append(path)
    return found


def bash_reads(command: str, cwd: str) -> list[str]:
    """The Markdown files that exist and that a Bash command names: cat, head, sed -n and grep count as a read."""
    found: list[str] = []
    for cmd in _commands(command or "", cwd):
        for token in cmd.words + cmd.inputs:
            if not token.lower().endswith(".md"):
                continue
            path = _resolve(token, cmd.cwd)
            if not path:
                continue
            matches = sorted(glob.glob(path))[:50] if glob.has_magic(path) else [path]
            for match in matches:
                if os.path.isfile(match) and match not in found:
                    found.append(match)
    return found


# --- the decision --------------------------------------------------------------------------------

def _refusal(cfg, area, path, missing) -> str:
    lines = [f"atlasmd: this change to {areas.rel(cfg, path)} is refused until you read the files that "
             f"atlasmd.toml lists for \"{area.name}\":"]
    for file, anchor in missing:
        name = areas.rel(cfg, file)
        lines.append(f"- {name}#{anchor}, the section {anchor}" if anchor else f"- {name}")
    lines.append("Read them, then make the change again. If a file changes what you planned to do, follow the file "
                 "and say so in your report.")
    return "\n".join(lines)


def _reminder(cfg, area, path, missing) -> str:
    lines = [f"atlasmd: you changed {areas.rel(cfg, path)} without the files that atlasmd.toml lists for "
             f"\"{area.name}\":"]
    for file, anchor in missing:
        name = areas.rel(cfg, file)
        lines.append(f"- {name}#{anchor}, the section {anchor}" if anchor else f"- {name}")
    lines.append("Read them now. If a file changes what you did, correct the change and say so in your report.")
    return "\n".join(lines)


def new_file(data: dict, path: str) -> tuple[str, str] | None:
    """The decision on a Write of a file that does not exist yet: a Markdown file whose name breaks the rule of
    its folder, or a source file in a folder that no [[area]] entry lists. None to pass."""
    found = config.find(path)
    if found is None:
        return None
    cfg = config.load(found)
    rel = areas.rel(cfg, path)
    if rel.startswith("../"):
        return None
    if rel.lower().endswith(".md"):
        if cfg.guard.mode == "off":
            return None
        try:
            siblings = os.listdir(os.path.dirname(path))
        except OSError:
            siblings = []
        text = naming.refusal(cfg.naming, rel, siblings, datetime.date.today())
        if text is None:
            return None
        if cfg.guard.mode == "deny":
            ledger.record_refusal(ledger.key(data), text)
            return "deny", text
        return "remind", text.replace("Name the file so, then write it again.", "Give the file a name under that rule.")
    if cfg.guard.new_folders != "remind" or not upkeep.is_source(path) or areas.area_of(cfg, path) is not None:
        return None
    folder = upkeep.new_folder(cfg, path)
    if folder is None:
        return None
    key = ledger.key(data)
    here = config.norm(os.path.dirname(path))
    if any(areas._under(here, done) for done in ledger.reminded(key)):
        return None
    ledger.add_reminded(key, cfg.root / folder)
    return "remind", (f"atlasmd: {folder}/ has no [[area]] entry in atlasmd.toml. Make its README.md and add the "
                      f"entry, or run /amd:area {folder}.")


def check(data: dict) -> tuple[str, str] | None:
    """The decision on a PreToolUse call: None to pass, or (mode, text) with mode deny or remind."""
    tool = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if tool in EDIT_TOOLS:
        target = tool_input.get(EDIT_TOOLS[tool])
        paths = [os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))] if isinstance(target, str) and target else []
    elif tool == "Bash":
        paths = bash_writes(tool_input.get("command") or "", cwd)
    else:
        return None

    first = new_file(data, paths[0]) if tool == "Write" and paths and not os.path.exists(paths[0]) else None
    if first is not None and first[0] == "deny":
        return first
    decision = _read_first(data, tool, paths)
    if first is None or (decision is not None and decision[0] == "deny"):
        return decision
    return first if decision is None else ("remind", first[1] + "\n\n" + decision[1])


def _read_first(data: dict, tool: str, paths: list[str]) -> tuple[str, str] | None:
    """The refusal or the reminder when the session did not read the files under pack of the [[area]] of a path."""
    key, read, loaded = ledger.key(data), None, {}
    for path in paths:
        if not path:
            continue
        found = config.find(path)
        if found is None:
            continue
        cfg = loaded.get(found) or loaded.setdefault(found, config.load(found))
        if cfg.guard.mode == "off" or (tool == "Bash" and not cfg.guard.bash):
            continue
        if areas.is_free(cfg, path):
            continue
        area = areas.area_of(cfg, path)
        if area is None:
            continue
        if read is None:
            read = ledger.read_paths(key)
        missing = [(file, anchor) for file, anchor in areas.pack_of(cfg, area)
                   if file.is_file() and config.norm(file) not in read]
        if not missing:
            continue
        if cfg.guard.mode == "deny":
            text = _refusal(cfg, area, path, missing)
            ledger.record_refusal(key, text)
            return "deny", text
        return "remind", _reminder(cfg, area, path, missing)
    return None
