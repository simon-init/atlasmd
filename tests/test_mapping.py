"""The map: the blocks between the markers, the tree and the area table."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlasmd import config, mapping  # noqa: E402


def project(base, toml=""):
    root = Path(base)
    (root / "atlasmd.toml").write_text(toml, encoding="utf-8")
    for rel, text in {"README.md": "# Top\n", "docs/start/10-map.md": "# The map\n",
                      "docs/archive/a.md": "# A\n", "docs/archive/b.md": "# B\n",
                      "docs/plans/login.md": "---\ntitle: x\n---\n\n```\n# not a heading\n```\n## The login\n"}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return config.load(root / "atlasmd.toml")


class Blocks(unittest.TestCase):
    def test_put_block_replaces_only_the_text_between_the_markers(self):
        text = "before\n<!-- atlasmd:tree -->\nold\n<!-- /atlasmd:tree -->\nafter\n"
        new, existed = mapping.put_block(text, mapping.TREE, "- `a.md`")
        self.assertTrue(existed)
        self.assertEqual(new, "before\n<!-- atlasmd:tree -->\n- `a.md`\n<!-- /atlasmd:tree -->\nafter\n")
        again, _ = mapping.put_block(new, mapping.TREE, "- `a.md`")
        self.assertEqual(again, new)

    def test_put_block_appends_a_missing_pair(self):
        new, existed = mapping.put_block("# Map", mapping.AREAS, "x")
        self.assertFalse(existed)
        self.assertEqual(new, "# Map\n\n<!-- atlasmd:areas -->\nx\n<!-- /atlasmd:areas -->\n")

    def test_a_closer_without_an_opener_is_a_missing_pair(self):
        self.assertIsNone(mapping.find_block("<!-- /atlasmd:tree -->\n<!-- atlasmd:tree -->", mapping.TREE))


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_the_tree_has_each_path_with_its_heading_and_one_line_for_the_archive(self):
        cfg = project(self.tmp.name)
        tree = mapping.tree_block(cfg.root).splitlines()
        self.assertIn("- `README.md`: Top", tree)
        self.assertIn("- `docs/plans/login.md`: The login", tree)
        self.assertIn("- `docs/archive/`: 2 files of history, never read at a start", tree)
        self.assertFalse(any("a.md" in line for line in tree))

    def test_the_area_table_has_one_row_per_area(self):
        cfg = project(self.tmp.name, '[[area]]\nname = "login"\npaths = ["app/login/"]\n'
                                     'pack = ["docs/plans/login.md", "docs/x.md#P15"]\n')
        table = mapping.areas_block(cfg).splitlines()
        self.assertEqual(table[0], "| Area | Code paths | Pack |")
        self.assertEqual(table[2], "| login | `app/login/` | `docs/plans/login.md`, `docs/x.md#P15` |")
        self.assertIn("No areas yet", mapping.areas_block(project(self.tmp.name)))

    def test_stale_names_the_blocks_that_differ(self):
        cfg = project(self.tmp.name)
        self.assertEqual(mapping.stale(cfg), ["areas", "tree"])
        result = mapping.write(cfg)
        self.assertTrue(result["changed"])
        self.assertEqual(mapping.stale(cfg), [])
        self.assertFalse(mapping.write(cfg)["changed"])
        (Path(self.tmp.name) / "docs/plans/export.md").write_text("# Export\n", encoding="utf-8")
        self.assertEqual(mapping.stale(cfg), ["tree"])


if __name__ == "__main__":
    unittest.main()
