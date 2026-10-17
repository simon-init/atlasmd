"""Tests of the hook: each test builds a fixture project and drives hook.py as a subprocess."""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "atlasmd" / "hook.py"
sys.path.insert(0, str(REPO))

from atlasmd import guard, ledger  # noqa: E402

TOML = """
[start]
budget = {budget}
inject = {inject}

[guard]
mode = "{mode}"
bash = {bash}

[agents]
inject = "{agents}"

[[area]]
name = "the scrubber"
paths = ["services/scrubber/scrubber/"]
pack = ["services/scrubber/README.md", "docs/product-decisions.md#P15"]

[[area]]
name = "the review screen"
paths = ["apps/review/src/"]
pack = ["apps/review/README.md"]
"""


def write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build(root: pathlib.Path, budget=30000, inject="true", mode="deny", bash="true", agents="map"):
    write(root / "atlasmd.toml", TOML.format(budget=budget, inject=inject, mode=mode, bash=bash, agents=agents))
    write(root / "docs/start/20-open-items.md", "# Open items\n\nThe second file of the start reading.\n")
    write(root / "docs/start/10-map.md", "# Map\n\nThe first file of the start reading.\n")
    write(root / "docs/product-decisions.md", "# Decisions\n\n## P15\n\nThe default policy.\n")
    write(root / "services/scrubber/README.md", "# The scrubber\n")
    write(root / "services/scrubber/scrubber/main.py", "print('scrub')\n")
    write(root / "apps/review/README.md", "# The review screen\n")
    write(root / "apps/review/src/app.ts", "export {}\n")
    write(root / "tools/free.py", "print('free')\n")
    (root / ".git").mkdir(exist_ok=True)


class HookCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self._tmp.name).resolve()
        self.root = self.base / "project"
        self.data = self.base / "data"
        build(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ATLASMD"))}
        env["ATLASMD_DATA"] = str(self.data)
        env.update(extra)
        return env

    def hook(self, payload: dict, **extra):
        payload = dict(payload)
        payload.setdefault("session_id", "s1")
        payload.setdefault("transcript_path", str(self.base / "t.jsonl"))
        payload.setdefault("cwd", str(self.root))
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True,
                              text=True, env=self.env(**extra), timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    # the events

    def start(self, source="startup", **extra):
        return self.hook({"hook_event_name": "SessionStart", "source": source}, **extra)

    def subagent(self, agent="a1"):
        return self.hook({"hook_event_name": "SubagentStart", "agent_id": agent, "agent_type": "Explore"})

    def edit(self, rel, agent=None, tool="Edit"):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_use_id": "t1",
                   "tool_input": {key: str(self.root / rel), "old_string": "a", "new_string": "b"}}
        if agent:
            payload["agent_id"] = agent
        return self.hook(payload)

    def read(self, rel, agent=None, **tool_input):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Read",
                   "tool_input": {"file_path": str(self.root / rel), **tool_input}, "tool_response": {}}
        if agent:
            payload["agent_id"] = agent
        return self.hook(payload)

    def bash_pre(self, command):
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}})

    def bash_post(self, command):
        return self.hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": command},
                          "tool_response": {"stdout": "", "stderr": ""}})

    def compact(self, summary="the summary"):
        return self.hook({"hook_event_name": "PostCompact", "trigger": "auto", "compact_summary": summary})

    def read_pack(self, agent=None):
        self.read("services/scrubber/README.md", agent=agent)
        self.read("docs/product-decisions.md", agent=agent)

    def denied(self, answer):
        return bool(answer) and answer["hookSpecificOutput"].get("permissionDecision") == "deny"

    def context(self, answer):
        self.assertIsNotNone(answer)
        return answer["hookSpecificOutput"]["additionalContext"]


class StartReading(HookCase):
    def test_startup_injects_the_content_in_name_order(self):
        answer = self.start()
        self.assertEqual(answer["hookSpecificOutput"]["hookEventName"], "SessionStart")
        text = self.context(answer)
        self.assertTrue(text.startswith("atlasmd: project has 2 files to read at the start, about "))
        self.assertIn("every Edit and Write of that file is refused", text)
        first = text.index("## docs/start/10-map.md")
        second = text.index("## docs/start/20-open-items.md")
        self.assertLess(first, second)
        self.assertIn("The first file of the start reading.", text)
        self.assertIn("The second file of the start reading.", text)

    def test_clear_injects_the_start_reading(self):
        self.assertIn("## docs/start/10-map.md", self.context(self.start("clear")))

    def test_over_the_budget_injects_the_list(self):
        build(self.root, budget=10)
        text = self.context(self.start())
        self.assertIn("Read these files now, in this order:", text)
        self.assertIn("- docs/start/10-map.md, about ", text)
        self.assertIn("over the budget of 10 in atlasmd.toml", text)
        self.assertNotIn("The first file of the start reading.", text)

    def test_inject_false_injects_the_list_without_a_warning(self):
        build(self.root, inject="false")
        text = self.context(self.start())
        self.assertIn("Read these files now, in this order:", text)
        self.assertNotIn("over its budget", text)
        self.assertNotIn("The first file of the start reading.", text)

    def test_above_the_limit_of_claude_code_injects_the_list(self):
        write(self.root / "docs/start/15-long.md", "word " * 3000)
        text = self.context(self.start())
        self.assertIn("Read the rest now, in this order:", text)
        self.assertIn("The first file of the start reading.", text)
        self.assertIn("docs/start/15-long.md, about", text)
        self.assertIn("Claude Code takes at most 10000 characters from a hook", text)
        self.assertLess(len(text), 10000)

    def test_resume_injects_one_line(self):
        text = self.context(self.start("resume"))
        self.assertRegex(text, r"^atlasmd gave this session 2 Markdown files at its start, about \d+ tokens\. They are in the context\.$")
        self.assertRegex(self.context(self.start("fork")), r"^atlasmd gave this session 2 Markdown files")

    def test_compact_source_empties_the_ledger_and_injects(self):
        self.read_pack()
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))
        self.assertIn("## docs/start/10-map.md", self.context(self.start("compact")))
        self.assertTrue(self.denied(self.edit("services/scrubber/scrubber/main.py")))

    def test_subagent_gets_the_map(self):
        answer = self.subagent()
        self.assertEqual(answer["hookSpecificOutput"]["hookEventName"], "SubagentStart")
        text = self.context(answer)
        self.assertTrue(text.startswith("atlasmd: docs/start/10-map.md of project, about "))
        self.assertIn("The first file of the start reading.", text)
        self.assertNotIn("The second file of the start reading.", text)

    def test_subagent_gets_the_start_reading_or_nothing(self):
        build(self.root, agents="start")
        self.assertIn("The second file of the start reading.", self.context(self.subagent()))
        build(self.root, agents="none")
        self.assertIsNone(self.subagent())


class Guard(HookCase):
    def test_edit_in_an_area_is_refused_with_the_pack_named(self):
        answer = self.edit("services/scrubber/scrubber/main.py")
        self.assertTrue(self.denied(answer))
        reason = answer["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("atlasmd: this change to services/scrubber/scrubber/main.py is refused until you read the files that atlasmd.toml lists for \"the scrubber\":",
                      reason)
        self.assertIn("- services/scrubber/README.md\n", reason)
        self.assertIn("then make the change again", reason)

    def test_every_edit_tool_is_guarded(self):
        for tool in ("Write", "MultiEdit", "NotebookEdit"):
            self.assertTrue(self.denied(self.edit("services/scrubber/scrubber/main.py", tool=tool)), tool)

    def test_edit_passes_after_a_read_of_every_pack_file(self):
        self.read("services/scrubber/README.md")
        answer = self.edit("services/scrubber/scrubber/main.py")
        self.assertTrue(self.denied(answer))
        self.assertNotIn("- services/scrubber/README.md\n", answer["hookSpecificOutput"]["permissionDecisionReason"])
        self.read("docs/product-decisions.md")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))
        self.assertTrue(self.denied(self.edit("apps/review/src/app.ts")))

    def test_a_read_with_an_offset_counts(self):
        self.read("services/scrubber/README.md", offset=10, limit=5)
        self.read("docs/product-decisions.md", offset=3)
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))

    def test_a_bash_cat_of_a_pack_file_counts(self):
        self.bash_post("cat services/scrubber/README.md | head -5")
        self.bash_post(f"cd {pathlib.Path(self.root).as_posix()}/docs && sed -n '1,20p' product-decisions.md")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))

    def test_a_bash_sed_into_an_area_is_refused_and_echo_passes(self):
        self.assertTrue(self.denied(self.bash_pre("sed -i 's/a/b/' services/scrubber/scrubber/main.py")))
        self.assertIsNone(self.bash_pre("echo hello"))

    def test_bash_false_leaves_bash_alone(self):
        build(self.root, bash="false")
        self.assertIsNone(self.bash_pre("sed -i 's/a/b/' services/scrubber/scrubber/main.py"))
        self.assertTrue(self.denied(self.edit("services/scrubber/scrubber/main.py")))

    def test_a_path_in_no_area_passes(self):
        self.assertIsNone(self.edit("tools/free.py"))
        self.assertFalse(self.denied(self.edit("tools/new-file.py", tool="Write")))  # 0.2 reminds, see NewFiles
        self.assertIsNone(self.hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                                     "tool_input": {"file_path": str(self.base / "elsewhere.py")}}))

    def test_the_start_folder_the_packs_and_the_settings_pass(self):
        self.assertIsNone(self.edit("docs/start/30-state.md", tool="Write"))
        self.assertIsNone(self.edit("docs/start/10-map.md"))
        self.assertIsNone(self.edit("services/scrubber/README.md"))
        self.assertIsNone(self.edit("atlasmd.toml"))

    def test_a_subagent_has_its_own_ledger(self):
        self.read_pack()
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))
        self.assertTrue(self.denied(self.edit("services/scrubber/scrubber/main.py", agent="a1")))
        self.read_pack(agent="a1")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py", agent="a1"))

    def test_post_compact_empties_the_ledgers_and_writes_the_log(self):
        self.read_pack()
        self.read_pack(agent="a1")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))
        self.assertIsNone(self.compact("x" * 1234))
        self.assertTrue(self.denied(self.edit("services/scrubber/scrubber/main.py")))
        self.assertTrue(self.denied(self.edit("services/scrubber/scrubber/main.py", agent="a1")))
        lines = (self.data / "compacts.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        stamp, cwd, trigger, chars = lines[0].split("\t")
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual((cwd, trigger, chars), (str(self.root), "auto", "1234"))

    def test_another_session_keeps_its_ledger_after_a_compaction(self):
        self.hook({"hook_event_name": "PostToolUse", "tool_name": "Read", "session_id": "s2",
                   "tool_input": {"file_path": str(self.root / "apps/review/README.md")}})
        self.compact()
        self.assertIsNone(self.hook({"hook_event_name": "PreToolUse", "tool_name": "Edit", "session_id": "s2",
                                     "tool_input": {"file_path": str(self.root / "apps/review/src/app.ts")}}))

    def test_anchor_entries_count_on_any_read_and_are_named(self):
        self.read("services/scrubber/README.md")
        reason = self.edit("services/scrubber/scrubber/main.py")["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("- docs/product-decisions.md#P15, the section P15", reason)
        self.read("docs/product-decisions.md", offset=1, limit=2)
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))

    def test_the_refusal_is_recorded(self):
        self.edit("services/scrubber/scrubber/main.py", agent="a1")
        with _data(self.data):
            text = ledger.last_refusal(ledger.key({"session_id": "s1", "agent_id": "a1"}))
        self.assertTrue(text.startswith("atlasmd: this change to "))

    def test_remind_mode_adds_context_and_does_not_refuse(self):
        build(self.root, mode="remind")
        answer = self.edit("services/scrubber/scrubber/main.py")
        output = answer["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", output)
        self.assertIn("services/scrubber/README.md", output["additionalContext"])

    def test_off_mode_does_nothing(self):
        build(self.root, mode="off")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))

    def test_reads_at_the_same_time_are_all_kept(self):
        names = [f"docs/note-{n}.md" for n in range(8)]
        for name in names:
            write(self.root / name, "x")
        procs = []
        for name in names:
            payload = {"hook_event_name": "PostToolUse", "tool_name": "Read", "session_id": "s1", "cwd": str(self.root),
                       "tool_input": {"file_path": str(self.root / name)}}
            proc = subprocess.Popen([sys.executable, str(HOOK)], stdin=subprocess.PIPE, env=self.env(),
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append((proc, json.dumps(payload).encode()))
        for proc, payload in procs:
            proc.stdin.write(payload)
            proc.stdin.close()
        for proc, _ in procs:
            proc.wait(timeout=30)
        with _data(self.data):
            read = ledger.read_paths("s1")
        self.assertEqual(len(read), len(names))

    def test_a_missing_pack_file_is_not_asked_for(self):
        (self.root / "docs/product-decisions.md").unlink()
        self.read("services/scrubber/README.md")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))


class NewFiles(HookCase):
    """0.2: a Write of a file that does not exist yet."""

    def write_new(self, rel, session="s1"):
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": "Write", "session_id": session,
                          "tool_input": {"file_path": str(self.root / rel), "content": "x"}})

    def settings(self, old, new):
        path = self.root / "atlasmd.toml"
        write(path, path.read_text(encoding="utf-8").replace(old, new))

    def reason(self, answer):
        self.assertTrue(self.denied(answer), answer)
        return answer["hookSpecificOutput"]["permissionDecisionReason"]

    def test_a_bad_name_is_refused_with_the_rule_in_words(self):
        today = datetime.date.today().isoformat()
        write(self.root / "docs/decisions/P007-old.md", "# P7\n")
        cases = {
            "docs/notes/Gate Run.md": f"atlasmd: docs/notes/ names its files with the date as YYYY-MM-DD, a hyphen and "
                                      f"the subject in lower case with hyphens, for example {today}-gate-run.md. "
                                      "Gate Run.md breaks that rule. Name the file so, then write it again.",
            "docs/start/open.md": "atlasmd: docs/start/ names its files with two digits, a hyphen and the subject in "
                                  "lower case with hyphens, for example 30-open.md. open.md breaks that rule. "
                                  "Name the file so, then write it again.",
            "docs/decisions/policy.md": "atlasmd: docs/decisions/ names its files with P, three digits, a hyphen and "
                                        "the subject in lower case with hyphens, for example P008-policy.md. "
                                        "policy.md breaks that rule. Name the file so, then write it again.",
            "docs/plans/Big Plan.md": "atlasmd: docs/plans/ names its files with the subject in lower case with "
                                      "hyphens, for example big-plan.md. Big Plan.md breaks that rule. "
                                      "Name the file so, then write it again.",
        }
        for rel, text in cases.items():
            self.assertEqual(self.reason(self.write_new(rel)), text, rel)
        with _data(self.data):
            self.assertEqual(ledger.last_refusal("s1"), cases["docs/plans/Big Plan.md"])

    def test_a_rule_outside_the_convention_is_given_as_its_regular_expression(self):
        self.settings("[agents]", '[naming]\n"docs/runs" = "^run-[0-9]+\\\\.md$"\n\n[agents]')
        write(self.root / "docs/runs/run-1.md", "x")
        self.assertEqual(self.reason(self.write_new("docs/runs/second.md")),
                         "atlasmd: docs/runs/ names its files to match the regular expression ^run-[0-9]+\\.md$, "
                         "for example run-1.md. second.md breaks that rule. Name the file so, then write it again.")

    def test_a_good_name_and_a_readme_pass(self):
        for rel in ("docs/notes/2026-10-16-gate-run.md", "docs/start/50-rules.md", "docs/decisions/P008-policy.md",
                    "docs/plans/login.md", "docs/plans/README.md", "docs/elsewhere/Any Name.md"):
            self.assertIsNone(self.write_new(rel), rel)

    def test_an_edit_of_an_existing_file_with_a_bad_name_passes(self):
        write(self.root / "docs/notes/Old Name.md", "# Old\n")
        self.assertIsNone(self.edit("docs/notes/Old Name.md"))
        self.assertIsNone(self.edit("docs/notes/Old Name.md", tool="Write"))

    def test_remind_and_off_follow_guard_mode(self):
        build(self.root, mode="remind")
        answer = self.write_new("docs/plans/Big Plan.md")
        self.assertFalse(self.denied(answer))
        self.assertTrue(self.context(answer).endswith("Big Plan.md breaks that rule. Give the file a name under that rule."))
        build(self.root, mode="off")
        self.assertIsNone(self.write_new("docs/plans/Big Plan.md"))

    def test_a_new_source_file_in_a_folder_without_an_entry_is_named_once(self):
        tools = ("atlasmd: tools/ has no [[area]] entry in atlasmd.toml. Make its README.md and add the entry, "
                 "or run /atlasmd:area tools.")
        answer = self.write_new("tools/new-file.py")
        self.assertFalse(self.denied(answer))
        self.assertEqual(self.context(answer), tools)
        self.assertIsNone(self.write_new("tools/other.py"))
        self.assertIsNone(self.write_new("tools/deeper/third.py"))
        self.assertEqual(self.context(self.write_new("tools/new-file.py", session="s2")), tools)
        self.assertIn("atlasmd: pkg/ has no [[area]] entry", self.context(self.write_new("pkg/sub/mod.py")))
        self.assertIsNone(self.write_new("pkg/sub/two.py"))
        self.compact()
        self.assertEqual(self.context(self.write_new("tools/after.py")), tools)

    def test_no_reminder_where_it_does_not_apply(self):
        for rel in ("tests/test_new.py", "docs/tool.py", ".github/x.py", "tools/data.json", "top.py",
                    "apps/review/src/new.ts"):
            answer = self.write_new(rel)
            if rel.startswith("apps/review/"):
                self.assertTrue(self.denied(answer), rel)  # an [[area]] holds it: the files under pack come first
            else:
                self.assertIsNone(answer, rel)
        self.assertIsNone(self.edit("tools/free.py"))

    def test_new_folders_off(self):
        self.settings("bash = true", 'bash = true\nnew_folders = "off"')
        self.assertIsNone(self.write_new("tools/new-file.py"))


class NoConfig(HookCase):
    def setUp(self):
        super().setUp()
        self.bare = self.base / "bare"
        (self.bare / ".git").mkdir(parents=True)

    def test_the_offer_comes_once(self):
        text = self.context(self.hook({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(self.bare)}))
        self.assertEqual(text, "atlasmd: this project has no atlasmd.toml. "
                               "Run /atlasmd:init once. It writes atlasmd.toml and docs/start/, and lists which Markdown files Claude reads at the start and before a change in each folder.")
        self.assertIsNone(self.hook({"hook_event_name": "SessionStart", "source": "startup",
                                     "cwd": str(self.bare / "sub")}))

    def test_no_offer_when_the_person_turned_it_off(self):
        self.assertIsNone(self.hook({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(self.bare)},
                                    CLAUDE_PLUGIN_OPTION_OFFER_SETUP="false"))

    def test_no_offer_without_git_and_docs(self):
        plain = self.base / "plain"
        plain.mkdir()
        if any((parent / ".git").exists() for parent in plain.parents):
            self.skipTest("the temporary folder is inside a git repository")
        self.assertIsNone(self.hook({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(plain)}))

    def test_edit_without_config_passes(self):
        self.assertIsNone(self.hook({"hook_event_name": "PreToolUse", "tool_name": "Edit",
                                     "cwd": str(self.bare), "tool_input": {"file_path": str(self.bare / "a.py")}}))

    def test_a_broken_settings_file_never_breaks_a_tool_call(self):
        write(self.root / "atlasmd.toml", "[guard\nmode = 'deny'\n")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))
        self.assertIsNone(self.bash_pre("sed -i 's/a/b/' services/scrubber/scrubber/main.py"))
        self.assertIsNone(self.read("services/scrubber/README.md"))
        self.assertIsNone(self.subagent())
        log = (self.data / "log.txt").read_text(encoding="utf-8")
        self.assertIn("ConfigError", log)
        self.assertIn("is not valid TOML", log)
        text = self.context(self.start())
        self.assertIn("Until atlasmd.toml is correct, nothing is read at the start and no edit is refused.", text)

    def test_a_wrong_value_never_breaks_a_tool_call(self):
        write(self.root / "atlasmd.toml", "[guard]\nmode = 'strict'\n")
        self.assertIsNone(self.edit("services/scrubber/scrubber/main.py"))
        self.assertIn("[guard] mode must be deny, remind or off", (self.data / "log.txt").read_text(encoding="utf-8"))

    def test_bad_input_is_ignored(self):
        for text in ("", "not json", "[1, 2]", json.dumps({"hook_event_name": "Elsewhere"})):
            proc = subprocess.run([sys.executable, str(HOOK)], input=text, capture_output=True, text=True,
                                  env=self.env(), timeout=30)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))


class _data:
    """Point the in-process modules at a data folder for the time of a with block."""

    def __init__(self, folder):
        self.folder = str(folder)

    def __enter__(self):
        self.old = os.environ.get("ATLASMD_DATA")
        os.environ["ATLASMD_DATA"] = self.folder

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("ATLASMD_DATA", None)
        else:
            os.environ["ATLASMD_DATA"] = self.old


class BashForms(unittest.TestCase):
    cwd = "/work"

    def writes(self, command):
        return guard.bash_writes(command, self.cwd)

    def test_the_forms_that_write(self):
        cases = {
            "sed -i 's/a/b/' x.py": ["/work/x.py"],
            "sed -i.bak -e 's/a/b/' -e 's/c/d/' a/x.py b/y.py": ["/work/a/x.py", "/work/b/y.py"],
            "sed -i '' 's/a/b/' x.py": ["/work/x.py"],
            "sed -n '1,5p' x.py": [],
            "perl -pi -e 's/a/b/' x.py": ["/work/x.py"],
            "perl -e 'print 1' x.py": [],
            "echo hi > out.txt": ["/work/out.txt"],
            "echo hi >> /tmp/log.txt 2>&1": ["/tmp/log.txt"],
            "make 2> err.log": ["/work/err.log"],
            "printf x | tee -a a.md b/c.md": ["/work/a.md", "/work/b/c.md"],
            "cp a.py b/c.py": ["/work/b/c.py"],
            "cp -r src/ dest/": ["/work/dest"],
            "mv old.py new.py": ["/work/new.py", "/work/old.py"],
            "rm -rf build/ x.py": ["/work/build", "/work/x.py"],
            "cat > notes/a.md <<'EOF'\nline > other.txt\nEOF": ["/work/notes/a.md"],
            "python3 - <<'PY'\nimport pathlib\npathlib.Path('pkg/mod.py').write_text('x')\nPY": ["/work/pkg/mod.py"],
            "python3 - <<'PY'\nprint(open('pkg/mod.py').read())\nPY": [],
            "python3 -c \"open('a/b.txt', 'w').write('x')\"": ["/work/a/b.txt"],
            "cd /srv && sed -i 's/a/b/' x.py": ["/srv/x.py"],
            "FOO=1 sudo tee /etc/x.conf < in.txt": ["/etc/x.conf"],
            "echo hello": [],
            "ls -la; git status && echo done": [],
            "echo $HOME > $OUT": [],
        }
        for command, expected in cases.items():
            self.assertEqual(self.writes(command), [os.path.normpath(p) for p in expected], command)
        self.assertEqual(self.writes("echo 'an open quote"), [])

    def test_the_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            write(pathlib.Path(folder) / "docs/a.md", "a")
            write(pathlib.Path(folder) / "docs/b.md", "b")
            reads = guard.bash_reads("cat docs/a.md && grep -n x docs/*.md missing.md", folder)
            self.assertEqual(reads, [os.path.normpath(os.path.join(folder, "docs/a.md")),
                                     os.path.normpath(os.path.join(folder, "docs/b.md"))])


class Ledger(unittest.TestCase):
    def test_ten_refusals_are_kept(self):
        with tempfile.TemporaryDirectory() as folder, _data(folder):
            for number in range(12):
                ledger.record_refusal("s9", f"refusal {number}")
            self.assertEqual(ledger.last_refusal("s9"), "refusal 11")
            data = json.loads(next(pathlib.Path(folder, "ledgers").glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(len(data["refusals"]), 10)
            self.assertEqual((data["session_id"], data["agent_id"]), ("s9", None))

    def test_old_ledgers_are_removed(self):
        with tempfile.TemporaryDirectory() as folder, _data(folder):
            ledger.add("s9", "/a.md")
            path = next(pathlib.Path(folder, "ledgers").glob("*.json"))
            old = path.stat().st_mtime - 15 * 24 * 3600
            os.utime(path, (old, old))
            ledger.prune()
            self.assertFalse(path.exists())

    def test_seen_roots(self):
        with tempfile.TemporaryDirectory() as folder, _data(folder):
            self.assertFalse(ledger.seen_root(folder))
            ledger.mark_seen(folder)
            self.assertTrue(ledger.seen_root(folder))


if __name__ == "__main__":
    unittest.main()
