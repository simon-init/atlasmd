#!/usr/bin/env python3
"""The entry of every hook of atlasmd. Claude Code runs it at SessionStart, SubagentStart, PreToolUse,
PostToolUse and PostCompact. It prints one JSON answer or nothing.

It never breaks a tool call: on an internal error it writes the error into <data>/log.txt,
prints nothing and exits 0. The manifest runs `python3 ... || python ...`, so a non-zero exit
would start the second command.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import traceback

LOG_LIMIT = 256 * 1024


def _data_dir() -> str:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    return data or os.path.join(os.path.expanduser("~"), ".claude", "plugins", "data", "amd")


def log(event: str, message: str) -> None:
    try:
        folder = _data_dir()
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "log.txt")
        if os.path.exists(path) and os.path.getsize(path) > LOG_LIMIT:
            os.replace(path, path + ".1")
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{stamp}\t{event}\t{message}\n")
    except Exception:
        pass


def _context(event: str, text: str) -> dict | None:
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def _git_root(folder: str) -> str | None:
    current = os.path.abspath(folder)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _offer(cwd: str) -> str:
    from atlasmd import config, ledger
    if not config.personal()["offer_setup"]:
        return ""
    root = _git_root(cwd) or (cwd if os.path.isdir(os.path.join(cwd, "docs")) else None)
    if root is None or ledger.seen_root(root):
        return ""
    ledger.mark_seen(root)
    return "atlasmd: this project has no atlasmd.toml. Run /amd:init once to set up the start reading and the areas."


def _broken(event: str, error: Exception) -> dict | None:
    log(event, f"ConfigError: {error}")
    return _context(event, f"atlasmd: {error} The start reading and the guard are off until the file is correct.")


def session_start(data: dict) -> dict | None:
    from atlasmd import config, ledger, start
    cwd = data.get("cwd") or os.getcwd()
    found = config.find(cwd)
    if found is None:
        return _context("SessionStart", _offer(cwd))
    try:
        cfg = config.load(found)
    except config.ConfigError as error:
        return _broken("SessionStart", error)
    source = data.get("source") or "startup"
    if source == "compact":
        ledger.clear_session(data.get("session_id"))
    composed = start.compose(cfg)
    if not composed.files:
        return None
    if source in ("resume", "fork"):
        count = len(composed.files)
        files = "start file" if count == 1 else "start files"
        return _context("SessionStart", f"atlasmd: {count} {files}, about {composed.tokens} tokens, "
                                        "read at the start of this session.")
    return _context("SessionStart", composed.text)


def subagent_start(data: dict) -> dict | None:
    from atlasmd import config, start
    found = config.find(data.get("cwd") or os.getcwd())
    if found is None:
        return None
    try:
        cfg = config.load(found)
    except config.ConfigError as error:
        log("SubagentStart", f"ConfigError: {error}")
        return None
    if cfg.agents.inject == "map":
        return _context("SubagentStart", start.compose_map(cfg))
    if cfg.agents.inject == "start":
        return _context("SubagentStart", start.compose(cfg).text)
    return None


def pre_tool_use(data: dict) -> dict | None:
    from atlasmd import guard
    decision = guard.check(data)
    if decision is None:
        return None
    mode, text = decision
    if mode == "deny":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                       "permissionDecisionReason": text}}
    # remind: additionalContext of a PreToolUse hook reaches the model next to the tool result.
    # No permissionDecision, so the normal permission flow of the call does not change.
    return _context("PreToolUse", text)


def post_tool_use(data: dict) -> None:
    from atlasmd import guard, ledger
    tool = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    key = ledger.key(data)
    if tool == "Read":
        path = tool_input.get("file_path")
        if isinstance(path, str) and path:
            ledger.add(key, os.path.join(cwd, os.path.expanduser(path)))
    elif tool == "Bash":
        for path in guard.bash_reads(tool_input.get("command") or "", cwd):
            ledger.add(key, path)
    return None


def post_compact(data: dict) -> None:
    from atlasmd import ledger
    ledger.clear_session(data.get("session_id"))
    ledger.log_compact(data.get("cwd") or os.getcwd(), data.get("trigger") or "", len(data.get("compact_summary") or ""))
    return None


HANDLERS = {
    "SessionStart": session_start,
    "SubagentStart": subagent_start,
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
    "PostCompact": post_compact,
}


def main() -> int:
    event = "unknown"
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            return 0
        event = str(data.get("hook_event_name") or "unknown")
        handler = HANDLERS.get(event)
        if handler is None:
            return 0
        from atlasmd import ledger
        try:
            ledger.prune()
        except Exception as error:
            log(event, f"prune: {error!r}")
        answer = handler(data)
        if answer:
            sys.stdout.write(json.dumps(answer) + "\n")
            sys.stdout.flush()
    except BaseException as error:  # a broken hook must never break the session
        where = traceback.extract_tb(error.__traceback__)[-1:] if error.__traceback__ else []
        place = f" at {os.path.basename(where[0].filename)}:{where[0].lineno}" if where else ""
        log(event, f"{type(error).__name__}: {error}{place}")
    return 0


if __name__ == "__main__":
    # The folder above atlasmd/, so that `atlasmd` is a package. It replaces the folder of this
    # script, so that a module of atlasmd never hides a module of the standard library.
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main()
    sys.exit(0)
