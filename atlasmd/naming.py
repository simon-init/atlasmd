"""The naming check: every Markdown file against the rule of its folder in [naming].

A rule is a regular expression for the file name. It applies to the files of its folder
and of the folders below it. When two rules apply, the rule of the deeper folder wins.
README.md is the index of a folder and needs no other name. The check renames nothing.
"""
import re


def _norm(folder):
    return folder.replace("\\", "/").strip("/")


def rule_for(rules, rel):
    """(folder, pattern) of the rule that applies to the relative path rel, or None."""
    rel = rel.replace("\\", "/")
    best = None
    for folder, pattern in rules.items():
        f = _norm(folder)
        if f and rel.startswith(f + "/"):
            if best is None or len(f) > len(_norm(best[0])):
                best = (folder, pattern)
    return best


def check(rules, paths):
    """The findings for the relative paths: a list of dicts with path, folder, rule, text.
    A rule that is not a valid pattern gives one finding with an empty path."""
    compiled, findings = {}, []
    for folder, pattern in rules.items():
        try:
            compiled[folder] = re.compile(pattern)
        except re.error as exc:
            findings.append({"path": "", "folder": folder, "rule": pattern,
                             "text": f"the rule for {_norm(folder)}/ under [naming] is not a valid regular expression: {exc}"})
    for rel in paths:
        found = rule_for(rules, rel)
        if not found or found[0] not in compiled:
            continue
        folder, pattern = found
        name = rel.replace("\\", "/").rsplit("/", 1)[-1]
        if name == "README.md":
            continue
        if not compiled[folder].fullmatch(name):
            findings.append({"path": rel, "folder": folder, "rule": pattern,
                             "text": f"the file name does not match the rule for {_norm(folder)}/ under [naming]: {pattern}"})
    return findings
