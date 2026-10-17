"""amd scan: what /atlasmd:init needs to know about a project before it proposes a setup.

It lists every Markdown file with its size and its estimated tokens, the folders that
hold source files and a README (the area candidates), whether atlasmd.toml and
docs/start/ exist, and the files that CLAUDE.md names.
"""
import os
import re
import subprocess
from pathlib import Path

SOURCE_EXT = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".go",
    ".rs", ".java", ".kt", ".kts", ".scala", ".rb", ".php", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".cs", ".fs", ".swift", ".m", ".mm", ".dart", ".ex", ".exs", ".erl", ".clj",
    ".lua", ".r", ".jl", ".zig", ".nim", ".hs", ".ml", ".sh", ".bash", ".ps1", ".sql",
    ".css", ".scss", ".html",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "target"}
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
NAMED_MD = re.compile(r"(?<![\w/.-])@?((?:\.{1,2}/|~/)?[\w][\w./-]*\.md)\b")


def git(root, *args):
    """The output of a git command in root, or None when git fails or is missing."""
    try:
        out = subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def git_root(path):
    out = git(path, "rev-parse", "--show-toplevel")
    return Path(out.strip()) if out and out.strip() else None


def _walk(root):
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in filenames:
            yield (Path(dirpath) / name).relative_to(root).as_posix()


def all_files(root):
    """Every file git tracks, plus the new files git does not ignore, as sorted relative
    POSIX paths. Outside a git repository: every file below root, without hidden folders."""
    root = Path(root)
    out = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if out is None:
        return sorted(_walk(root))
    names = {n for n in out.split("\0") if n}
    return sorted(n for n in names if (root / n).is_file())


def markdown_files(root, files=None):
    return [f for f in (all_files(root) if files is None else files) if f.lower().endswith(".md")]


def read_text(path, limit=None):
    try:
        with open(path, "rb") as fh:
            data = fh.read() if limit is None else fh.read(limit)
    except OSError:
        return ""
    return data.decode("utf-8", "replace")


def first_heading(path):
    """The text of the first heading of a Markdown file, after front matter, outside code."""
    lines = read_text(path, 65536).splitlines()
    i, fence = 0, None
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                i = j + 1
                break
    for line in lines[i:]:
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            fence = None if fence and stripped.startswith(fence) else (fence or stripped[:3])
            continue
        if fence:
            continue
        m = HEADING.match(line)
        if m and m.group(1):
            return m.group(1)
    return ""


def estimate(text):
    from atlasmd import config, start
    return start.estimate_tokens(text, config.personal()["token_chars"])


def file_entry(root, rel):
    path = Path(root) / rel
    text = read_text(path)
    size = path.stat().st_size if path.exists() else 0
    return {"path": rel, "kb": round(size / 1024, 1), "tokens": estimate(text), "heading": first_heading(path)}


def area_candidates(root, files):
    """Folders below the root that hold a README.md and source files, in them or below."""
    readmes = {}
    for f in files:
        parent, _, name = f.rpartition("/")
        if parent and name.lower() == "readme.md":
            readmes[parent] = f
    out = []
    for folder in sorted(readmes):
        prefix = folder + "/"
        count = sum(1 for f in files if f.startswith(prefix) and Path(f).suffix.lower() in SOURCE_EXT)
        if count:
            out.append({"path": prefix, "readme": readmes[folder], "source_files": count,
                        "heading": first_heading(Path(root) / readmes[folder])})
    return out


def folders_without_readme(files):
    """Folders below the root that hold source files and no README.md in them or in a folder above them, the top
    folders only, as amd check reports them."""
    from atlasmd import upkeep  # upkeep imports scan, so the import stays here
    out = []
    for folder in upkeep.no_readme(files):
        prefix = folder + "/"
        count = sum(1 for f in files if f.startswith(prefix) and Path(f).suffix.lower() in SOURCE_EXT)
        out.append({"path": prefix, "source_files": count})
    return out


def claude_md(root):
    """The Markdown files that CLAUDE.md at the root names, with whether each exists."""
    path = Path(root) / "CLAUDE.md"
    if not path.is_file():
        return None
    seen, names = set(), []
    for m in NAMED_MD.finditer(read_text(path)):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        target = Path(os.path.expanduser(name)) if name.startswith("~/") else (Path(root) / name)
        names.append({"name": name, "exists": target.is_file()})
    return {"path": "CLAUDE.md", "names": names}


def scan(root):
    root = Path(root)
    files = all_files(root)
    md = [file_entry(root, f) for f in markdown_files(root, files)]
    return {
        "root": str(root),
        "config": (root / "atlasmd.toml").is_file(),
        "start_dir": (root / "docs" / "start").is_dir(),
        "files": md,
        "total": {"files": len(md), "kb": round(sum(f["kb"] for f in md), 1),
                  "tokens": sum(f["tokens"] for f in md)},
        "candidates": area_candidates(root, files),
        "without_readme": folders_without_readme(files),
        "claude_md": claude_md(root),
    }


def tree_rows(entries):
    """[(indented name, entry or None)] for a list of entries with a path, as a tree."""
    rows, shown = [], set()
    for e in entries:
        parts = e["path"].split("/")
        for depth in range(len(parts) - 1):
            folder = "/".join(parts[:depth + 1])
            if folder not in shown:
                shown.add(folder)
                rows.append(("  " * depth + parts[depth] + "/", None))
        rows.append(("  " * (len(parts) - 1) + parts[-1], e))
    return rows


def number(n):
    return f"{n:,}"


def render(data):
    lines = [f"Project  {data['root']}", ""]
    lines.append(f"atlasmd.toml  {'exists' if data['config'] else 'does not exist'}")
    lines.append(f"docs/start/   {'exists' if data['start_dir'] else 'does not exist'}")
    lines.append("")
    t = data["total"]
    lines.append(f"Markdown files  {t['files']} files, {t['kb']} KB, about {number(t['tokens'])} tokens")
    lines.append("")
    rows = tree_rows(data["files"])
    if rows:
        width = max(len(name) for name, _ in rows)
        kbw = max([len("KB")] + [len(f"{e['kb']}") for _, e in rows if e])
        tkw = max([len("tokens")] + [len(number(e["tokens"])) for _, e in rows if e])
        lines.append(f"  {'file':<{width}}  {'KB':>{kbw}}  {'tokens':>{tkw}}")
        for name, e in rows:
            if e:
                lines.append(f"  {name:<{width}}  {e['kb']:>{kbw}}  {number(e['tokens']):>{tkw}}")
            else:
                lines.append(f"  {name}")
    lines.append("")
    lines.append(f"Folders with source files and a README  {len(data['candidates'])}. "
                 "/atlasmd:init can list each one as an [[area]] in atlasmd.toml")
    if data["candidates"]:
        width = max(len(c["path"]) for c in data["candidates"])
        lines.append("")
        for c in data["candidates"]:
            lines.append(f"  {c['path']:<{width}}  {c['source_files']:>4} source file{'s' if c['source_files'] != 1 else ' '}  {c['heading']}".rstrip())
    lines.append("")
    lines.append(f"Folders with source files and no README  {len(data['without_readme'])}. "
                 "/atlasmd:init writes a README for each one and lists it as an [[area]]")
    if data["without_readme"]:
        width = max(len(c["path"]) for c in data["without_readme"])
        lines.append("")
        for c in data["without_readme"]:
            lines.append(f"  {c['path']:<{width}}  {c['source_files']:>4} source file{'s' if c['source_files'] != 1 else ''}")
    cm = data["claude_md"]
    lines.append("")
    if cm is None:
        lines.append("CLAUDE.md  does not exist")
    else:
        lines.append(f"CLAUDE.md  names {len(cm['names'])} Markdown files")
        for n in cm["names"]:
            lines.append(f"  {'✓' if n['exists'] else '✗'} {n['name']}" + ("" if n["exists"] else "  does not exist"))
    return "\n".join(lines)
