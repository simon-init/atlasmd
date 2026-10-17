---
name: end
description: End the session. Move the built plans and the replaced notes to docs/archive/ as amd check says, write the file in start.state again, commit and push, and give the first message for a fresh chat
---

End the session in four steps.

1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check --json`. For each finding of the kinds `orphan-plan`, `orphan-note`, `dead-pointer`, `no-index-line`, `stale-readme` and `no-readme`, do what its `text` says:
   - `orphan-plan`: if the work of the plan is built, move the plan to `docs/archive/` with `git mv`. If the work is open, add a line for it to `docs/start/20-open-items.md`.
   - `orphan-note`: if a newer note replaces the note, move the note to `docs/archive/` with `git mv`. If the note is still current, add its path to the file that needs it.
   - `dead-pointer`: correct the path in the line of `docs/start/20-open-items.md`. If the item of the line is closed, remove the line.
   - `no-index-line`: add the line of the decision to `docs/decisions/README.md`.
   - `stale-readme`: read the commits of the folder since the README last changed, with `git log --oneline`, and update the State section of the README.
   - `no-readme`: write the README.md of the folder, or run `/atlasmd:area <folder>`.

   The plugin deletes no file. A file that leaves goes to `docs/archive/` with `git mv`, and git keeps every version. Keep a list of what you moved and what you changed, and of what you left, with the reason for each.

2. Write again the file that `atlasmd.toml` names under `start.state`, `docs/start/30-state.md` by default: what was done since the last `/atlasmd:end`, what the person must look at, what waits on a person, and what comes next. Write each as short lines, with the path of the file that holds the details. Keep the file under 12,000 characters. Move out of it what is no longer current. Then update `docs/start/20-open-items.md` the same way.

3. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check`, fix what it reports, and commit the changed files by name. Push, unless the rules of the project say when a push must wait. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" end`: it shows what is not committed or not pushed.

4. Tell the person what moved to `docs/archive/`, what changed, and what you left and why, from the list of step 1. Then give the first message for a fresh chat, in a code block, with the path of the file in `start.state` beside it. The message is `start.line` of `atlasmd.toml`. The fresh chat gets the files of `docs/start/` from the hook, so the message asks for nothing else.
