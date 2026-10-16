"""Tests of the settings, the areas and the start reading, in the process."""
import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from atlasmd import areas, config, start  # noqa: E402
from atlasmd.config import ConfigError  # noqa: E402

AREAS = """
[[area]]
name = "the scrubber"
paths = ["services/scrubber/", "services/scrubber/policy/", "tools/scrub.py"]
pack = ["services/scrubber/README.md", "docs/product-decisions.md#P15", "./docs/policy.md"]

[[area]]
name = "the policy"
paths = ["services/scrubber/policy/strict/"]
pack = ["docs/policy.md"]
"""


def write(path: pathlib.Path, text: str = "x\n") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name).resolve() / "project"
        self.root.mkdir()
        self._env = os.environ.pop("CLAUDE_PROJECT_DIR", None)

    def tearDown(self):
        if self._env is not None:
            os.environ["CLAUDE_PROJECT_DIR"] = self._env
        self._tmp.cleanup()

    def settings(self, text: str) -> config.Config:
        write(self.root / config.CONFIG_NAME, text)
        return config.load(self.root / config.CONFIG_NAME)

    def refused(self, text: str, words: str):
        with self.assertRaises(ConfigError) as caught:
            self.settings(text)
        self.assertIn(words, str(caught.exception))


class Load(Case):
    def test_the_default_text_gives_the_defaults(self):
        cfg = self.settings(config.defaults_text())
        self.assertEqual(cfg.start, config.Start())
        self.assertEqual(cfg.guard, config.Guard())
        self.assertEqual(cfg.agents, config.Agents())
        self.assertEqual(cfg.private, [])
        self.assertEqual(cfg.naming, config.DEFAULT_NAMING)
        self.assertEqual(cfg.areas, [])
        self.assertEqual((cfg.root, cfg.path), (self.root, self.root / config.CONFIG_NAME))

    def test_an_empty_file_gives_the_defaults(self):
        cfg = self.settings("")
        self.assertEqual(cfg.start.budget, 30000)
        self.assertEqual(cfg.naming, config.DEFAULT_NAMING)
        self.assertEqual(cfg.naming["docs/start"], r"^[0-9]{2}-[a-z0-9-]+\.md$")

    def test_values_are_read(self):
        cfg = self.settings('[start]\nfiles = ["a.md", "./b.md"]\nbudget = 500\ninject = false\n'
                            '[guard]\nmode = "remind"\nbash = false\n[agents]\ninject = "none"\n'
                            '[private]\nfiles = ["docs/start/90-me.md"]\n[naming]\n"docs/x/" = "^a$"\n' + AREAS)
        self.assertEqual(cfg.start.files, ["a.md", "b.md"])
        self.assertEqual((cfg.start.budget, cfg.start.inject), (500, False))
        self.assertEqual((cfg.guard.mode, cfg.guard.bash, cfg.agents.inject), ("remind", False, "none"))
        self.assertEqual(cfg.private, ["docs/start/90-me.md"])
        self.assertEqual(cfg.naming, {"docs/x": "^a$"})
        self.assertEqual([a.name for a in cfg.areas], ["the scrubber", "the policy"])
        self.assertEqual(cfg.areas[0].pack[2], "docs/policy.md")

    def test_bad_files_give_a_plain_sentence(self):
        self.refused("[start\n", "is not valid TOML")
        self.refused("[colour]\n", "the table [colour] is not known")
        self.refused("[start]\nbudjet = 3\n", "the key \"budjet\" in [start] is not known")
        self.refused("[start]\nbudget = 0\n", "[start] budget must be a whole number above 0")
        self.refused("[start]\nbudget = true\n", "[start] budget must be a whole number above 0")
        self.refused("[start]\ninject = 'yes'\n", "[start] inject must be true or false")
        self.refused("[start]\nalso = 'x'\n", "[start] also must be a list")
        self.refused("[guard]\nmode = 'strict'\n", "[guard] mode must be deny, remind or off, not \"strict\"")
        self.refused("[agents]\ninject = 'all'\n", "[agents] inject must be map, start or none")
        self.refused("[start]\ndir = '/abs/docs'\n", "must be relative to the folder of atlasmd.toml")
        self.refused("[start]\ndir = 'C:/docs'\n", "must be relative to the folder of atlasmd.toml")
        self.refused("[start]\ndir = 'docs\\\\start'\n", "must use / as the separator")
        self.refused("[naming]\n\"docs\" = \"([\"\n", "is not a valid regular expression")
        self.refused("[[area]]\npaths = ['a/']\n", "area 1 has no name")
        self.refused("[[area]]\nname = 'a'\n[[area]]\nname = 'a'\n", "two areas have the name \"a\"")
        self.refused("[[area]]\nname = 'a'\nfiles = []\n", "the key \"files\" in area 1 is not known")
        self.refused("[area]\nname = 'a'\n", "[[area]], with two square brackets")
        with self.assertRaises(ConfigError):
            config.load(self.root / "nothing.toml")


class Find(Case):
    def test_find_walks_up_from_a_file_that_does_not_exist(self):
        write(self.root / config.CONFIG_NAME, "")
        found = config.find(self.root / "a" / "b" / "new.py")
        self.assertEqual(found, self.root / config.CONFIG_NAME)
        self.assertEqual(config.find(self.root / "a"), self.root / config.CONFIG_NAME)

    def test_the_nearest_file_wins(self):
        write(self.root / config.CONFIG_NAME, "")
        inner = write(self.root / "sub" / config.CONFIG_NAME, "")
        self.assertEqual(config.find(self.root / "sub" / "x.py"), inner)

    def test_the_project_folder_is_the_last_place(self):
        project = self.root / "project"
        outside = self.root / "outside"
        outside.mkdir()
        self.assertIsNone(config.find(outside))
        write(project / config.CONFIG_NAME, "")
        os.environ["CLAUDE_PROJECT_DIR"] = str(project)
        try:
            self.assertEqual(config.find(outside), project / config.CONFIG_NAME)
        finally:
            del os.environ["CLAUDE_PROJECT_DIR"]


class Personal(unittest.TestCase):
    def test_the_personal_settings(self):
        old = {k: os.environ.pop(k, None) for k in ("CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_OPTION_OFFER_SETUP")}
        try:
            mine = config.personal()
            self.assertTrue(mine["offer_setup"])
            self.assertEqual(mine["data_dir"], pathlib.Path.home() / ".claude" / "plugins" / "data" / "amd")
            self.assertEqual(mine["token_chars"], 2.5)
            os.environ["CLAUDE_PLUGIN_OPTION_OFFER_SETUP"] = "false"
            os.environ["CLAUDE_PLUGIN_DATA"] = "/data/amd"
            mine = config.personal()
            self.assertFalse(mine["offer_setup"])
            self.assertEqual(mine["data_dir"], pathlib.Path("/data/amd"))
            os.environ["CLAUDE_PLUGIN_OPTION_OFFER_SETUP"] = "true"
            self.assertTrue(config.personal()["offer_setup"])
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


class Areas(Case):
    def test_the_longest_prefix_wins(self):
        cfg = self.settings(AREAS)
        self.assertEqual(areas.area_of(cfg, self.root / "services/scrubber/x.py").name, "the scrubber")
        self.assertEqual(areas.area_of(cfg, self.root / "services/scrubber/policy/a.py").name, "the scrubber")
        self.assertEqual(areas.area_of(cfg, self.root / "services/scrubber/policy/strict/a.py").name, "the policy")
        self.assertEqual(areas.area_of(cfg, self.root / "services/scrubber").name, "the scrubber")
        self.assertEqual(areas.area_of(cfg, self.root / "tools/scrub.py").name, "the scrubber")
        self.assertIsNone(areas.area_of(cfg, self.root / "tools/scrub.py.bak"))
        self.assertIsNone(areas.area_of(cfg, self.root / "services/scrubber-old/x.py"))
        self.assertIsNone(areas.area_of(cfg, self.root.parent / "elsewhere.py"))

    def test_the_pack_with_its_anchors(self):
        cfg = self.settings(AREAS)
        self.assertEqual(areas.pack_of(cfg, cfg.areas[0]), [
            (self.root / "services/scrubber/README.md", None),
            (self.root / "docs/product-decisions.md", "P15"),
            (self.root / "docs/policy.md", None),
        ])

    def test_free_paths(self):
        cfg = self.settings('[start]\nalso = ["../other/docs/start/"]\n' + AREAS)
        for free in ("atlasmd.toml", "docs/start/10-map.md", "docs/start/new.md", "docs/start/30-state.md",
                     "services/scrubber/README.md", "docs/product-decisions.md", "../other/docs/start/10-map.md"):
            self.assertTrue(areas.is_free(cfg, self.root / free), free)
        for guarded in ("services/scrubber/x.py", "docs/other.md", "docs/startle.md"):
            self.assertFalse(areas.is_free(cfg, self.root / guarded), guarded)

    def test_rel(self):
        cfg = self.settings("")
        self.assertEqual(areas.rel(cfg, self.root / "a" / "b.md"), "a/b.md")
        self.assertEqual(areas.rel(cfg, self.root.parent / "x.md"), "../x.md")


class StartReading(Case):
    def test_the_files_in_order(self):
        write(self.root / "docs/start/20-b.md")
        write(self.root / "docs/start/10-a.md")
        write(self.root / "docs/start/.hidden.md")
        write(self.root / "docs/start/picture.png")
        write(self.root / "docs/start/sub/30-c.md")
        write(self.root / "../other/docs/start/10-z.md")
        write(self.root / "extra.md")
        cfg = self.settings('[start]\nalso = ["../other/docs/start/", "extra.md", "missing.md", "docs/start/10-a.md"]\n')
        names = [p.name for p in start.files(cfg)]
        self.assertEqual(names, ["10-a.md", "20-b.md", "10-z.md", "extra.md"])

    def test_an_explicit_list_replaces_the_folder(self):
        write(self.root / "docs/start/10-a.md")
        write(self.root / "b.md")
        write(self.root / "a.md")
        cfg = self.settings('[start]\nfiles = ["b.md", "a.md", "gone.md"]\n')
        self.assertEqual([p.name for p in start.files(cfg)], ["b.md", "a.md"])

    def test_compose_measures_the_files(self):
        write(self.root / "docs/start/10-a.md", "a" * 25)
        write(self.root / "docs/start/20-b.md", "b" * 26)
        composed = start.compose(self.settings(""))
        self.assertEqual([n for _, n in composed.files], [10, 11])
        self.assertEqual(composed.tokens, 21)
        self.assertFalse(composed.over_budget)
        self.assertIn("## docs/start/10-a.md\n\n" + "a" * 25, composed.text)
        self.assertTrue(start.compose(self.settings("[start]\nbudget = 20\n")).over_budget)

    def test_no_files_give_no_text(self):
        composed = start.compose(self.settings(""))
        self.assertEqual((composed.text, composed.tokens, composed.files), ("", 0, []))

    def test_estimate_tokens(self):
        self.assertEqual(start.estimate_tokens(""), 0)
        self.assertEqual(start.estimate_tokens("abcde"), 2)
        self.assertEqual(start.estimate_tokens("abcdef"), 3)
        self.assertEqual(start.estimate_tokens("abcd", token_chars=4), 1)


if __name__ == "__main__":
    unittest.main()
