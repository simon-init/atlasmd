"""The checks of 0.2 under [check], amd area, and the eight rules that amd init writes, on a git repository
in a temporary folder. The commits have fixed dates, so the ages and the counts do not change with the day."""
import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atlasmd import cli, config, upkeep  # noqa: E402

TODAY = datetime.date(2026, 10, 16)

TOML = """# The settings of this fixture.

[start]
budget = 30000

[[area]]
name = "the app"
paths = ["app/"]
pack = ["app/README.md"]
"""


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def git(root, *args, when="2026-01-01T12:00:00"):
    hooks = Path(root).parent / "no-hooks"
    hooks.mkdir(exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}",
                           "-c", "init.defaultBranch=master", *args],
                          cwd=root, capture_output=True, text=True, env=env, check=True)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = os.environ.get("ATLASMD_DATA")
        os.environ["ATLASMD_DATA"] = str(Path(self.tmp.name) / "data")
        self.addCleanup(lambda: os.environ.__setitem__("ATLASMD_DATA", old) if old is not None
                        else os.environ.pop("ATLASMD_DATA", None))
        self.root = Path(self.tmp.name).resolve() / "project"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "core.autocrlf", "false")
        write(self.root, "atlasmd.toml", TOML)
        write(self.root, "app/README.md", "# The app\n")
        write(self.root, "app/main.py", "x = 1\n")
        write(self.root, "docs/start/20-open-items.md", "# Open items\n\n- The login. `docs/plans/login.md`\n")
        write(self.root, "docs/start/30-state.md", "# Where things stand\n")
        write(self.root, "docs/plans/login.md", "# The login\n")
        self.commit("the start", "2026-01-01T12:00:00")

    def commit(self, message, when):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "--allow-empty", "-m", message, when=when)

    def settings(self, extra=""):
        write(self.root, "atlasmd.toml", TOML + extra)

    def run_checks(self):
        cfg = config.load(self.root / "atlasmd.toml")
        from atlasmd import scan
        return upkeep.run(cfg, scan.all_files(self.root), today=TODAY)

    def found(self, kind):
        return [(path, text) for k, path, text in self.run_checks()[0] if k == kind]

    def paths(self, kind):
        return [path for path, _text in self.found(kind)]

    def amd(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(list(args), cwd=str(self.root))
        return code, buf.getvalue()


class Growth(Case):
    def test_no_readme(self):
        self.assertEqual(self.found("no-readme"), [])
        write(self.root, "tools/run.py", "x\n")
        write(self.root, "tools/sub/more.py", "x\n")
        write(self.root, "lib/a/b.ts", "x\n")
        for skipped in ("tests/t.py", "test/t.py", "docs/x.py", ".hidden/x.py", "node_modules/x.js", ".venv/x.py",
                        "app/tests/t.py", "data/notes.txt"):
            write(self.root, skipped, "x\n")
        self.assertEqual(self.found("no-readme"), [
            ("lib/a/", "lib/a/ has source files and no README.md. Write one, or run /amd:area lib/a."),
            ("tools/", "tools/ has source files and no README.md. Write one, or run /amd:area tools.")])
        write(self.root, "tools/README.md", "# Tools\n")
        write(self.root, "lib/README.md", "# Lib\n")
        self.assertEqual(self.found("no-readme"), [])

    def test_no_entry(self):
        self.assertEqual(self.found("no-entry"), [])
        write(self.root, "tools/README.md", "# Tools\n")
        write(self.root, "tools/run.py", "x\n")
        write(self.root, "tools/sub/more.py", "x\n")
        write(self.root, "app/deep/new.py", "x\n")
        write(self.root, "tests/t.py", "x\n")
        self.assertEqual(self.found("no-entry"), [
            ("tools/", "tools/ has source files and no [[area]] entry in atlasmd.toml lists it. "
                       "Run /amd:area tools.")])
        self.settings('\n[[area]]\nname = "tools"\npaths = ["tools/"]\npack = ["tools/README.md"]\n')
        self.assertEqual(self.found("no-entry"), [])

    def test_dead_entry(self):
        self.assertEqual(self.found("dead-entry"), [])
        self.settings('\n[[area]]\nname = "gone"\npaths = ["gone/", "app/main.py", "old.py"]\npack = []\n')
        self.assertEqual(self.found("dead-entry"), [
            ("gone/", 'the [[area]] "gone" lists gone/, which does not exist. Remove it or fix the path.'),
            ("old.py", 'the [[area]] "gone" lists old.py, which does not exist. Remove it or fix the path.')])

    def test_stale_readme(self):
        self.settings("\n[check]\nstale_readme = 3\n")
        for n, day in enumerate(("02", "03"), 1):
            write(self.root, "app/main.py", f"x = {n + 1}\n")
            self.commit(f"change {n}", f"2026-01-{day}T12:00:00")
        write(self.root, "elsewhere.py", "x\n")
        self.commit("not in app", "2026-01-04T12:00:00")
        self.assertEqual(self.found("stale-readme"), [])
        write(self.root, "app/main.py", "x = 4\n")
        self.commit("change 3", "2026-01-05T12:00:00")
        self.assertEqual(self.found("stale-readme"), [
            ("app/README.md", "app/README.md did not change in the last 3 commits that changed app/. "
                              "Update its State section.")])
        write(self.root, "app/README.md", "# The app\n\n## State\n\nUpdated.\n")
        self.commit("the state", "2026-01-06T12:00:00")
        self.assertEqual(self.found("stale-readme"), [])

    def test_stale_readme_counts_the_paths_inside_its_folder(self):
        write(self.root, "svc/README.md", "# The service\n")
        write(self.root, "svc/core/a.py", "x\n")
        self.settings('\n[[area]]\nname = "the service"\npaths = ["svc/core/"]\npack = ["svc/README.md"]\n'
                      '\n[check]\nstale_readme = 2\n')
        self.commit("the service", "2026-01-02T12:00:00")
        write(self.root, "svc/other.txt", "not in the paths\n")
        self.commit("other", "2026-01-03T12:00:00")
        write(self.root, "svc/core/a.py", "y\n")
        self.commit("core 1", "2026-01-04T12:00:00")
        self.assertEqual(self.found("stale-readme"), [])
        write(self.root, "svc/core/a.py", "z\n")
        self.commit("core 2", "2026-01-05T12:00:00")
        self.assertEqual(self.paths("stale-readme"), ["svc/README.md"])
        self.assertIn("the last 2 commits that changed svc/core/.", self.found("stale-readme")[0][1])


class Cleaning(Case):
    def test_dead_pointer(self):
        self.assertEqual(self.found("dead-pointer"), [])
        write(self.root, "docs/start/20-open-items.md",
              "# Open items\n\n- `docs/plans/login.md` `app/` `app/README.md#state` `docs/plans/gone.md`\n"
              "- `notes.md` `amd check --json` `git log -- app/` `https://example.com/a/b` `<folder>/` `P12`\n")
        self.assertEqual(self.found("dead-pointer"), [
            ("docs/plans/gone.md", "docs/start/20-open-items.md names docs/plans/gone.md, which does not exist. "
                                   "Fix the line or remove it."),
            ("notes.md", "docs/start/20-open-items.md names notes.md, which does not exist. Fix the line or remove it.")])

    def test_dead_pointer_reads_start_items(self):
        text = (self.root / "atlasmd.toml").read_text(encoding="utf-8").replace(
            "budget = 30000", 'budget = 30000\nitems = "TODO.md"')
        write(self.root, "atlasmd.toml", text)
        write(self.root, "TODO.md", "- `docs/plans/gone.md`\n")
        self.assertEqual(self.paths("dead-pointer"), ["docs/plans/gone.md"])
        self.assertIn("TODO.md names docs/plans/gone.md", self.found("dead-pointer")[0][1])

    def test_orphan_plan(self):
        self.assertEqual(self.found("orphan-plan"), [])
        write(self.root, "docs/plans/billing.md", "# Billing\n")
        write(self.root, "docs/plans/login-two.md", "# The login, round two\n")
        write(self.root, "docs/plans/README.md", "# Plans\n")
        self.assertEqual(self.found("orphan-plan"), [
            ("docs/plans/billing.md", "docs/plans/billing.md is named by no line of docs/start/20-open-items.md. "
                                      "Add a line, or move the plan to docs/archive/ if it is built."),
            ("docs/plans/login-two.md", "docs/plans/login-two.md is named by no line of docs/start/20-open-items.md. "
                                        "Add a line, or move the plan to docs/archive/ if it is built.")])
        write(self.root, "docs/start/20-open-items.md", "- `docs/plans/login.md`\n- billing: plans/billing.md\n"
                                                        "- round two: `login-two.md`\n")
        self.assertEqual(self.found("orphan-plan"), [])

    def test_orphan_note(self):
        write(self.root, "docs/notes/2026-01-01-old.md", "# Old\n")
        write(self.root, "docs/notes/2026-01-02-named.md", "# Named\n")
        write(self.root, "docs/notes/2026-10-10-new.md", "# New\n")
        write(self.root, "docs/notes/undated.md", "# Undated\n")
        write(self.root, "docs/plans/login.md", "# The login\n\nSee `docs/notes/2026-01-02-named.md`.\n")
        write(self.root, "docs/archive/old-plan.md", "Named only here: docs/notes/2026-01-01-old.md\n")
        write(self.root, "docs/start/10-map.md", "# Map\n\n<!-- atlasmd:tree -->\n- `docs/notes/2026-01-01-old.md`\n"
                                                 "- `docs/notes/undated.md`\n<!-- /atlasmd:tree -->\n")
        self.commit("the notes", "2026-03-01T12:00:00")
        self.assertEqual(self.found("orphan-note"), [
            ("docs/notes/2026-01-01-old.md", "docs/notes/2026-01-01-old.md is named by no Markdown file and is "
                                             "288 days old. Point at it, or move it to docs/archive/."),
            ("docs/notes/undated.md", "docs/notes/undated.md is named by no Markdown file and is 229 days old. "
                                      "Point at it, or move it to docs/archive/.")])
        write(self.root, "docs/start/30-state.md", "- `docs/notes/2026-01-01-old.md`\n- notes/undated.md\n")
        self.assertEqual(self.found("orphan-note"), [])

    def test_no_index_line(self):
        write(self.root, "docs/decisions/P001-first.md", "# P1\n")
        write(self.root, "docs/decisions/P002-second.md", "# P2\n")
        write(self.root, "docs/decisions/P010-tenth.md", "# P10\n")
        write(self.root, "docs/decisions/README.md", "# Decisions\n\n- P1 The first\n- `P010-tenth.md`\n- P12 later\n")
        self.assertEqual(self.found("no-index-line"), [
            ("docs/decisions/P002-second.md", "docs/decisions/P002-second.md has no line in docs/decisions/README.md. "
                                              "Add the line.")])
        write(self.root, "docs/decisions/README.md", "# Decisions\n\n- P1 The first\n- P2 The second\n- P10\n")
        self.assertEqual(self.found("no-index-line"), [])

    def test_stale_state(self):
        self.settings("\n[check]\nstale_state = 2\n")
        self.commit("one", "2026-01-02T12:00:00")
        self.assertEqual(self.found("stale-state"), [])
        self.commit("two", "2026-01-03T12:00:00")
        self.assertEqual(self.found("stale-state"), [
            ("docs/start/30-state.md", "docs/start/30-state.md did not change in the last 2 commits. "
                                       "Rewrite it with /amd:end.")])
        write(self.root, "docs/start/30-state.md", "# Where things stand\n\nNew.\n")
        self.commit("the state", "2026-01-04T12:00:00")
        self.assertEqual(self.found("stale-state"), [])


class Keys(Case):
    def mess(self):
        write(self.root, "tools/run.py", "x\n")
        write(self.root, "docs/plans/billing.md", "# Billing\n")
        write(self.root, "docs/notes/2026-01-01-old.md", "# Old\n")
        write(self.root, "docs/decisions/P001-first.md", "# P1\n")
        write(self.root, "docs/start/20-open-items.md", "- `docs/plans/login.md` `docs/plans/gone.md`\n")
        self.settings('\n[[area]]\nname = "gone"\npaths = ["gone/"]\npack = []\n'
                      '\n[check]\nstale_readme = 1\nstale_state = 1\n')
        write(self.root, "app/main.py", "x = 2\n")
        self.commit("a change", "2026-01-02T12:00:00")

    def test_every_finding_comes_on_and_goes_off_with_its_key(self):
        self.mess()
        kinds = {k for k, _p, _t in self.run_checks()[0]}
        self.assertEqual(kinds, {"no-readme", "no-entry", "dead-entry", "stale-readme", "dead-pointer", "orphan-plan",
                                 "orphan-note", "no-index-line", "stale-state"})
        text = (self.root / "atlasmd.toml").read_text(encoding="utf-8")
        write(self.root, "atlasmd.toml", text.replace("stale_readme = 1\nstale_state = 1\n",
                                                      "folders = false\nstale_readme = 0\ndead_pointers = false\n"
                                                      "plans = false\nnotes = 0\ndecisions = false\nstale_state = 0\n"))
        self.assertEqual(self.run_checks(), ([], []))
        code, out = self.amd("check")
        self.assertIn("✓ growth      [check] in atlasmd.toml turns these checks off, or their folders do not exist", out)

    def test_one_key_turns_off_its_finding_only(self):
        self.mess()
        for key, value, kinds in (("folders", "false", {"no-readme", "no-entry", "dead-entry"}),
                                  ("dead_pointers", "false", {"dead-pointer"}), ("plans", "false", {"orphan-plan"}),
                                  ("notes", "0", {"orphan-note"}), ("decisions", "false", {"no-index-line"})):
            text = (self.root / "atlasmd.toml").read_text(encoding="utf-8")
            write(self.root, "atlasmd.toml", text.replace("[check]\n", f"[check]\n{key} = {value}\n"))
            found = {k for k, _p, _t in self.run_checks()[0]}
            self.assertFalse(found & kinds, key)
            self.assertTrue(found, key)
            write(self.root, "atlasmd.toml", text)

    def test_a_folder_that_does_not_exist_keeps_its_check_silent(self):
        (self.root / "docs/plans/login.md").unlink()
        (self.root / "docs/plans").rmdir()
        checks = [kind for _s, kind, _g in self.run_checks()[1]]
        self.assertNotIn("orphan-plan", checks)
        self.assertNotIn("orphan-note", checks)
        self.assertIn("dead-pointer", checks)

    def test_check_json_and_the_two_sections(self):
        self.mess()
        code, out = self.amd("check", "--json")
        self.assertEqual(code, 1)
        found = {(f["kind"], f["path"]) for f in json.loads(out)["findings"]}
        self.assertIn(("no-readme", "tools/"), found)
        self.assertIn(("orphan-plan", "docs/plans/billing.md"), found)
        self.assertIn(("stale-state", "docs/start/30-state.md"), found)
        code, out = self.amd("check")
        lines = out.splitlines()
        self.assertIn("✗ growth      tools/ has source files and no README.md. Write one, or run /amd:area tools.", lines)
        self.assertTrue(any(line.startswith("✗ cleaning    docs/plans/billing.md is named by no line") for line in lines))
        self.assertNotIn("✓ growth      every path of every [[area]] entry exists", lines)

    def test_the_good_lines(self):
        code, out = self.amd("check")
        lines = out.splitlines()
        for good in ("✓ growth      every folder with source files has a README.md, in it or in a folder above it",
                     "✓ growth      every folder with source files is in the paths of an [[area]] entry",
                     "✓ growth      every path of every [[area]] entry exists",
                     "✓ growth      every README.md under pack changed within the last 15 commits of its folder",
                     "✓ cleaning    every path in backticks in docs/start/20-open-items.md exists",
                     "✓ cleaning    docs/start/20-open-items.md names every plan in docs/plans/",
                     "✓ cleaning    docs/start/30-state.md changed within the last 20 commits"):
            self.assertIn(good, lines)

    def test_bad_values_give_a_plain_sentence(self):
        for text, words in (("[check]\nnotes = -1\n", "[check] notes must be a whole number, 0 or above"),
                            ("[check]\nplans = 1\n", "[check] plans must be true or false"),
                            ("[check]\ncolour = true\n", "the key \"colour\" in [check] is not known"),
                            ("[guard]\nnew_folders = \"deny\"\n", "[guard] new_folders must be remind or off")):
            write(self.root, "atlasmd.toml", text)
            with self.assertRaises(config.ConfigError) as caught:
                config.load(self.root / "atlasmd.toml")
            self.assertIn(words, str(caught.exception))


class Area(Case):
    def test_area_writes_the_readme_and_the_entry_and_the_map(self):
        write(self.root, "services/billing/core/bill.py", "x\n")
        write(self.root, "docs/start/10-map.md", "# Map\n")
        before = (self.root / "atlasmd.toml").read_text(encoding="utf-8")
        code, out = self.amd("area", "services/billing")
        self.assertEqual(code, 0, out)
        readme = (self.root / "services/billing/README.md").read_text(encoding="utf-8")
        self.assertEqual(readme, cli.AREA_README.format(title="billing", date=datetime.date.today().isoformat()))
        self.assertIn("## How to run it", readme)
        self.assertIn("## State\n\nUpdated ", readme)
        after = (self.root / "atlasmd.toml").read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before.rstrip("\n") + "\n\n[[area]]\n"))
        cfg = config.load(self.root / "atlasmd.toml")
        self.assertEqual([(a.name, a.paths, a.pack) for a in cfg.areas][-1],
                         ("billing", ["services/billing/"], ["services/billing/README.md"]))
        self.assertIn("| billing | `services/billing/` | `services/billing/README.md` |",
                      (self.root / "docs/start/10-map.md").read_text(encoding="utf-8"))
        self.assertIn("services/billing/README.md, from the template", out)
        self.assertEqual(self.found("no-entry"), [])
        self.assertEqual(self.found("no-readme"), [])

    def test_area_keeps_a_readme_and_takes_a_name(self):
        write(self.root, "tools/README.md", "# My tools\n")
        write(self.root, "tools/run.sh", "echo\n")
        code, out = self.amd("area", "tools/", "--name", "the tools")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.root / "tools/README.md").read_text(encoding="utf-8"), "# My tools\n")
        self.assertIn("Left as it was:\n  tools/README.md", out)
        self.assertEqual(config.load(self.root / "atlasmd.toml").areas[-1].name, "the tools")

    def test_area_refuses_and_writes_nothing(self):
        write(self.root, "plain/notes.md", "# Notes\n")
        write(self.root, "lib/core/a.py", "x\n")
        self.settings('\n[[area]]\nname = "core"\npaths = ["lib/core/"]\npack = []\n')
        write(self.root, "web/app.js", "x\n")
        write(self.root, "app/deep/b.py", "x\n")
        before = (self.root / "atlasmd.toml").read_text(encoding="utf-8")
        for args, words in ((["nothing"], "There is no folder nothing/ in"),
                            (["plain"], "plain/ holds no source files"),
                            (["app"], "app/ is in the paths of the [[area]] \"the app\" already"),
                            (["app/deep"], "app/deep/ is in the paths of the [[area]] \"the app\" already, as app/."),
                            (["lib"], "The [[area]] \"core\" lists lib/core/, which is inside lib/"),
                            (["web", "--name", "the app"], "has an [[area]] with the name \"the app\" already")):
            code, out = self.amd("area", *args)
            self.assertNotEqual(code, 0, args)
            self.assertIn(words, out)
            self.assertIn("amd area made nothing.", out)
        self.assertEqual((self.root / "atlasmd.toml").read_text(encoding="utf-8"), before)
        self.assertFalse((self.root / "plain/README.md").exists())
        self.assertFalse((self.root / "web/README.md").exists())


class Init(unittest.TestCase):
    def test_init_writes_the_eight_rules_and_the_check_keys(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as data:
            root = Path(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), mock.patch.dict(os.environ, {"ATLASMD_DATA": data}):
                self.assertEqual(cli.main(["init"], cwd=tmp), 0)
            way = (root / "docs/start/40-way-of-work.md").read_text(encoding="utf-8")
            self.assertIn("\n## How the Markdown files live\n\n", way)
            self.assertEqual(len([line for line in way.split("## How the Markdown files live")[1].splitlines()
                                  if line.startswith("- ")]), 8)
            self.assertIn("The command /amd:area <folder> does all three.", way)
            self.assertIn("Then rewrite the state file.", way)
            text = (root / "atlasmd.toml").read_text(encoding="utf-8")
            self.assertIn("\n[check]\n", text)
            for key in ("folders = true", "stale_readme = 15", "dead_pointers = true", "plans = true", "notes = 30",
                        "decisions = true", "stale_state = 20", 'new_folders = "remind"',
                        'items = "docs/start/20-open-items.md"'):
                self.assertIn(key, text)
            self.assertTrue(all(line.split("#")[1].strip() for line in text.split("[check]")[1].split("\n\n")[0]
                                .splitlines()[2:]))
            cfg = config.load(root / "atlasmd.toml")
            self.assertEqual(cfg.check, config.Check())
            self.assertEqual((cfg.start.items, cfg.guard.new_folders), ("docs/start/20-open-items.md", "remind"))


if __name__ == "__main__":
    unittest.main()
