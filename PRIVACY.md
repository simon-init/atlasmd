# Privacy

atlasmd is a set of hooks and a command line that run on your own computer, inside
Claude Code. It has no server, no account and no network access. Nothing leaves the
computer through the plugin.

## What it reads

- The Markdown files of the start reading of a project, to give them to the session at
  its start and after each compaction. When the hook gives their content, that content
  goes into the context of the session. It goes to the model as every file that the
  session reads goes to the model.
- The map of a project, which a subagent gets at its start.
- `atlasmd.toml` of a project, and the paths of the files that a tool call reads or
  changes, to find the area of a file.
- The text of a Bash command, to find the files that it reads or writes.
- The Markdown files of a project, when you run `amd scan`, `amd check` or `amd map`.
  The command line reads them on your computer and prints the result in your terminal.

## What it keeps

All files are under `~/.claude/plugins/data/amd/`, or under the folder that
`CLAUDE_PLUGIN_DATA` names:

- `ledgers/`: one small file per session and per subagent. It holds the paths of the
  files that the session read, on this computer, and the texts of the last refusals.
  The hook removes a ledger after 14 days.
- `compacts.log`: one line per compaction, with the time, the folder of the project,
  the trigger and the size of the summary in characters. It does not hold the summary.
- `settings.toml`: your two settings, `offer_setup` and `token_chars`.
- `seen.json`: the folders where the plugin already offered the setup.
- `log.txt`: the internal errors of the hook, if there are errors.

You own these files. Delete the folder and the plugin forgets everything.

## What it sends

Nothing. The plugin makes no network calls. It contacts no service, no telemetry
endpoint and no update server.

## Changes

When the behavior of the plugin changes, this page changes with it, and the change log
names the version.
