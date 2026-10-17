"""The meter: the records of the sessions, read from a synthetic transcript, the status line and the comparison."""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "atlasmd" / "hook.py"
sys.path.insert(0, str(REPO))

from atlasmd import cli, meter  # noqa: E402

TOML = """
[start]
budget = 30000

[guard]
mode = "deny"

[[area]]
name = "the API"
paths = ["api/"]
pack = ["api/README.md"]
"""


def assistant(ident, usage, tools=(), stamp="2026-10-16T10:00:00.000Z"):
    content = [{"type": "tool_use", "name": name, "id": f"t-{ident}", "input": {}} for name in tools] or \
        [{"type": "text", "text": "The text that the meter never reads."}]
    return {"type": "assistant", "isSidechain": False, "timestamp": stamp, "requestId": f"r-{ident}",
            "message": {"id": ident, "model": "claude-test-1", "role": "assistant", "content": content,
                        "usage": {"input_tokens": usage[0], "cache_read_input_tokens": usage[1],
                                  "cache_creation_input_tokens": usage[2], "output_tokens": usage[3]}}}


BOUNDARY = {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": "auto", "preTokens": 9}}
USER = {"type": "user", "message": {"role": "user", "content": "please change api/main.py"}}


def lines(*items):
    return "".join((item if isinstance(item, str) else json.dumps(item)) + "\n" for item in items)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name).resolve()
        self.data = self.base / "data"
        self.root = self.base / "project"
        (self.root / "api").mkdir(parents=True)
        (self.root / ".git").mkdir()
        (self.root / "atlasmd.toml").write_text(TOML, encoding="utf-8")
        (self.root / "api/README.md").write_text("# The API\n", encoding="utf-8")
        (self.root / "api/main.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "docs/start").mkdir(parents=True)
        (self.root / "docs/start/10-map.md").write_text("# Map\n\nThe map.\n", encoding="utf-8")
        self.transcript = self.base / "session.jsonl"
        old = {k: os.environ.get(k) for k in ("ATLASMD_DATA", "ATLASMD", "CLAUDE_PROJECT_DIR")}
        os.environ["ATLASMD_DATA"] = str(self.data)
        os.environ.pop("ATLASMD", None)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])

    def event(self, session="s1", **extra):
        return {"session_id": session, "transcript_path": str(self.transcript), "cwd": str(self.root), **extra}

    def hook(self, payload, **env):
        payload = {**self.event(), **payload}
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ATLASMD"))}
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              env={**clean, "ATLASMD_DATA": str(self.data), **env}, timeout=30)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def amd(self, *args, stdin=""):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf), mock.patch("sys.stdin", io.StringIO(stdin)):
            code = cli.main(list(args), cwd=str(self.root))
        return code, buf.getvalue()


class Reading(Base):
    def test_the_meter_sums_the_requests_the_start_and_the_cycles(self):
        self.transcript.write_text(lines(
            USER,
            assistant("m1", (10, 100, 50, 5)),
            assistant("m1", (10, 100, 50, 5)),          # the second block of the same request counts once
            assistant("m2", (1, 200, 20, 7), tools=["Read"]),
            assistant("m3", (2, 300, 30, 9), tools=["Edit"]),
            assistant("m4", (3, 400, 40, 11)),
            "{not json",
            BOUNDARY,
            assistant("m5", (4, 50, 60, 13)),
            {"type": "assistant", "isSidechain": True, "message": {"id": "side", "usage": {"input_tokens": 99}}},
        ), encoding="utf-8")
        record = meter.update(self.event(), on=True, given=1234)
        s = meter.summary(record)
        self.assertEqual(s["requests"], 5)
        self.assertEqual(s["totals"], {"input_tokens": 20, "cache_read_input_tokens": 1050,
                                       "cache_creation_input_tokens": 200, "output_tokens": 45})
        self.assertEqual(s["tokens"], 1315)
        self.assertEqual((s["start_tokens"], s["start_requests"], s["edited"]), (165 + 228 + 341, 3, True))
        self.assertEqual(s["compactions"], 1)
        self.assertEqual([(c["requests"], c["tokens"]) for c in s["cycles"]], [(4, 165 + 228 + 341 + 454), (1, 127)])
        self.assertEqual(s["context"], 4 + 50 + 60)
        self.assertEqual(s["given"], 1234)
        self.assertEqual(s["model"], "claude-test-1")
        self.assertEqual(s["window"], 200_000)
        self.assertNotIn("never reads", json.dumps(record))

    def test_a_second_call_reads_only_the_new_bytes(self):
        first = lines(assistant("m1", (10, 100, 50, 5)))
        self.transcript.write_text(first, encoding="utf-8", newline="\n")
        record = meter.update(self.event(), on=True)
        self.assertEqual(record["offset"], len(first.encode()))
        # the old bytes change but keep their length: a reader from the start would count 999
        old = self.transcript.read_bytes().replace(b'"input_tokens": 10,', b'"input_tokens": 99,')
        self.transcript.write_bytes(old + lines(assistant("m2", (1, 1, 1, 1))).encode())
        record = meter.update(self.event(), on=True)
        self.assertEqual(record["totals"]["input_tokens"], 11)
        self.assertEqual(record["requests"], 2)
        # a line that Claude Code is still writing waits for its end
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(assistant("m3", (1, 1, 1, 1)))[:40])
        size = self.transcript.stat().st_size
        record = meter.update(self.event(), on=True)
        self.assertLess(record["offset"], size)
        self.assertEqual(record["requests"], 2)

    def test_a_broken_transcript_never_breaks_a_tool_call(self):
        self.transcript.mkdir()  # a folder where the file should be
        answer = self.hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                            "tool_input": {"file_path": str(self.root / "api/main.py")}})
        self.assertEqual(answer["hookSpecificOutput"]["permissionDecision"], "deny")
        self.transcript.rmdir()
        self.transcript.write_bytes(b"\xff\xfe garbage\n\x00\x00\n{\"type\": \"assistant\", \"message\": 7}\n")
        answer = self.hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                            "tool_input": {"file_path": str(self.root / "api/main.py")}})
        self.assertEqual(answer["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_no_record_without_atlasmd_toml_and_none_for_a_subagent(self):
        (self.root / "atlasmd.toml").unlink()
        self.transcript.write_text(lines(assistant("m1", (1, 1, 1, 1))), encoding="utf-8")
        self.assertIsNone(meter.update(self.event(), on=True))
        (self.root / "atlasmd.toml").write_text(TOML, encoding="utf-8")
        self.assertIsNone(meter.update(self.event(agent_id="a1"), on=True))
        self.assertIsNotNone(meter.update(self.event(), on=True))


class Off(Base):
    def test_atlasmd_off_turns_every_answer_off_and_still_writes_the_record(self):
        self.transcript.write_text(lines(assistant("m1", (1, 2, 3, 4))), encoding="utf-8")
        edit = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": str(self.root / "api/main.py")}}
        self.assertIsNotNone(self.hook({"hook_event_name": "SessionStart", "source": "startup"}))
        self.assertIsNotNone(self.hook(edit))
        session = {"session_id": "s2"}
        self.assertIsNone(self.hook({"hook_event_name": "SessionStart", "source": "startup", **session}, ATLASMD="off"))
        self.assertIsNone(self.hook({**edit, **session}, ATLASMD="off"))
        self.assertIsNone(self.hook({"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_response": {},
                                     "tool_input": {"file_path": str(self.root / "api/README.md")}, **session},
                                    ATLASMD="off"))
        self.assertIsNone(self.hook({"hook_event_name": "PostCompact", "trigger": "auto", **session}, ATLASMD="off"))
        self.assertIsNone(self.hook({"hook_event_name": "SubagentStart", "agent_id": "a1", **session}, ATLASMD="off"))
        self.assertFalse(list((self.data / "ledgers").glob("s2*")) if (self.data / "ledgers").is_dir() else [])
        self.assertFalse((self.data / "compacts.log").exists())
        record = meter.load("s2")
        self.assertFalse(record["on"])
        self.assertEqual(meter.tokens(record["totals"]), 10)
        self.assertTrue(meter.load("s1")["on"])
        self.assertGreater(meter.load("s1")["cycles"][-1]["given"], 0)
        self.assertEqual(record["cycles"][-1]["given"], 0)


class Lines(Base):
    def test_statusline_prints_the_line_of_the_session(self):
        self.transcript.write_text(lines(assistant("m1", (1, 16000, 100, 0)), assistant("m2", (0, 0, 0, 0), tools=["Write"]),
                                         BOUNDARY, assistant("m3", (0, 196379, 0, 0))), encoding="utf-8")
        meter.update(self.event(), on=True)
        stdin = json.dumps({"session_id": "s1", "transcript_path": str(self.transcript), "cwd": str(self.root),
                            "context_window": {"context_window_size": 1000000}})
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            code, text = self.amd("statusline", stdin=stdin)
        self.assertEqual(code, 0)
        self.assertEqual(text.strip(), "atlasmd on · start 16,101 · session 212,480 · 1 compaction")
        self.assertEqual(meter.load("s1")["window"], 1000000)
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertEqual(self.amd("statusline", stdin="not json")[1].strip(), "atlasmd")
            text = self.amd("statusline", stdin=json.dumps({"session_id": "s9", "cwd": str(self.base)}))[1]
        self.assertEqual(text.strip(), f"atlasmd · no atlasmd.toml in {self.base.name}")

    def test_compare_prints_off_on_and_the_difference(self):
        self.transcript.write_text(lines(assistant("m1", (0, 900, 100, 0), tools=["Edit"]),
                                         assistant("m2", (0, 1000, 0, 0))), encoding="utf-8")
        meter.update(self.event("off-session"), on=False)
        other = self.base / "other.jsonl"
        other.write_text(lines(assistant("n1", (0, 400, 100, 0), tools=["Edit"])), encoding="utf-8")
        meter.update({**self.event("on-session"), "transcript_path": str(other)}, on=True)
        code, text = self.amd("meter", "--compare", "on-s", "off-s")
        self.assertEqual(code, 0, text)
        rows = [line.split() for line in text.splitlines()]
        head = next(r for r in rows if r[:3] == ["off", "on", "difference"])
        self.assertEqual(head, ["off", "on", "difference"])
        self.assertIn(["start", "1,000", "500", "-500", "50%", "saved"], rows)
        self.assertIn(["total", "2,000", "500", "-1,500", "75%", "saved"], rows)
        self.assertIn(["requests", "2", "1", "-1", "50%", "saved"], rows)
        code, text = self.amd("meter", "--list")
        self.assertEqual(code, 0)
        self.assertIn("History  2 sessions", text)
        data = json.loads(self.amd("meter", "--json")[1])
        self.assertEqual(sorted(s["session_id"] for s in data["sessions"]), ["off-session", "on-session"])
        self.assertEqual(self.amd("meter", "--compare", "nothing", "off-s")[0], 2)


if __name__ == "__main__":
    unittest.main()
