# Privacy

atlasmd is a set of hooks and a command line that run on your own computer, inside
Claude Code. It has no server, no account and no network access. The one thing that
leaves the computer is a `git push` that the skill `/atlasmd:end` tells Claude to run.

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
- Before a Write of a new file, the names of the files in its folder, to give the next
  free number in the example of a refusal, and the folders above it, to find the first
  new folder.
- The Markdown files of a project, when you run `amd scan`, `amd check` or `amd map`.
  The command line reads them on your computer and prints the result in your terminal.
- The git log of a project, when you run `amd check`: the last commit of a README.md,
  of a note and of the file in `start.state`, and the number of commits after it.
- The transcript of a session, the JSONL file that Claude Code writes under
  `~/.claude/projects/`, at every hook event and when you run `amd meter` or
  `amd statusline`. The meter reads only the lines that the file got after the last
  read. From these lines it takes the token counts, the model, the compaction lines and
  the names of the tools. It does not keep the text of a message.
- `atlasmd.toml` of every repository of the list, at a session start in a repository with
  a group and when you run `amd config`. With a group, the files of `docs/start/` of the
  other repositories go into the context of the session. They go there as the files of
  the repository itself do.
- The JSON that Claude Code gives a status line command, when you use `amd statusline`.
  It takes the session id, the transcript path and the size of the context window.

## What it keeps

All files are under `~/.claude/plugins/data/amd/`, or under the folder that
`ATLASMD_DATA` names:

- `ledgers/`: one small file for each session and each subagent. It holds the paths of
  the files that the session read on this computer, the text of the last 10 refused
  edits, and the folders without an `[[area]]` entry that the hook named to Claude. The
  hook removes a file after 14 days.
- `compacts.log`: one line for each compaction, with the date and time, the project
  folder, whether the compaction was manual or automatic, and the size of the summary
  in characters. It does not hold the summary.
- `settings.toml`: your two settings, `offer_setup` and `token_chars`.
- `seen.json`: the project folders where the hook already told Claude about
  `/atlasmd:init`.
- `projects.toml`: the list of the repositories that atlasmd knows, with the path, the
  name of the folder, the group and the time of the last session start there.
- `meter/`: one small file for each session in a repository with `atlasmd.toml`. It
  holds no text of the session, only token counts and times. These are the repository
  and its group, whether atlasmd was on, the time of the first request and the model.
  Then the four token counts, the number of requests, the tokens up to the first Edit
  or Write, and the counts of each compaction cycle. Last, the byte offset of the last
  read and the ids of the last few requests. The plugin does not remove these files.
- `log.txt`: the internal errors of the hook, if there are errors.

You own these files. To remove all of them, delete the folder.

`amd setup` makes one more file, outside that folder, only when you pick "Put amd on my PATH
now": the link `~/.local/bin/amd` to `bin/amd` of the plugin, and the folder `~/.local/bin`
when it is missing. The link holds no data.

## What it sends

The hook and the `amd` command make no network calls. They contact no service, no
telemetry endpoint and no update server.

The skill `/atlasmd:end`, when you type it, tells Claude to commit the changed files and
to run `git push`. The push sends those commits to the remote that your repository already
has, the same place that a push without the plugin sends them. The skill skips the push
when the rules of your project say that a push must wait. No other skill sends data.

## Changes

When the behavior of the plugin changes, this page changes with it, and `CHANGELOG.md`
names the version.
