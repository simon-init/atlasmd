---
name: check
description: Run amd check on this project, explain each problem in docs/start/, atlasmd.toml, the file names and the map file, and make the fixes that the person agrees to
---

Check the project in three steps.

1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check --json`. Under `budget`, it gives the tokens of each file that Claude gets at the start of a session, and the total against `start.budget`. Under `findings`, it gives one entry for each problem, with its `kind`:
   - `start`: `docs/start/` has no Markdown files, so Claude gets nothing at the start of a session.
   - `budget`: the files of `docs/start/` have more tokens than `start.budget`.
   - `missing-pack`: a file under `pack` of an `[[area]]` does not exist.
   - `empty-pack`: an `[[area]]` lists no files under `pack`, so the hook refuses no edit in its paths.
   - `overlap`: the paths of two `[[area]]` entries overlap.
   - `naming`: a file name does not match the rule of its folder under `[naming]`.
   - `unread`: a Markdown file is not in `docs/start/`, not under `pack`, and not in a folder under `[naming]`, so no rule says when Claude reads it.
   - `map`: the map file in `start.map` does not exist or is out of date.

2. Tell the person each problem in plain words, one line each, with the fix you propose for it. For a name, propose the new name under the rule of its folder. For a file that no rule tells Claude to read, propose to add it under `pack` of an `[[area]]`, to move it into a folder under `[naming]`, or to move it into `docs/archive/`. For a map file that is out of date, the fix is `"${CLAUDE_PLUGIN_ROOT}/bin/amd" map`. Ask once which fixes to make.

3. Make the fixes that the person agrees to. Use `git mv` for a rename or a move, and update every link that it breaks. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check` again and report what is left. Commit nothing unless the person asked for a commit.
