# Changes

## 0.1.1

2026-10-16.

- When the files of `docs/start/` are longer than the 10,000 characters that Claude Code takes from a hook, the hook gives the text of the first files as far as the limit lets, and the list of the rest.
- When `start.map` names a file in another project, `amd check` skips that file and `amd map` refuses to write it. That project checks and writes its own map file.
- `amd check` reports a project that has no Markdown files in `docs/start/` and no `start.also`. A project with `start.also` gets no report.
- The hook reads the file of your own settings that `amd set` writes.

## 0.1.0

2026-10-16

- At the start of a session and after each compaction, the hook gives Claude the Markdown files of `docs/start/`, in name order, up to `start.budget` tokens.
- When these files are over `start.budget`, or over the 10,000 characters that Claude Code takes from a hook, the hook gives Claude the list of the files, not their text.
- Before an Edit, a Write or a Bash command that writes a file in the paths of an `[[area]]`, the hook refuses the edit until the session reads the files under `pack`. `guard.mode` is `deny` or `remind`.
- The hook keeps the list of the files that each session and each subagent read. After a compaction, it empties the list of the session.
- At its start, a subagent gets the map file or the files of `docs/start/`.
- After each compaction, the hook writes the date and time, the project folder, whether the compaction was manual or automatic, and the size of the summary to `compacts.log`.
- `atlasmd.toml` with every key and its default.
- The command line `amd`: `setup`, `config`, `scan`, `init`, `check`, `map`, `status`, `why`, `end`, `set` and `version`.
- The screen with five steps, `amd setup`, and the settings screen, `amd config`.
- `amd check` examines the names of the Markdown files against the rule of their folder, and reports the files that no rule tells Claude to read.
- The skills `/amd:init`, `/amd:check`, `/amd:map`, `/amd:status`, `/amd:why` and `/amd:end`.
- Tests on Linux, macOS and Windows.
