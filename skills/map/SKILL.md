---
name: map
description: Write the tree of every Markdown file and the area table into the map of the start reading
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" map`. It writes the tree of every Markdown file, with the first heading of each, and the table of the areas into the map file that `atlasmd.toml` names under `start.map`. It changes only the text between the marker lines.

Then run `git diff` on the map file and tell the person what changed: the files that came into the tree or left it, and the areas that changed. If nothing changed, say so in one sentence. Commit nothing unless the person asked for a commit.
