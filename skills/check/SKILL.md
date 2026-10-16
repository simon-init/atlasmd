---
name: check
description: Run amd check on this project, explain each problem in docs/start/, atlasmd.toml, the file names, the map file, the folders without a README.md or an [[area]] entry, the plans and notes that nothing names, and the decisions without a line in the index. Make the fixes that the person agrees to
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
   - `no-readme`: a folder holds source files and has no README.md, in it or in a folder above it.
   - `no-entry`: a folder holds source files that the paths of no `[[area]]` entry hold.
   - `dead-entry`: an `[[area]]` entry lists a path under `paths` that does not exist.
   - `stale-readme`: a README.md under `pack` did not change in the last commits that changed its folder. `stale_readme` under `[check]` gives the number.
   - `dead-pointer`: `docs/start/20-open-items.md` names a path in backticks that does not exist.
   - `orphan-plan`: no line of `docs/start/20-open-items.md` names a file of `docs/plans/`.
   - `orphan-note`: no Markdown file names a note of `docs/notes/`, and the note is older than `notes` days under `[check]`.
   - `no-index-line`: `docs/decisions/README.md` has no line for a file of `docs/decisions/`.
   - `stale-state`: the file in `start.state` did not change in the last commits. `stale_state` under `[check]` gives the number.

   Each key under `[check]` in `atlasmd.toml` turns its findings off with `false` or `0`.

2. Tell the person each problem in plain words, one line each, with the fix you propose for it. For a name, propose the new name under the rule of its folder. For a file that no rule tells Claude to read, propose to add it under `pack` of an `[[area]]`, to move it into a folder under `[naming]`, or to move it into `docs/archive/`. For a map file that is out of date, the fix is `"${CLAUDE_PLUGIN_ROOT}/bin/amd" map`. For a finding of the kinds `no-readme` to `stale-state`, the fix is in the sentence of its `text`: for a folder, `/amd:area <folder>`. For a built plan or a replaced note, the fix is a move to `docs/archive/` with `git mv`. Ask once which fixes to make.

3. Make the fixes that the person agrees to. Use `git mv` for a rename or a move, and update every link that it breaks. Then run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check` again and report what is left. Commit nothing unless the person asked for a commit.
