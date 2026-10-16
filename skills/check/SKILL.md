---
name: check
description: Check the Markdown of this project against atlasmd, the budget of the start reading, the packs, the names and the map, and fix what it finds
---

Check the project in three steps.

1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check --json`. It lists the budget of the start reading with the tokens of each file, and one finding for each problem: a pack file that does not exist, an area with an empty pack, two areas whose paths overlap, a file name against the rule of its folder, a Markdown file that nothing reads, and a map that differs from the project.

2. Tell the person each finding in plain words, one line each, with the fix you propose for it. For a name, propose the new name under the rule of its folder. For a file that nothing reads, propose a pack, a folder, or `docs/archive/`. For a stale map, the fix is `"${CLAUDE_PLUGIN_ROOT}/bin/amd" map`. Ask once which fixes to apply.

3. Apply the fixes that the person agrees to. Use `git mv` for a rename or a move, and update every link that it breaks. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check` again and report what is left. Commit nothing unless the person asked for a commit.
