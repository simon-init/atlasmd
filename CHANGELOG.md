# Changes

## 0.4.0

2026-10-17. Simon: the plugin is named atlasmd, and amd is the command in the terminal.

- The plugin's name is `atlasmd`, in `plugin.json` and in the marketplace. The install is `claude plugin install atlasmd@atlasmd`, and the skills are `/atlasmd:init`, `/atlasmd:area`, `/atlasmd:check`, `/atlasmd:map`, `/atlasmd:status`, `/atlasmd:why` and `/atlasmd:end`. The command in the terminal stays `amd`, and the files of the plugin stay in `~/.claude/plugins/data/amd/`. The marketplace maps the old name `amd` to `atlasmd`, so an install under the old name follows.
- The tests pass on Windows. Four tests compared paths in the POSIX form with the paths of the platform, and one wrote a transcript with the line ends of the platform. The code did not change.
- The workflow uses the actions that run on Node 24.

## 0.3.6

2026-10-17. Simon: `/amd:init` must cover every code folder at once, not wait for an edit there.

- `/amd:init` proposes an `[[area]]` entry for every folder that holds code, with a README or without one, so that every source file is under the paths of an entry. After the yes, Claude writes the README of each code folder that has none, from its files. The reminder of the hook stays for a folder that comes later.
- `amd scan` lists the code folders without a README, in the text and as `without_readme` in the JSON.

## 0.3.5

2026-10-17. Simon: a removal from `amd config` must remove atlasmd from the repository, and the plugin needs a logo and the notes for the directory.

- `r` on a repository in `amd config`, and `amd config --remove <path>`, remove atlasmd from that repository: they delete its `atlasmd.toml`, so the hook gives no start files and refuses nothing there, drop its row from the table of repositories, and stop the offer of `/amd:init` there. Every other file stays. The question before the deletion names the file. When git tracks the file, the message says that `git restore atlasmd.toml` brings it back. A repository whose `atlasmd.toml` is gone already leaves the table only.
- The logo: a page with a route on it, in `assets/`, as SVG and PNG. The README shows it.
- `SUBMISSION.md`: what must be true before a submission to Anthropic's directory, the steps in the portal, the answers to the data questions, and the risk of the name `amd`.
- The README has the section "What it runs, reads and keeps".

## 0.3.4

2026-10-17. Simon: a way back after `amd init` in the wrong folder, and who does what.

- `amd init --undo` removes what `amd init` made, the five files and the empty folders, while none of them changed. One changed file stops it, and the message names the file. `--dry-run` shows what it removes. The last line of `amd init` names the undo.
- The README has the section "What happens by itself, and what you do": what the hook does at every session without a command, what Claude does in a session because the rules say so, what happens only when you ask, and what atlasmd never does. It says that nothing sorts the existing Markdown files by itself: `/amd:init` proposes the moves, also after `amd init`.

## 0.3.3

2026-10-17. Simon: the README was far too long, and `amd area` on the repository itself gave a confusing message.

- The README is a fifth of its size. The reason first, then what atlasmd does, the install, the three ways to set up a repository, each command with its output, and one table for the files, one for `atlasmd.toml` and one for the commands.
- `amd area` on the root of the repository, or on a folder that does not exist, says that it takes a folder of the repository that holds code, for example `amd area api`. The README has a section "Add a code folder" with the output.
- The output of `amd area` and `amd why` says "the tree of the Markdown files" and "the records of read files", not "the list".

## 0.3.2

2026-10-17. The README and the texts of the setup say what each thing is before they name it.

- The README starts with why a project keeps what Claude must know in Markdown files, and what a compaction is. Every command comes after the sentences that say what it does, so that the reader can decide before the command. The install, the command `amd` in a terminal and the setup of a repository each give their three ways. The sentence on the limit of 10,000 characters says what Claude gets: the full text of the first files, then the names of the files that did not fit.
- No text that a person reads says "the list" without its thing: the names of the files that did not fit, the record of the files that a session read in `~/.claude/plugins/data/amd/ledgers/`, the table of repositories in `projects.toml`, the tree of the Markdown files in the map file.
- The welcome of `amd setup` gives the reason first, and says what a hook and a compaction are. The step "You" says what a token is. The About station of `amd config` starts with the reason.

## 0.3.1

2026-10-17. Simon's corrections of the config, the setup and the words.

- The table of `amd config` shows the start files that a session in each repository gets, and their tokens: `4` for its own files, `4 from group` or `4 from also` when they come from the group or from `start.also`, and `2 + 3 from group` for both. A repository whose sessions get nothing shows `0`, and a sentence under the table says that a session there gets nothing at the start.
- The table sorts by the name of the group, with the repositories without a group last, and by name inside a group. A new group on a row moves the row to its group at once.
- The setup has the station "The command amd" before "You". "Put amd on my PATH now" makes `~/.local/bin` when it is missing and the link `~/.local/bin/amd` to `bin/amd` of the plugin, then says whether `~/.local/bin` is on the PATH and gives the line for the start file of fish, zsh or bash. "Not now" gives the command to run later. On Windows it gives the folder and changes nothing. The README gives the link for an install from GitHub and from a folder, and the full path of `amd`.
- `r` on a row of the table, after one question, and `amd config --remove <path>` remove a repository from the list in `projects.toml`. No file of the repository changes. The sentence after the removal says so, and that `amd init`, `amd config` or the next session start there puts it back on the list.
- A person reads "start files as text", never "inject": the column of the table, the row "Give the start files as text when they fit in 10,000 characters" with yes or no, the README and the comment beside `start.inject` in `atlasmd.toml`. The key keeps its name. The row of `agents.inject` reads "a subagent gets".
- The screen of `amd config` has the station About first: what atlasmd does in the three sentences of the welcome of the setup, how to set up a repository in three steps, every command with one line, the seven skills, and the three ways to turn atlasmd off. The last station of the setup names it.
- The setup prints each station under the one before, as a terminal does: the route stays at the top, a station that is done shows its answer on one line in the dim color, and the current station shows in full. The stack scrolls when it passes the bottom. Enter picks an answer only when it is on the screen.
- The setup, the screen of `amd config` and the README say "repository" where they meant the folder with `atlasmd.toml`.
- `amd check`, `amd map`, `amd area` and `amd meter` in a folder without `atlasmd.toml` above it print one sentence and exit with code 1: "Run this in a repository that has atlasmd.toml, in its root or in a folder under it. amd init sets one up." `amd meter --list` there prints the sessions of every repository.

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
