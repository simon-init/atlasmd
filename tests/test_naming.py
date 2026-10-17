"""The naming check against each rule of the convention."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from atlasmd import config, naming  # noqa: E402

RULES = dict(config.DEFAULT_NAMING)


def bad(paths, rules=RULES):
    return [f["path"] for f in naming.check(rules, paths)]


class Naming(unittest.TestCase):
    def test_the_start_folder_wants_two_digits_and_a_subject(self):
        self.assertEqual(bad(["docs/start/10-map.md", "docs/start/40-way-of-work.md"]), [])
        self.assertEqual(bad(["docs/start/map.md", "docs/start/1-map.md", "docs/start/10-Map.md",
                              "docs/start/10_map.md"]),
                         ["docs/start/map.md", "docs/start/1-map.md", "docs/start/10-Map.md", "docs/start/10_map.md"])

    def test_the_decisions_folder_wants_a_number_with_three_digits(self):
        self.assertEqual(bad(["docs/decisions/P008-default-policy.md", "docs/decisions/README.md"]), [])
        self.assertEqual(bad(["docs/decisions/P8-policy.md", "docs/decisions/decision-policy.md",
                              "docs/decisions/p008-policy.md"]),
                         ["docs/decisions/P8-policy.md", "docs/decisions/decision-policy.md",
                          "docs/decisions/p008-policy.md"])

    def test_the_notes_folder_wants_the_date_first(self):
        self.assertEqual(bad(["docs/notes/2026-10-16-gate-run.md"]), [])
        self.assertEqual(bad(["docs/notes/gate-run-2026-10-16.md", "docs/notes/2026-10-gate.md"]),
                         ["docs/notes/gate-run-2026-10-16.md", "docs/notes/2026-10-gate.md"])

    def test_the_plans_folder_wants_a_subject_only(self):
        self.assertEqual(bad(["docs/plans/login.md", "docs/plans/phase-5.md"]), [])
        self.assertEqual(bad(["docs/plans/PHASE-5.md", "docs/plans/plan login.md"]),
                         ["docs/plans/PHASE-5.md", "docs/plans/plan login.md"])

    def test_a_file_outside_every_rule_folder_is_not_examined(self):
        self.assertEqual(bad(["README.md", "docs/MY-PROJECT.md", "docs/archive/Old Name.md",
                              "services/x/README.md"]), [])

    def test_the_rule_applies_below_its_folder_and_the_deeper_rule_wins(self):
        rules = {**RULES, "docs/notes/raw": r"^[a-z]+\.md$"}
        self.assertEqual(bad(["docs/notes/2026/2026-01-02-a.md", "docs/notes/raw/abc.md"], rules), [])
        self.assertEqual(bad(["docs/notes/2026/a.md", "docs/notes/raw/2026-01-02-a.md"], rules),
                         ["docs/notes/2026/a.md", "docs/notes/raw/2026-01-02-a.md"])
        self.assertEqual(naming.rule_for(rules, "docs/notes/raw/x.md")[0], "docs/notes/raw")
        self.assertIsNone(naming.rule_for(rules, "docs/notesbook/x.md"))

    def test_a_rule_that_is_not_a_pattern_gives_one_finding(self):
        found = naming.check({"docs/x": "^[a-"}, ["docs/x/a.md"])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["path"], "")
        self.assertIn("not a valid regular expression", found[0]["text"])


if __name__ == "__main__":
    unittest.main()
