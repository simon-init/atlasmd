"""Several repositories as one group, the list of repositories, and amd config with its plain forms."""
import contextlib
import datetime
import io
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

from atlasmd import cli, config, projects, screen  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def write(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def git(root, *args):
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=master", *args], cwd=root,
                          capture_output=True, text=True, env={**os.environ, **GIT_ENV}, check=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name).resolve()
        self.data = self.base / "data"
        old = {k: os.environ.get(k) for k in ("ATLASMD_DATA", "ATLASMD", "CLAUDE_PROJECT_DIR")}
        os.environ["ATLASMD_DATA"] = str(self.data)
        os.environ.pop("ATLASMD", None)
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])

    def repo(self, name, group=None, start=(), also=None):
        """A repository with atlasmd.toml and the files of docs/start/ that start names."""
        root = self.base / name
        root.mkdir()
        lines = [f'group = "{group}"', ""] if group is not None else []
        lines += ["[start]", f"also = {json.dumps(also or [])}", "", "[guard]", 'mode = "deny"']
        write(root / "atlasmd.toml", "\n".join(lines) + "\n")
        for file in start:
            write(root / "docs/start" / file, f"# {name} {file}\n\nThe text of {file} in {name}.\n")
        (root / ".git").mkdir()
        return root

    def amd(self, *args, cwd=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(list(args), cwd=str(cwd or self.base))
        return code, buf.getvalue()

    def hook(self, payload, **env):
        payload = {"session_id": "s1", "transcript_path": str(self.base / "t.jsonl"), **payload}
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ATLASMD"))}
        proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                              env={**clean, "ATLASMD_DATA": str(self.data), **env}, timeout=30)
        self.assertEqual((proc.returncode, proc.stderr), (0, ""))
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def start(self, root, **env):
        answer = self.hook({"hook_event_name": "SessionStart", "source": "startup", "cwd": str(root)}, **env)
        return answer["hookSpecificOutput"]["additionalContext"] if answer else None


class TheList(Base):
    def test_init_writes_the_entry_and_the_hook_refreshes_it(self):
        root = self.base / "web"
        root.mkdir()
        git(root, "init", "-q")
        code, text = self.amd("init", cwd=root)
        self.assertEqual(code, 0, text)
        entries = projects.load()
        self.assertEqual([(e["path"], e["name"], e["group"], e["seen"]) for e in entries], [(str(root), "web", "", "")])
        text = (root / "atlasmd.toml").read_text(encoding="utf-8")
        write(root / "atlasmd.toml", text.replace('# group = "my-project"', 'group = "shop"'))
        os.utime(root / "atlasmd.toml")
        self.start(root)
        entries = projects.load()
        self.assertEqual([(e["name"], e["group"]) for e in entries], [("web", "shop")])
        self.assertTrue(entries[0]["seen"].startswith(datetime.date.today().isoformat()))

    def test_dry_run_writes_no_entry(self):
        root = self.base / "web"
        root.mkdir()
        git(root, "init", "-q")
        self.amd("init", "--dry-run", cwd=root)
        self.assertEqual(projects.load(), [])

    def test_an_entry_whose_folder_is_gone_is_dropped_at_the_next_write(self):
        one, two = self.repo("one"), self.repo("two")
        projects.touch(one, "")
        projects.touch(two, "")
        self.assertEqual([e["name"] for e in projects.load()], ["one", "two"])
        for path in sorted(two.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        two.rmdir()
        self.start(one)
        self.assertEqual([e["name"] for e in projects.load()], ["one"])


class TheGroup(Base):
    def test_a_session_start_gets_the_files_of_the_group_own_first_each_once(self):
        api = self.repo("api", "shop", ["10-map.md", "20-open-items.md"], also=["../web/docs/start"])
        web = self.repo("web", "shop", ["10-map.md", "30-state.md"])
        app = self.repo("app", "shop", ["10-map.md"])
        other = self.repo("blog", "news", ["10-map.md"])
        for root in (api, web, app, other):
            projects.touch(root, "")  # the group of the list is old: the hook reads each atlasmd.toml
        text = self.start(api)
        self.assertTrue(text.startswith('atlasmd: api and 2 more repositories of the group "shop" have 5 files to '
                                        "read at the start, about "), text)
        heads = [line[3:] for line in text.splitlines() if line.startswith("## ")]
        self.assertEqual(heads, ["docs/start/10-map.md", "docs/start/20-open-items.md", "../web/docs/start/10-map.md",
                                 "../web/docs/start/30-state.md", "../app/docs/start/10-map.md"])
        self.assertNotIn("blog", text)

    def test_a_repository_without_a_group_gets_its_own_files_only(self):
        alone = self.repo("alone", None, ["10-map.md"])
        web = self.repo("web", "shop", ["10-map.md"])
        projects.touch(alone, "")
        projects.touch(web, "shop")
        text = self.start(alone)
        self.assertTrue(text.startswith("atlasmd: alone has 1 file to read at the start, about "), text)
        self.assertNotIn("../web", text)

    def test_check_names_the_group(self):
        api = self.repo("api", "shop", ["10-map.md"])
        web = self.repo("web", "shop", ["10-map.md"])
        projects.touch(api, "shop")
        _code, text = self.amd("check", cwd=api)
        self.assertIn('group       "shop" has no other repository on this machine.', text)
        projects.touch(web, "shop")
        _code, text = self.amd("check", cwd=api)
        self.assertIn('group       "shop": web. Claude gets the files of its docs/start/', text)


class ConfigForms(Base):
    def test_set_replaces_a_key_uncomments_a_key_appends_a_key_and_keeps_the_comments(self):
        root = self.base / "web"
        root.mkdir()
        write(root / "atlasmd.toml", config.defaults_text().replace('budget = 30000                     # the limit'
                                                                    ' in estimated tokens. Above it, Claude gets the '
                                                                    'list of the files and a warning, not their text\n',
                                                                    ""))
        before = (root / "atlasmd.toml").read_text(encoding="utf-8").splitlines()
        self.assertEqual(self.amd("config", "--set", str(root), "guard.mode", "remind")[0], 0)
        self.assertEqual(self.amd("config", "--set", "web", "group", "shop")[0], 0)
        self.assertEqual(self.amd("config", "--set", str(root), "start.budget", "40,000")[0], 0)
        self.assertEqual(self.amd("config", "--set", str(root), "start.inject", "false")[0], 0)
        after = (root / "atlasmd.toml").read_text(encoding="utf-8").splitlines()
        cfg = config.load(root / "atlasmd.toml")
        self.assertEqual((cfg.group, cfg.guard.mode, cfg.start.budget, cfg.start.inject), ("shop", "remind", 40000, False))
        changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        self.assertEqual(len(after), len(before) + 1)  # the budget is the one new line
        self.assertTrue(after[3].startswith('group = "shop"') and after[3].endswith("share their docs/start/ at a "
                                                                                   "session's start"))
        mode = next(line for line in after if line.startswith("mode ="))
        self.assertIn('mode = "remind"', mode)
        self.assertIn("# deny: refuse the edit", mode)
        self.assertIn("budget = 40000", after)
        comments = [line for line in before if line.lstrip().startswith("#") and "group =" not in line]
        self.assertTrue(all(line in after for line in comments))
        self.assertTrue(changed)
        self.assertEqual(self.amd("config", "--set", str(root), "guard.mode", "maybe")[0], 2)
        self.assertEqual(self.amd("config", "--set", str(root), "group", "two words")[0], 2)
        self.assertEqual(self.amd("config", "--set", str(root), "colour", "red")[0], 2)

    def test_list_and_json_show_every_repository_with_its_group(self):
        api = self.repo("api", "shop", ["10-map.md", "20-open-items.md"])
        web = self.repo("web", None, [])
        projects.touch(api, "")
        projects.touch(web, "")
        code, text = self.amd("config", "--list", cwd=self.base)
        self.assertEqual(code, 0, text)
        lines = text.splitlines()
        head = next(i for i, line in enumerate(lines) if line.startswith("repository"))
        self.assertEqual(lines[head].split("  ")[0], "repository")
        row = lines[head + 1].split()
        self.assertEqual((row[0], row[2], row[3], row[4], row[5], row[6]), ("api", "shop", "deny", "true", "30,000", "2"))
        self.assertEqual(lines[head + 2].split()[2], "none")
        data = json.loads(self.amd("config", "--json")[1])
        self.assertEqual([r["name"] for r in data["repositories"]], ["api", "web"])
        self.assertEqual(data["repositories"][0]["start_files"], 2)

    def test_config_in_a_repository_adds_it_to_the_list(self):
        api = self.repo("api", "shop", ["10-map.md"])
        self.amd("config", "--list", cwd=api / "docs")
        self.assertEqual([(e["name"], e["group"]) for e in projects.load()], [("api", "shop")])

    def test_p_writes_the_private_files_and_the_exclude_file(self):
        root = self.base / "web"
        root.mkdir()
        git(root, "init", "-q")
        self.amd("init", cwd=root)
        write(root / "docs/notes/2026-10-16-mine.md", "# Mine\n")
        cfg = config.load(root / "atlasmd.toml")
        text = cli.toggle_private(cfg, "docs/notes/2026-10-16-mine.md")
        self.assertIn(".git/info/exclude", text)
        exclude = (root / ".git/info/exclude").read_text(encoding="utf-8").splitlines()
        self.assertIn("/docs/notes/2026-10-16-mine.md", exclude)
        self.assertIn(cli.EXCLUDE_HEAD, exclude)
        cfg = config.load(root / "atlasmd.toml")
        self.assertEqual(cfg.private, ["docs/notes/2026-10-16-mine.md"])
        status = git(root, "status", "--porcelain", "--untracked-files=all").stdout
        self.assertNotIn("2026-10-16-mine.md", status)
        cli.toggle_private(cfg, "docs/notes/2026-10-16-mine.md")
        self.assertNotIn("/docs/notes/2026-10-16-mine.md",
                         (root / ".git/info/exclude").read_text(encoding="utf-8").splitlines())
        self.assertEqual(config.load(root / "atlasmd.toml").private, [])

    def test_the_toml_editor_keeps_a_list_on_several_lines_in_one_piece(self):
        text = '[private]\nfiles = [\n  "a.md",\n  "b.md",\n]   # the files\n\n[naming]\n"docs" = "x"\n'
        new = screen.set_toml_value(text, "private", "files", ["a.md"])
        self.assertEqual(new, '[private]\nfiles = ["a.md"]   # the files\n\n[naming]\n"docs" = "x"\n')


if __name__ == "__main__":
    unittest.main()
