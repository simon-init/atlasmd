# Changes

## 0.1.1

2026-10-16.

- The start reading over the limit of a hook gives the content of the first files as far as the limit lets, and the list of the rest.
- A map in another project, as with `[start] also`, is left to that project: `amd check` skips it and `amd map` refuses to write it.
- A project with no start reading of its own and no `also` still gets the finding; one with `also` does not.
- The hook reads the personal settings file that `amd set` writes.

## 0.1.0

2026-10-16

- The start reading: the files of `docs/start/`, in name order, at each session start and after each compaction, within a budget of tokens.
- The list of the start files in place of their content when the content is over the budget, or over the 10,000 characters that Claude Code takes from a hook.
- The guard: no Edit, Write or Bash write in an area until the session read the pack of the area, in the modes `deny` and `remind`.
- The ledger of the files that each session and each subagent read. It starts again after a compaction.
- The map or the start reading for a subagent at its start.
- The compaction log: the time, the folder, the trigger and the size of the summary.
- `atlasmd.toml` with every key and its default.
- The command line `amd`: `setup`, `config`, `scan`, `init`, `check`, `map`, `status`, `why`, `end`, `set` and `version`.
- The guided screen `amd setup` and the settings screen `amd config`.
- The naming check of the Markdown files against the convention, and the report of the files that nothing reads.
- The skills `/amd:init`, `/amd:check`, `/amd:map`, `/amd:status`, `/amd:why` and `/amd:end`.
- Tests on Linux, macOS and Windows.
