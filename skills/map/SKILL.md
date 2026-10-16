---
name: map
description: Run amd map, which writes the list of every Markdown file and the table of the [[area]] entries into the map file in docs/start/
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" map`. It writes the list of every Markdown file, with the first heading of each, and the table of the `[[area]]` entries into the map file that `atlasmd.toml` names under `start.map`, `docs/start/10-map.md` by default. It changes only the text between the marker lines.

Then run `git diff` on the map file and tell the person what changed: the files that came into the list or left it, and the `[[area]]` entries that changed. If nothing changed, say so in one sentence. Commit nothing unless the person asked for a commit.
