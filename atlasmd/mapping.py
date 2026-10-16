"""amd map: the tree of every Markdown file and the area table, written into the map.

The map file is start.map of atlasmd.toml. Each block stands between two marker lines.
The text outside the markers stays as it is. When a pair of markers is missing, the
pair goes to the end of the file.
"""
from pathlib import Path

from atlasmd import scan

TREE = ("<!-- atlasmd:tree -->", "<!-- /atlasmd:tree -->")
AREAS = ("<!-- atlasmd:areas -->", "<!-- /atlasmd:areas -->")
ARCHIVE = "docs/archive/"


def _cell(text):
    return str(text).replace("|", "\\|")


def tree_block(root, files=None):
    """One line per Markdown file: the path and its first heading. The archive is one line."""
    root = Path(root)
    md = scan.markdown_files(root, files)
    archived = [f for f in md if f.startswith(ARCHIVE)]
    lines = []
    for rel in md:
        if rel.startswith(ARCHIVE):
            continue
        heading = scan.first_heading(root / rel)
        lines.append(f"- `{rel}`: {heading}" if heading else f"- `{rel}`")
    if archived:
        lines.append(f"- `{ARCHIVE}`: {len(archived)} old files, kept for history. Claude does not get them at the start")
    return "\n".join(lines) if lines else "- no Markdown files yet"


def areas_block(cfg):
    if not cfg.areas:
        return ("`atlasmd.toml` lists no folders yet. Each `[[area]]` entry in it names folders, and the files "
                "to read before a change there.")
    rows = ["| Name | Folders and files | Read before a change there |", "|---|---|---|"]
    for a in cfg.areas:
        paths = ", ".join(f"`{_cell(p)}`" for p in a.paths)
        pack = ", ".join(f"`{_cell(p)}`" for p in a.pack)
        rows.append(f"| {_cell(a.name)} | {paths} | {pack} |")
    return "\n".join(rows)


def find_block(text, markers):
    """(start, end) of the text between the markers, or None when the pair is missing."""
    opener, closer = markers
    a = text.find(opener)
    if a < 0:
        return None
    b = text.find(closer, a + len(opener))
    if b < 0:
        return None
    return a + len(opener), b


def current(text, markers):
    span = find_block(text, markers)
    return None if span is None else text[span[0]:span[1]].strip("\n")


def put_block(text, markers, body):
    """The text with body between the markers. Returns (new text, whether the markers existed)."""
    span = find_block(text, markers)
    if span is not None:
        return text[:span[0]] + "\n" + body + "\n" + text[span[1]:], True
    if text and not text.endswith("\n"):
        text += "\n"
    sep = "\n" if text else ""
    return text + sep + markers[0] + "\n" + body + "\n" + markers[1] + "\n", False


def map_path(cfg):
    return Path(cfg.root) / cfg.start.map


def write(cfg, files=None):
    """Write both blocks into the map file. Returns a dict: path, changed, added."""
    path = map_path(cfg)
    old = scan.read_text(path) if path.exists() else ""
    text, added = old, []
    for markers, body in ((AREAS, areas_block(cfg)), (TREE, tree_block(cfg.root, files))):
        text, existed = put_block(text, markers, body)
        if not existed:
            added.append(markers[0])
    changed = text != old
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return {"path": str(path), "changed": changed, "added": added}


def stale(cfg, files=None):
    """The names of the blocks in the map that differ from the project now: tree, areas."""
    path = map_path(cfg)
    text = scan.read_text(path) if path.exists() else ""
    out = []
    for name, markers, body in (("areas", AREAS, areas_block(cfg)), ("tree", TREE, tree_block(cfg.root, files))):
        if current(text, markers) != body:
            out.append(name)
    return out
