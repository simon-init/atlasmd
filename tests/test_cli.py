"""The command line of atlasmd, on a fixture repository in a temporary folder."""
import contextlib
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from atlasmd import cli, config, ledger, tui  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(root, *args):
    hooks = Path(root).parent / "no-hooks"
    hooks.mkdir(exist_ok=True)
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={hooks}",
                           "-c", "init.defaultBranch=master", *args],
                          cwd=root, capture_output=True, text=True, env={**os.environ, **GIT_ENV}, check=True)


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def fixture(base):
    """A small project: a README, a CLAUDE.md, two code folders with a README each, an old note."""
    root = Path(base) / "project"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    write(root, "README.md", "# Fixture\n\nA project for the tests.\n")
    write(root, "CLAUDE.md", "# Rules\n\nRead `docs/old-notes.md` first.\n")
    write(root, "services/scrub/README.md", "# The scrubber\n\nHow it works.\n")
    write(root, "services/scrub/core/a.py", "x = 1\n")
    write(root, "web/README.md", "# The web app\n")
    write(root, "web/app.js", "console.log(1)\n")
    write(root, "docs/old-notes.md", "# Old notes\n")
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {k: os.environ.get(k) for k in ("ATLASMD_DATA", "CLAUDE_PROJECT_DIR",
                                                    "CLAUDE_PLUGIN_OPTION_OFFER_SETUP")}
        os.environ["ATLASMD_DATA"] = str(Path(self.tmp.name) / "data")
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        os.environ.pop("CLAUDE_PLUGIN_OPTION_OFFER_SETUP", None)
        self.addCleanup(self.restore_env)
        self.root = fixture(self.tmp.name)

    def restore_env(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def amd(self, *args, cwd=None):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = cli.main(list(args), cwd=str(cwd or self.root))
        return code, buf.getvalue() + err.getvalue()

    def files(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if ".git" not in p.parts)

    def areas_file(self, areas):
        path = Path(self.tmp.name) / "areas.json"
        path.write_text(json.dumps(areas), encoding="utf-8")
        return str(path)


class Help(Base):
    def test_plain_amd_prints_the_logo_and_every_command(self):
        code, text = self.amd()
        self.assertEqual(code, 0)
        self.assertIn(tui.LOGO[1], text)
        self.assertIn(tui.TAGLINE, text)
        for name in ("setup", "config", "scan", "init", "check", "map", "status", "why", "end", "set", "version"):
            self.assertIn(f"amd {name}", text)
        self.assertTrue(all(len(line) <= 80 for line in text.splitlines()))

    def test_an_unknown_command_exits_2(self):
        code, text = self.amd("nothing")
        self.assertEqual(code, 2)
        self.assertIn("no command nothing", text)

    def test_the_script_runs_from_its_own_folder(self):
        result = subprocess.run([sys.executable, str(ROOT / "atlasmd" / "cli.py"), "version"],
                                capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __import__("atlasmd").__version__)


class Init(Base):
    def test_init_writes_the_config_and_the_four_files_and_overwrites_nothing(self):
        code, text = self.amd("init")
        self.assertEqual(code, 0, text)
        self.assertEqual((self.root / "atlasmd.toml").read_text(encoding="utf-8").strip(),
                         config.defaults_text().strip())
        for name, key in (("10-map.md", "map"), ("20-open-items.md", "open-items"),
                          ("30-state.md", "state"), ("40-way-of-work.md", "way-of-work")):
            self.assertEqual((self.root / "docs/start" / name).read_text(encoding="utf-8"), cli.TEMPLATES[key])
            self.assertLess(len(cli.TEMPLATES[key].splitlines()), 30)
        for folder in ("decisions", "plans", "notes", "archive"):
            self.assertTrue((self.root / "docs" / folder).is_dir())
        write(self.root, "docs/start/30-state.md", "# Where things stand\n\nMine.\n")
        write(self.root, "atlasmd.toml", "[guard]\nmode = \"remind\"\n")
        code, text = self.amd("init")
        self.assertEqual(code, 0, text)
        self.assertIn("Made:\n  nothing", text)
        self.assertEqual((self.root / "docs/start/30-state.md").read_text(encoding="utf-8"), "# Where things stand\n\nMine.\n")
        self.assertEqual((self.root / "atlasmd.toml").read_text(encoding="utf-8"), "[guard]\nmode = \"remind\"\n")

    def test_the_four_templates_stay_under_ten_lines_of_text(self):
        for key, text in cli.TEMPLATES.items():
            text = text.split("## How the Markdown files live")[0]  # the eight rules of 0.2 come on top
            words = [line for line in text.splitlines() if line.strip() and not line.startswith(("|", "<!--"))]
            self.assertLessEqual(len(words), 10, key)

    def test_areas_json_lands_in_the_config(self):
        areas = [{"name": "the scrubber", "paths": ["services/scrub/"], "pack": ["services/scrub/README.md"]},
                 {"name": "the web app", "paths": ["web/"], "pack": ["web/README.md", "docs/product.md#P15"]}]
        code, text = self.amd("init", "--areas-json", self.areas_file(areas))
        self.assertEqual(code, 0, text)
        cfg = config.load(self.root / "atlasmd.toml")
        self.assertEqual([(a.name, a.paths, a.pack) for a in cfg.areas],
                         [(a["name"], a["paths"], a["pack"]) for a in areas])

    def test_areas_json_is_not_added_to_a_config_that_exists(self):
        write(self.root, "atlasmd.toml", "")
        areas = [{"name": "the web app", "paths": ["web/"], "pack": ["web/README.md"]}]
        code, text = self.amd("init", "--areas-json", self.areas_file(areas))
        self.assertEqual(code, 0, text)
        self.assertEqual((self.root / "atlasmd.toml").read_text(encoding="utf-8"), "")
        self.assertIn('name = "the web app"', text)

    def test_dry_run_writes_nothing(self):
        before = self.files()
        code, text = self.amd("init", "--dry-run", "--areas-json",
                              self.areas_file([{"name": "a", "paths": ["web/"], "pack": []}]))
        self.assertEqual(code, 0, text)
        self.assertIn("To make:", text)
        self.assertIn("docs/start/10-map.md", text)
        self.assertEqual(self.files(), before)

    def test_bad_areas_json_writes_nothing(self):
        before = self.files()
        code, text = self.amd("init", "--areas-json", self.areas_file([{"paths": ["web/"]}]))
        self.assertEqual(code, 2)
        self.assertIn("must be an object with a name", text)
        code, _ = self.amd("init", "--areas-json", self.areas_file([{"name": "a", "paths": ["/abs/"], "pack": []}]))
        self.assertEqual(code, 2)
        self.assertEqual(self.files(), before)

    def test_private_files_go_into_the_exclude_file_once(self):
        write(self.root, "atlasmd.toml", '[private]\nfiles = ["docs/start/50-mine.md"]\n')
        self.amd("init")
        self.amd("init")
        exclude = (self.root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.count("/docs/start/50-mine.md"), 1)


class Check(Base):
    def test_check_reports_each_problem_then_passes(self):
        areas = [{"name": "the scrubber", "paths": ["services/scrub/"],
                  "pack": ["services/scrub/README.md", "docs/decisions/P001-policy.md"]},
                 {"name": "the core", "paths": ["services/scrub/core/"], "pack": []}]
        self.amd("init", "--areas-json", self.areas_file(areas))
        write(self.root, "docs/notes/a-note.md", "# A note\n")
        self.amd("map")
        code, text = self.amd("check", "--json")
        self.assertEqual(code, 1, text)
        found = json.loads(text)
        kinds = {f["kind"] for f in found["findings"]}
        self.assertEqual(kinds, {"missing-pack", "empty-pack", "overlap", "naming", "unread", "no-entry"})
        paths = {f["path"] for f in found["findings"]}
        self.assertIn("docs/decisions/P001-policy.md", paths)
        self.assertIn("docs/notes/a-note.md", paths)
        self.assertIn("docs/old-notes.md", paths)
        self.assertIn("web/README.md", paths)
        self.assertNotIn("README.md", paths)
        self.assertNotIn("CLAUDE.md", paths)
        self.assertEqual(found["budget"]["budget"], 30000)
        self.assertEqual(len(found["budget"]["files"]), 4)
        code, plain = self.amd("check")
        self.assertEqual(code, 1)
        self.assertTrue(any(line.startswith("✗ overlap") for line in plain.splitlines()))
        self.assertTrue(any(line.startswith("✓ start") for line in plain.splitlines()))

        # Fix every problem, and the check passes.
        write(self.root, "docs/decisions/P001-policy.md", "# P001 The policy\n")
        write(self.root, "docs/decisions/README.md", "# Decisions\n\n- P1 `docs/decisions/P001-policy.md` The policy\n")
        (self.root / "docs/notes/a-note.md").rename(self.root / f"docs/notes/{datetime.date.today()}-a-note.md")
        (self.root / "docs/old-notes.md").rename(self.root / "docs/archive/old-notes.md")
        text = (self.root / "atlasmd.toml").read_text(encoding="utf-8")
        text = text.replace('name = "the core"\npaths = ["services/scrub/core/"]\npack = []',
                            'name = "the web app"\npaths = ["web/"]\npack = ["web/README.md"]')
        write(self.root, "atlasmd.toml", text)
        code, plain = self.amd("check")
        self.assertEqual(code, 1, plain)
        self.assertIn("Run amd map", plain)
        self.amd("map")
        code, plain = self.amd("check")
        self.assertEqual(code, 0, plain)
        self.assertIn("No problems.", plain)

    def test_check_without_a_config_says_how_to_start(self):
        code, text = self.amd("check")
        self.assertEqual(code, 1)
        self.assertIn("amd init", text)

    def test_check_reports_a_start_reading_over_its_budget(self):
        self.amd("init")
        text = (self.root / "atlasmd.toml").read_text(encoding="utf-8").replace("budget = 30000", "budget = 10")
        write(self.root, "atlasmd.toml", text)
        self.amd("map")
        code, out = self.amd("check", "--json")
        self.assertEqual(code, 1)
        self.assertIn("budget", {f["kind"] for f in json.loads(out)["findings"]})


class Map(Base):
    def test_map_writes_between_the_markers_and_keeps_the_rest(self):
        self.amd("init", "--areas-json", self.areas_file(
            [{"name": "the web | app", "paths": ["web/"], "pack": ["web/README.md"]}]))
        path = self.root / "docs/start/10-map.md"
        original = path.read_text(encoding="utf-8").replace("One paragraph", "My own paragraph")
        path.write_text(original + "\nA closing line.\n", encoding="utf-8")
        code, text = self.amd("map")
        self.assertEqual(code, 0, text)
        first = path.read_text(encoding="utf-8")
        self.assertIn("My own paragraph", first)
        self.assertTrue(first.endswith("\nA closing line.\n"))
        self.assertIn("- `web/README.md`: The web app", first)
        self.assertIn("| the web \\| app | `web/` | `web/README.md` |", first)
        self.assertEqual(first.count("<!-- atlasmd:tree -->"), 1)
        self.amd("map")
        self.assertEqual(path.read_text(encoding="utf-8"), first)

    def test_map_adds_missing_markers_at_the_end(self):
        self.amd("init")
        path = self.root / "docs/start/10-map.md"
        path.write_text("# The map\n\nNo markers here.", encoding="utf-8")
        code, text = self.amd("map")
        self.assertEqual(code, 0)
        self.assertIn("was missing", text)
        result = path.read_text(encoding="utf-8")
        self.assertTrue(result.startswith("# The map\n\nNo markers here.\n"))
        self.assertLess(result.index("<!-- atlasmd:areas -->"), result.index("<!-- atlasmd:tree -->"))
        self.amd("map")
        self.assertEqual(path.read_text(encoding="utf-8"), result)


class Scan(Base):
    def test_scan_json_lists_the_files_with_sizes_and_the_area_candidates(self):
        code, text = self.amd("scan", "--json")
        self.assertEqual(code, 0)
        data = json.loads(text)
        files = {f["path"]: f for f in data["files"]}
        self.assertEqual(set(files), {"README.md", "CLAUDE.md", "services/scrub/README.md", "web/README.md",
                                      "docs/old-notes.md"})
        self.assertGreater(files["README.md"]["tokens"], 0)
        self.assertIn("kb", files["README.md"])
        self.assertEqual(files["web/README.md"]["heading"], "The web app")
        self.assertEqual(data["total"]["files"], 5)
        candidates = {c["path"]: c for c in data["candidates"]}
        self.assertEqual(set(candidates), {"services/scrub/", "web/"})
        self.assertEqual(candidates["services/scrub/"]["heading"], "The scrubber")
        self.assertFalse(data["config"])
        self.assertFalse(data["start_dir"])
        self.assertEqual(data["claude_md"]["names"], [{"name": "docs/old-notes.md", "exists": True}])

    def test_scan_plain_shows_the_tree(self):
        code, text = self.amd("scan")
        self.assertEqual(code, 0)
        self.assertIn("services/", text)
        self.assertIn("Folders with source files and a README  2", text)

    def test_scan_lists_the_code_folders_without_a_readme(self):
        data = json.loads(self.amd("scan", "--json")[1])
        self.assertEqual(data["without_readme"], [])
        write(self.root, "tools/run.py", "x = 1\n")
        write(self.root, "tools/deep/more.py", "y = 2\n")
        data = json.loads(self.amd("scan", "--json")[1])
        self.assertEqual(data["without_readme"], [{"path": "tools/", "source_files": 2}])
        self.assertNotIn("tools/", {c["path"] for c in data["candidates"]})
        code, text = self.amd("scan")
        self.assertIn("Folders with source files and no README  1", text)
        self.assertIn("  tools/     2 source files", text)

    def test_scan_skips_ignored_files(self):
        write(self.root, ".gitignore", "secret/\n")
        write(self.root, "secret/notes.md", "# Mine\n")
        data = json.loads(self.amd("scan", "--json")[1])
        self.assertNotIn("secret/notes.md", {f["path"] for f in data["files"]})


class End(Base):
    def test_end_exits_1_with_an_uncommitted_file_and_0_when_clean(self):
        self.amd("init")
        code, text = self.amd("end")
        self.assertEqual(code, 1, text)
        self.assertIn("?? ", text)
        self.assertIn("Say where things stand.", text)
        git(self.root, "add", "--", ".")
        git(self.root, "commit", "-q", "-m", "all")
        code, text = self.amd("end")
        self.assertEqual(code, 0, text)
        self.assertIn("✓ committed", text)

    def test_end_outside_git_exits_1(self):
        outside = Path(self.tmp.name) / "plain"
        outside.mkdir()
        code, text = self.amd("end", cwd=outside)
        self.assertIn(code, (1,))


class Personal(Base):
    def test_set_writes_the_personal_settings(self):
        code, _ = self.amd("set", "token_chars", "3")
        self.assertEqual(code, 0)
        code, _ = self.amd("set", "offer_setup", "no")
        self.assertEqual(code, 0)
        self.assertEqual(cli.read_personal(), {"token_chars": 3.0, "offer_setup": False})
        self.assertEqual(cli.personal_path().parent, Path(os.environ["ATLASMD_DATA"]))
        self.assertEqual(self.amd("set", "offer_setup", "maybe")[0], 2)
        self.assertEqual(self.amd("set", "colour", "red")[0], 2)
        self.assertEqual(self.amd("set", "token_chars", "-1")[0], 2)


class Ledger(Base):
    def test_status_and_why_read_the_ledger(self):
        self.amd("init", "--areas-json", self.areas_file(
            [{"name": "the scrubber", "paths": ["services/scrub/"],
              "pack": ["services/scrub/README.md", "docs/old-notes.md"]}]))
        code, text = self.amd("why")
        self.assertEqual(code, 0)
        self.assertIn("No refused edit", text)
        key = ledger.key({"session_id": "s1"})
        ledger.add(key, self.root / "services/scrub/README.md")
        ledger.record_refusal(key, "atlasmd refused the edit of services/scrub/core/a.py.")
        ledger.log_compact(str(self.root), "auto", 4812)
        code, text = self.amd("status", "--session", "s1")
        self.assertEqual(code, 0, text)
        self.assertIn("1 of 2 files", text)
        self.assertIn("docs/old-notes.md", text)
        self.assertIn("auto", text)
        code, text = self.amd("why")
        self.assertEqual(code, 0)
        self.assertIn("refused the edit of services/scrub/core/a.py", text)
        self.assertIn("guard.mode", text)


class SettingsFile(unittest.TestCase):
    def test_a_value_changes_in_place_and_the_comment_stays(self):
        from atlasmd import screen
        text = config.defaults_text()
        new = screen.set_toml_value(text, "guard", "mode", "remind")
        new = screen.set_toml_value(new, "start", "budget", 40000)
        new = screen.set_toml_value(new, "start", "inject", False)
        lines = new.splitlines()
        mode = next(line for line in lines if line.startswith("mode ="))
        self.assertEqual(mode.index("#"), next(line for line in text.splitlines() if line.startswith("mode =")).index("#"))
        self.assertIn('mode = "remind"', mode)
        self.assertEqual(len(lines), len(text.splitlines()))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "atlasmd.toml"
            path.write_text(new, encoding="utf-8")
            cfg = config.load(path)
        self.assertEqual((cfg.guard.mode, cfg.start.budget, cfg.start.inject), ("remind", 40000, False))

    def test_a_missing_key_and_a_missing_table_are_added(self):
        from atlasmd import screen
        text = '[guard]\nbash = true\n\n[[area]]\nname = "x"\n'
        new = screen.set_toml_value(text, "guard", "mode", "off")
        self.assertIn('[guard]\nbash = true\nmode = "off"\n', new)
        new = screen.set_toml_value(new, "agents", "inject", "none")
        self.assertTrue(new.endswith('[agents]\ninject = "none"\n'))


class Route(unittest.TestCase):
    def test_the_route_marks_passed_current_and_ahead(self):
        marks, labels = tui.route(["Welcome", "How it works", "You"], 1, 80)
        line = tui.route_text(["Welcome", "How it works", "You"], 1, 80)
        self.assertEqual(line[0], "●────────◉─────────────○")
        self.assertEqual(line[1], "Welcome  How it works  You")
        self.assertEqual([k for _x, _t, k in labels], ["passed", "current", "ahead"])

    def test_a_narrow_route_shows_a_window_around_the_current_station(self):
        names = [f"area {i}" for i in range(12)]
        for width in (20, 40, 80):
            for line in tui.route_text(names, 6, width):
                self.assertLessEqual(len(line), width + 1)
            self.assertIn("◉", tui.route_text(names, 6, width)[0])

    def test_fit_cuts_with_an_ellipsis(self):
        self.assertEqual(tui.fit("abcdef", 4), "abc…")
        self.assertEqual(tui.fit("abc", 4), "abc")


if __name__ == "__main__":
    unittest.main()


class InitUndo(Base):
    def test_undo_removes_what_init_made_while_nothing_changed(self):
        before = self.files()
        code, text = self.amd("init")
        self.assertEqual(code, 0, text)
        self.assertIn("amd init --undo", text)
        code, text = self.amd("init", "--undo", "--dry-run")
        self.assertEqual(code, 0, text)
        self.assertIn("To remove:", text)
        self.assertTrue((self.root / "atlasmd.toml").is_file())
        code, text = self.amd("init", "--undo")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.files(), before)
        self.assertIn("  docs/start/\n", text)
        self.assertIn("  docs/plans/\n", text)
        self.assertIn("docs/  (not empty)", text)  # docs/old-notes.md was there before init
        self.assertIn("left the table of repositories", text)

    def test_undo_refuses_after_a_change_and_removes_nothing(self):
        self.amd("init")
        write(self.root, "docs/start/30-state.md", "# Where things stand\n\nMine.\n")
        code, text = self.amd("init", "--undo")
        self.assertEqual(code, 1)
        self.assertIn("docs/start/30-state.md", text)
        self.assertIn("Nothing removed", text)
        self.assertTrue((self.root / "atlasmd.toml").is_file())
        self.assertTrue((self.root / "docs/start/10-map.md").is_file())

    def test_undo_outside_a_repository_says_so(self):
        code, text = self.amd("init", "--undo", cwd=self.tmp.name)
        self.assertEqual(code, 1)
        self.assertIn("nothing to undo", text)
