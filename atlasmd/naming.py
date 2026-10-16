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


# --- the rule in words, for the refusal of the hook -------------------------------------------------

# Each rule of the convention, with a name that it matches, names that it does not match, and its words.
SHAPES = [
    ("subject", "a-subject.md", ("A Subject.md",),
     "with the subject in lower case with hyphens"),
    ("number", "10-a-subject.md", ("a-subject.md", "1-a-subject.md"),
     "with two digits, a hyphen and the subject in lower case with hyphens"),
    ("decision", "P012-a-subject.md", ("a-subject.md", "P12-a-subject.md"),
     "with P, three digits, a hyphen and the subject in lower case with hyphens"),
    ("date", "2026-10-16-a-subject.md", ("a-subject.md", "10-a-subject.md"),
     "with the date as YYYY-MM-DD, a hyphen and the subject in lower case with hyphens"),
]


def shape(pattern):
    """The rule of the convention that the pattern behaves as, or None."""
    try:
        rule = re.compile(pattern)
    except re.error:
        return None
    for kind, good, bads, _words in SHAPES:
        if rule.fullmatch(good) and not any(rule.fullmatch(b) for b in bads):
            return kind
    return None


def subject(name):
    """The subject of a file name: lower case, hyphens, without the date, the number and .md."""
    stem = re.sub(r"\.md$", "", name, flags=re.IGNORECASE)
    stem = re.sub(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[-_ ]*", "", stem)
    stem = re.sub(r"^[Pp]?[0-9]+[-_ ]+", "", stem)
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "subject"


def example(pattern, name, siblings, today):
    """A name under the rule for the file name, with the next free number. None for a rule outside the convention:
    then the first sibling that matches the rule, or None."""
    kind, words = shape(pattern), subject(name)
    if kind == "subject":
        return f"{words}.md"
    if kind == "number":
        used = [int(m.group(1)) for s in siblings if (m := re.match(r"^([0-9]{2})-", s))]
        return f"{min(max(used, default=0) + 10, 99):02d}-{words}.md"
    if kind == "decision":
        used = [int(m.group(1)) for s in siblings if (m := re.match(r"^P([0-9]{3})-", s))]
        return f"P{max(used, default=0) + 1:03d}-{words}.md"
    if kind == "date":
        return f"{today.isoformat()}-{words}.md"
    try:
        rule = re.compile(pattern)
    except re.error:
        return None
    return next((s for s in sorted(siblings) if s != "README.md" and rule.fullmatch(s)), None)


def refusal(rules, rel, siblings, today):
    """The sentence that refuses a new Markdown file whose name breaks the rule of its folder, or None."""
    found = rule_for(rules, rel)
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    if not found or name == "README.md":
        return None
    folder, pattern = found
    try:
        if re.compile(pattern).fullmatch(name):
            return None
    except re.error:
        return None
    kind = shape(pattern)
    words = next(w for k, _g, _b, w in SHAPES if k == kind) if kind else f"to match the regular expression {pattern}"
    good = example(pattern, name, siblings, today)
    instance = f", for example {good}" if good else ""
    return (f"atlasmd: {_norm(folder)}/ names its files {words}{instance}. {name} breaks that rule. "
            "Name the file so, then write it again.")
