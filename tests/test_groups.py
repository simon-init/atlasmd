"""Several repositories as one group, the list of repositories, and amd config with its plain forms."""
import contextlib
import datetime
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import types
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "atlasmd" / "hook.py"
sys.path.insert(0, str(REPO))

from atlasmd import cli, config, projects, screen, setup  # noqa: E402

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
        self.assertEqual((row[0], row[2], row[3], row[4], row[5], row[6]), ("api", "shop", "deny", "yes", "30,000", "2"))
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


def rows(text):
    """The rows of the table that amd config --list prints, as {name: cells}, and the names in their order."""
    lines = text.splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith("repository"))
    found, order = {}, []
    for line in lines[head + 1:]:
        if not line.strip():
            break
        cells = re.split(r"\s{2,}", line.strip())
        found[cells[0]] = cells
        order.append(cells[0])
    return found, order


class FakeScreen:
    """The parts of the screen of amd config that the station Repositories uses, without curses."""
    curses = types.SimpleNamespace(KEY_UP=259, KEY_DOWN=258, KEY_ENTER=343)
    sort = screen.Config.sort
    drop = screen.Config.drop
    repo = screen.Config.repo

    def __init__(self, typed="", answer="y"):
        self.repos = [screen.Repo(e["path"], e["name"], e["group"]) for e in projects.load()]
        screen.sort_repos(self.repos)
        self.typed, self.answer, self.said, self.views = typed, answer, [], {}
        self.repositories = screen.Repositories(self)

    def ask_line(self, prompt):
        return self.typed

    def ask_key(self, question, keys):
        self.said.append(question)
        return ord(self.answer)

    def say(self, text, problem=False):
        self.said.append(text)

    def names(self):
        return [r.name for r in self.repos]


class StartFiles(Base):
    def test_the_table_shows_the_start_files_of_the_group_and_of_also_and_a_sentence_for_none(self):
        api = self.repo("api", "shop", ["10-map.md", "20-open-items.md"])
        app = self.repo("app", "shop", ["10-map.md"])
        web = self.repo("web", "shop", [])
        blog = self.repo("blog", None, [], also=["../api/docs/start"])
        lonely = self.repo("lonely", None, [])
        for root in (api, app, web, blog, lonely):
            projects.touch(root, "")
        code, text = self.amd("config", "--list")
        self.assertEqual(code, 0, text)
        found, _order = rows(text)
        self.assertEqual(found["web"][6:8], ["3 from group", found["api"][7]])
        self.assertEqual(found["blog"][6], "2 from also")
        self.assertEqual(found["app"][6], "1 + 2 from group")
        self.assertEqual(found["lonely"][6:8], ["0", "0"])
        self.assertNotEqual(found["web"][7], "0")
        self.assertIn("lonely: a session there gets nothing at the start, because docs/start/ and start.also give "
                      "no Markdown file, and it has no group.", text)
        self.assertNotIn("web: a session there gets nothing", text)
        data = {r["name"]: r for r in json.loads(self.amd("config", "--json")[1])["repositories"]}
        self.assertEqual((data["web"]["start_files"], data["web"]["own_files"], data["web"]["start_from"]), (3, 0, "group"))
        self.assertEqual((data["blog"]["start_files"], data["blog"]["start_from"]), (2, "also"))
        self.assertEqual((data["lonely"]["start_files"], data["lonely"]["start_tokens"]), (0, 0))


class Order(Base):
    def test_the_table_sorts_by_group_and_the_rows_without_a_group_come_last(self):
        for name, group in (("zeta", "alpha"), ("beta", None), ("alpha", "zulu"), ("gamma", "alpha"),
                            ("aardvark", None)):
            projects.touch(self.repo(name, group, ["10-map.md"]), "")
        _found, order = rows(self.amd("config", "--list")[1])
        self.assertEqual(order, ["gamma", "zeta", "alpha", "aardvark", "beta"])
        data = json.loads(self.amd("config", "--json")[1])
        self.assertEqual([r["name"] for r in data["repositories"]], order)

    def test_a_new_group_on_the_screen_moves_the_row_at_once(self):
        for name, group in (("api", "shop"), ("web", "shop"), ("blog", None), ("lonely", None)):
            projects.touch(self.repo(name, group, ["10-map.md"]), "")
        fake = FakeScreen(typed="shop")
        self.assertEqual(fake.names(), ["api", "web", "blog", "lonely"])
        fake.repositories.cursor = 3
        before = (self.base / "lonely" / "atlasmd.toml").read_text(encoding="utf-8")
        fake.repositories.key(ord("g"))
        self.assertEqual(fake.names(), ["api", "lonely", "web", "blog"])
        self.assertEqual(fake.repositories.selected().name, "lonely")
        self.assertEqual((self.base / "lonely" / "atlasmd.toml").read_text(encoding="utf-8"), before)  # s saves
        fake.typed = ""
        fake.repositories.key(ord("g"))
        self.assertEqual(fake.names(), ["api", "web", "blog", "lonely"])
        self.assertEqual(fake.repositories.selected().name, "lonely")


class Remove(Base):
    def files(self, root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}

    def test_remove_deletes_atlasmd_toml_and_keeps_every_other_file(self):
        from atlasmd import ledger
        api = self.repo("api", "shop", ["10-map.md", "20-open-items.md"])
        web = self.repo("web", "shop", ["10-map.md"])
        projects.touch(api, "")
        projects.touch(web, "")
        before = self.files(api)
        code, text = self.amd("config", "--remove", str(api))
        self.assertEqual(code, 0, text)
        self.assertIn("atlasmd left api", text)
        self.assertIn("docs/start/ and every other file stay", text)
        self.assertIn("amd init there sets atlasmd up again", text)
        self.assertFalse((api / "atlasmd.toml").exists())
        before.pop("atlasmd.toml")
        self.assertEqual(self.files(api), before)
        self.assertEqual([e["name"] for e in projects.load()], ["web"])
        self.assertNotIn("../api/", self.start(web) or "")  # the group lost its files with the entry
        self.assertTrue(ledger.seen_root(api))  # no offer of /amd:init at the next session there

    def test_remove_takes_a_name_and_refuses_one_that_is_not_on_the_list(self):
        web = self.repo("web", None, [])
        projects.touch(web, "")
        code, text = self.amd("config", "--remove", "nothing")
        self.assertEqual(code, 2)
        self.assertIn("nothing is not in the table of repositories in", text)
        code, text = self.amd("config", "--remove", "web")
        self.assertEqual(code, 0, text)
        self.assertEqual(projects.load(), [])
        self.assertFalse((web / "atlasmd.toml").exists())

    def test_remove_of_a_repository_without_atlasmd_toml_drops_the_row_only(self):
        web = self.repo("web", None, [])
        projects.touch(web, "")
        (web / "atlasmd.toml").unlink()
        code, text = self.amd("config", "--remove", str(web))
        self.assertEqual(code, 0, text)
        self.assertIn("had no atlasmd.toml", text)
        self.assertEqual(projects.load(), [])

    def test_r_on_a_row_asks_once_then_removes_atlasmd_from_the_repository(self):
        api = self.repo("api", "shop", ["10-map.md"])
        web = self.repo("web", None, [])
        projects.touch(api, "")
        projects.touch(web, "")
        before = self.files(api)
        fake = FakeScreen(answer="n")
        fake.repositories.key(ord("r"))
        self.assertEqual([e["name"] for e in projects.load()], ["api", "web"])
        self.assertTrue(any(s.startswith("Remove atlasmd from api? This deletes") for s in fake.said))
        self.assertEqual(self.files(api), before)
        fake.answer = "y"
        fake.repositories.key(ord("r"))
        self.assertEqual([e["name"] for e in projects.load()], ["web"])
        self.assertEqual(fake.names(), ["web"])
        self.assertIn("atlasmd left api", fake.repositories.note)
        self.assertFalse((api / "atlasmd.toml").exists())
        before.pop("atlasmd.toml")
        self.assertEqual(self.files(api), before)


class Words(Base):
    def test_a_person_reads_start_files_as_text_and_never_inject(self):
        api = self.repo("api", None, ["10-map.md"])
        projects.touch(api, "")
        self.amd("config", "--set", str(api), "start.inject", "false")
        found, _order = rows(self.amd("config", "--list")[1])
        self.assertIn("start files as text", cli.REPO_HEAD)
        self.assertEqual(found["api"][4], "no")
        self.assertFalse(any("inject" in head for head in cli.REPO_HEAD))
        self.assertFalse(any("inject" in key + meaning for keys in screen.HELP.values() for key, meaning in keys))
        self.assertEqual(screen.LABELS[("start", "inject")],
                         "Give the start files as text when they fit in 10,000 characters")
        line = next(x for x in config.defaults_text().splitlines() if x.startswith("inject = true"))
        self.assertIn("as text when they fit in 10,000 characters", line.split("#", 1)[1])
        self.assertNotIn("inject", line.split("#", 1)[1])
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("inject", readme)


class About(unittest.TestCase):
    def test_the_about_station_has_what_atlasmd_does_the_setup_the_commands_the_skills_and_how_to_turn_it_off(self):
        text = "\n".join(" ".join(seg[1] for seg in line if seg[1]) for line in screen.about_lines(400))
        for sentence in cli.WHAT:
            self.assertIn(sentence, text)
            self.assertIn(sentence, setup.WELCOME)
        for name, meaning in cli.COMMANDS:
            self.assertIn(f"amd {name} {meaning}", text)
        for name, meaning in cli.SKILLS:
            self.assertIn(f"{name} {meaning}", text)
        self.assertEqual(len(cli.SKILLS), len(list((REPO / "skills").glob("*/SKILL.md"))))
        steps = [line for line in text.splitlines() if line[:3] in ("1. ", "2. ", "3. ")]
        self.assertEqual([s.split()[1:3] for s in steps], [["amd", "init"], ["amd", "map"], ["amd", "check"]])
        self.assertIn("/amd:init in a Claude Code session", steps[0])
        for way in ("guard.mode = off, with m on a row", "delete atlasmd.toml", "ATLASMD=off claude",
                    "r on a row of Repositories, or amd config --remove <path>"):
            self.assertIn(way, text)


class CommandOnPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name).resolve() / "home"
        self.home.mkdir()

    def everything(self):
        return sorted(p.relative_to(self.home).as_posix() for p in self.home.rglob("*"))

    @unittest.skipIf(os.name == "nt", "the setup makes no link on Windows")
    def test_put_amd_on_my_path_makes_the_folder_and_the_link_and_nothing_else(self):
        answer, lines = setup.link_amd(self.home, path_value="/usr/bin", shell="/usr/bin/fish")
        link = self.home / ".local" / "bin" / "amd"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.path.realpath(link), os.path.realpath(REPO / "bin" / "amd"))
        self.assertEqual(self.everything(), [".local", ".local/bin", ".local/bin/amd"])
        text = "\n".join(lines)
        self.assertIn("    mkdir -p ~/.local/bin", text)
        self.assertIn(f"    ln -s {REPO / 'bin' / 'amd'} ~/.local/bin/amd", text)
        self.assertIn("~/.local/bin is not on the PATH of this shell. Add this line to ~/.config/fish/config.fish", text)
        self.assertIn("    fish_add_path ~/.local/bin", text)
        self.assertTrue(answer.startswith("~/.local/bin/amd links to"))
        answer, lines = setup.link_amd(self.home, path_value=str(self.home / ".local" / "bin"), shell="/bin/zsh")
        self.assertIn("already", answer)
        self.assertIn("~/.local/bin is on the PATH of this shell", "\n".join(lines))
        self.assertEqual(self.everything(), [".local", ".local/bin", ".local/bin/amd"])

    @unittest.skipIf(os.name == "nt", "the setup makes no link on Windows")
    def test_an_existing_amd_stays_and_not_now_gives_the_command(self):
        self.assertEqual(setup.link_line(self.home),
                         f"mkdir -p ~/.local/bin && ln -s {REPO / 'bin' / 'amd'} ~/.local/bin/amd")
        mine = self.home / ".local" / "bin" / "amd"
        mine.parent.mkdir(parents=True)
        mine.write_text("mine\n", encoding="utf-8")
        self.assertEqual(setup.link_line(self.home), f"ln -s {REPO / 'bin' / 'amd'} ~/.local/bin/amd")
        answer, lines = setup.link_amd(self.home, path_value="", shell="/bin/bash")
        self.assertIn("nothing changed", answer)
        self.assertEqual(mine.read_text(encoding="utf-8"), "mine\n")
        self.assertEqual(setup.start_file_line("/bin/bash"), ("~/.bashrc", 'export PATH="$HOME/.local/bin:$PATH"'))
        self.assertEqual(setup.start_file_line("/bin/zsh")[0], "~/.zshrc")


class OutsideARepository(Base):
    def test_a_command_that_needs_atlasmd_toml_says_so_and_the_others_work(self):
        empty = self.base / "empty"
        empty.mkdir()
        for args in (["check"], ["map"], ["area", "api"], ["area"], ["meter"], ["meter", "--json"]):
            code, text = self.amd(*args, cwd=empty)
            self.assertEqual((code, text.strip()), (1, cli.NO_REPOSITORY), args)
        for args in ([], ["config", "--list"], ["config", "--json"], ["meter", "--list"], ["version"]):
            code, text = self.amd(*args, cwd=empty)
            self.assertEqual(code, 0, (args, text))
            self.assertNotIn(cli.NO_REPOSITORY, text)
        code, text = self.amd("setup", cwd=empty)
        self.assertNotIn(cli.NO_REPOSITORY, text)
        for args in (["scan"], ["init", "--dry-run"], ["status"], ["why"], ["end"]):
            code, text = self.amd(*args, cwd=empty)  # a plain sentence, never a traceback
            self.assertIn(code, (0, 1), (args, text))
            self.assertNotIn("Traceback", text)


if __name__ == "__main__":
    unittest.main()
