# Changes

## 0.3.0

2026-10-16.

- The new top-level key `group` in `atlasmd.toml`. `amd init` writes it as a comment. Repositories with the same group name share their `docs/start/` at the start of a session.
- atlasmd keeps the list of the repositories that it knows in `projects.toml` in its data folder. `amd init` and `amd config` add the repository where they run, and the hook adds or refreshes it at every session start. An entry whose folder does not exist leaves the list at the next write.
- At a session start in a repository with a group, Claude gets the files of this repository first. Then Claude gets the files of `start.dir` or `start.files` of each other repository of the group, in the order of their names, each file once. The first line names the group and the number of the other repositories.
- `amd check` prints one line for the group: the repositories that it found, or that the group has no other repository on this machine. Its list of the files at the start shows the files of the group with their paths from the repository.
- `amd config` has three stations: Repositories, the settings of one repository, and Files. On Repositories, `g`, `m`, `i` and `b` change the group, `guard.mode`, `start.inject` and `start.budget` of a row. On Files, `p` adds a Markdown file to `[private] files` and to `.git/info/exclude`, or removes it from both.
- `amd config --list`, `amd config --set <path> <key> <value>` and `amd config --json`. A write changes the key in its place. It uncomments a key that stands as a comment, and it adds a missing key at the end of its table. Every other line and comment stays.
- The meter: at every hook event, the hook reads the new lines of the transcript of the session. It writes one record per session in `meter/` of its data folder. The record holds the four token counts, the requests, the tokens up to the first Edit or Write, the compaction cycles and the model.
- `amd meter` shows the newest session of a repository with two bars, and the history of its sessions. Enter on two rows, or `c` on one row, shows the comparison: off, on, the difference and the percent saved. `--list`, `--compare` and `--json` print the same without the screen.
- `amd statusline` prints one line for the status line of Claude Code: on or off, the start tokens, the session tokens and the compactions.
- `ATLASMD=off claude` starts a session where the hook gives nothing, refuses nothing and reminds of nothing. The meter records the session, marked off.
- The data folder of atlasmd is always `~/.claude/plugins/data/amd/`, or the folder in `ATLASMD_DATA`. Before, the hook used `CLAUDE_PLUGIN_DATA`, which Claude Code sets to `~/.claude/plugins/data/amd-atlasmd/` for the hook only. So the command line, the status line and a Bash command read another folder than the hook wrote.
- The first line of the files at the start, and the warning over the budget, show the tokens with thousands separators.

## 0.2.0

2026-10-16.

- `amd init` writes the section "How the Markdown files live", with eight rules, into `docs/start/40-way-of-work.md`. It still overwrites no file.
- `amd check` reports a folder with source files and no README.md (`no-readme`), and a folder with source files that no `[[area]]` entry lists (`no-entry`).
- `amd check` reports a path under `paths` of an `[[area]]` entry that does not exist (`dead-entry`).
- `amd check` reports a README.md under `pack` that did not change in the last 15 commits that changed its folder (`stale-readme`).
- `amd check` reports a path in backticks in `docs/start/20-open-items.md` that does not exist (`dead-pointer`).
- `amd check` reports a file in `docs/plans/` that no line of `docs/start/20-open-items.md` names (`orphan-plan`).
- `amd check` reports a note in `docs/notes/` that no Markdown file names and that is older than 30 days (`orphan-note`).
- `amd check` reports a file in `docs/decisions/` without a line in `docs/decisions/README.md` (`no-index-line`).
- `amd check` reports the file in `start.state` when it did not change in the last 20 commits (`stale-state`).
- `amd check` gives these nine findings under two headings, `growth` and `cleaning`, with one line for each check that finds nothing. `--json` gives them with their `kind` and `path`.
- The new table `[check]` in `atlasmd.toml` has a key for each of these checks. `false` or `0` turns a check off. `amd init` writes the table with a comment on each key.
- The new key `start.items` names the file of the open items, `docs/start/20-open-items.md` by default. The hook never refuses an edit of it.
- The hook refuses a Write of a new Markdown file whose name breaks the rule of its folder under `[naming]`. The refusal gives the rule in words and an example name. An Edit of a file that exists is never refused for its name.
- The new key `guard.new_folders`, `remind` by default: when Claude writes a new source file in a folder that no `[[area]]` entry lists, the hook tells Claude once in the session to write the README.md and the entry.
- `/amd:end` runs `amd check --json` first, moves the built plans and the replaced notes to `docs/archive/` with `git mv`, corrects the open items, the index and the State sections, and tells the person what moved and what it left.
- The command `amd area <folder>` and the skill `/amd:area` write the README.md of a folder from a template, add its `[[area]]` entry at the end of `atlasmd.toml`, and write the map file.
- The README gives the eight rules, the keys under `[check]`, `start.items`, `guard.new_folders`, the nine findings, the refusal of a new file and `amd area`. Its example of an `[[area]]` entry, and the example in `atlasmd.toml`, use the folder `api/`.

## 0.1.2

2026-10-16.

- Every text that a person reads says what atlasmd does: the file, the folder, the key of `atlasmd.toml` and the log, never a word coined for a concept. Simon's rule of the same day.
- The refusal names the entry of `atlasmd.toml` whose files are missing, so `amd status` finds it again.

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
