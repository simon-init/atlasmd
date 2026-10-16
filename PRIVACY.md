# Privacy

atlasmd is a set of hooks and a command line that run on your own computer, inside
Claude Code. It has no server, no account and no network access. Nothing leaves the
computer through the plugin.

## What it reads

- The Markdown files in `docs/start/` of a project, or the files that `start.files`
  and `start.also` name, to give them to Claude at the start of a session and after
  each compaction. When the hook gives their text, that text goes into the context of
  the session. It goes to the model as every file that the session reads goes to the
  model.
- The map file of a project, `docs/start/10-map.md` by default, which a subagent gets
  at its start.
- `atlasmd.toml` of a project, and the paths of the files that a tool call reads or
  changes, to find the `[[area]]` whose paths hold a file.
- The text of a Bash command, to find the files that it reads or writes.
- The Markdown files of a project, when you run `amd scan`, `amd check` or `amd map`.
  The command line reads them on your computer and prints the result in your terminal.

## What it keeps

All files are under `~/.claude/plugins/data/amd/`, or under the folder that
`CLAUDE_PLUGIN_DATA` names:

- `ledgers/`: one small file for each session and each subagent. It holds the paths of
  the files that the session read on this computer, and the text of the last 10 refused
  edits. The hook removes a file after 14 days.
- `compacts.log`: one line for each compaction, with the date and time, the project
  folder, whether the compaction was manual or automatic, and the size of the summary
  in characters. It does not hold the summary.
- `settings.toml`: your two settings, `offer_setup` and `token_chars`.
- `seen.json`: the project folders where the hook already told Claude about
  `/amd:init`.
- `log.txt`: the internal errors of the hook, if there are errors.

You own these files. To remove all of them, delete the folder.

## What it sends

Nothing. The plugin makes no network calls. It contacts no service, no telemetry
endpoint and no update server.

## Changes

When the behavior of the plugin changes, this page changes with it, and `CHANGELOG.md`
names the version.
