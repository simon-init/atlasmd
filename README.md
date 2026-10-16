# atlasmd

![tests](https://github.com/simon-init/atlasmd/actions/workflows/tests.yml/badge.svg)

atlasmd is a hook inside Claude Code, written in Python with no dependencies, with a
command line, `amd`. It does three things:

1. **At the start of a session, and after every compaction,** it gives Claude the
   Markdown files in `docs/start/` of your project, and nothing else. Claude Code takes
   at most 10,000 characters from a hook. When the files fit, Claude gets their text.
   When they do not, Claude gets the text of the first files as far as the limit lets,
   the list of the rest, and reads each file of the list with one Read. So a fresh
   session and a compacted session start with the same files.
2. **Before every edit,** when the file is in a folder that `atlasmd.toml` lists, it
   refuses the edit until Claude has read the files listed for that folder, for example
   the folder's README and the decisions behind it. After a compaction, Claude reads
   them again before its next edit there. It also refuses a new Markdown file whose name
   breaks the rule of its folder. When Claude writes a new source file in a folder that
   `atlasmd.toml` does not list, the hook tells Claude once to write the README.md of
   the folder and its entry in `atlasmd.toml`.
3. **After every compaction,** it writes one line to `compacts.log`: the date and time,
   the project folder, whether the compaction was manual or automatic, and the size of
   the summary in characters. So you can see what compactions cost.

## Install

In a terminal:

```
claude plugin marketplace add simon-init/atlasmd
claude plugin install amd@atlasmd
```

Or in a Claude Code session:

```
/plugin install amd --marketplace simon-init/atlasmd
```

Then put the command line on your path, once. On Linux and macOS:

```
ln -s ~/.claude/plugins/marketplaces/atlasmd/bin/amd ~/.local/bin/amd
```

On Windows, add this folder to your PATH. The launcher in it is `amd.cmd`:

```
%USERPROFILE%\.claude\plugins\marketplaces\atlasmd\bin
```

The hook and the command line need Python 3.11 or newer and git. The plugin installs
nothing else. The two screens, `amd setup` and `amd config`, need the curses module.
Linux and macOS have it. On Windows, install it with `pip install windows-curses`.
Every other command works without it.

## Quick start

In a Claude Code session, in your project:

```
/amd:init
```

Claude reads the list of your Markdown files. Then it proposes three lists in one
message and asks you once:

- the text for the four files of `docs/start/`, which Claude gets at the start of every
  session,
- for each code folder, the files that Claude must read before it changes a file there,
- the Markdown files to move or to give a new name.

After your yes, Claude writes `atlasmd.toml`, writes the four files of `docs/start/`,
and moves the files that you agreed to move. It commits nothing unless you ask.

In a terminal, once after the install:

```
amd setup
```

This command opens a screen with five steps: what atlasmd does, how it works, your own
settings, this project, and three commands to remember. It saves your settings at the
last step. On the step for this project, you can run `amd init`, which writes its files
at once.

## Where the Markdown files go, and their names

The folder of a file says when it is read. The name of the file says the order, the
date or the number, and the subject. The subject is one to four words, in lower case,
joined by hyphens, in ASCII. The name has no prefix for the kind of file, because the
folder gives the kind.

| Folder | When to read it | Name |
|---|---|---|
| `docs/start/` | at the start of every session and after every compaction, in name order. The hook gives these files to Claude | `NN-<subject>.md`. Two digits set the order: `10-map.md`, `20-open-items.md`, `30-state.md`, `40-way-of-work.md` |
| `<code folder>/README.md` | before a change in that folder, when `atlasmd.toml` lists the README under `pack` | `README.md`, next to its code |
| `docs/decisions/` | before a change in a folder, when `atlasmd.toml` lists the decision under `pack` | `P<NNN>-<subject>.md`, one file per decision, and `README.md` as the index with one line each |
| `docs/plans/` | when the work of the plan starts | `<subject>.md`. When the plan is built, the file moves to `docs/archive/` |
| `docs/notes/` | when the subject of the note comes up | `YYYY-MM-DD-<subject>.md`. The date comes first, so the files sort by time |
| `docs/archive/` | never at the start. This folder holds old files | the name that the file had |

`amd init` writes four files into `docs/start/`:

- `10-map.md`, the map file: what the project is, the files to read before a change in
  each folder, where each kind of fact lives, and the list of every Markdown file.
  `amd map` writes the two lists.
- `20-open-items.md`: one line for each open item, with the path of the file that holds
  the details.
- `30-state.md`: where the work stands. `/amd:end` writes it again at the end of a
  session.
- `40-way-of-work.md`: the rules that Claude follows in every session.

`amd check` reports a file whose name does not match the rule of its folder. It also
reports a Markdown file that is not in `docs/start/`, not under `pack`, and not in a
folder under `[naming]`, because no rule says when Claude reads that file. The check
does not report files at the root of the project, files in folders whose names start
with a dot, `CLAUDE.md`, `AGENTS.md` and `SKILL.md`. These files are for people and
for Claude Code. The check renames nothing.

## How the Markdown files live

`amd init` writes these eight rules into `docs/start/40-way-of-work.md`, so Claude gets
them at the start of every session:

- A new folder with source files gets a README.md beside the code in the same commit.
  The README says what the folder holds, how to run it, and its state, with the date.
  The folder gets an `[[area]]` entry in `atlasmd.toml` with the README as the first
  file to read before a change there. Then run `amd map`. The command
  `/amd:area <folder>` does all three.
- A decision is a new file in `docs/decisions/` with the next number and a line in
  `docs/decisions/README.md`. A change to a decision goes into the decision's own file
  under a heading with the date. Never a second file for the same decision.
- A plan is a file in `docs/plans/` while the work is open, and one line in
  `docs/start/20-open-items.md` points at it. In the commit that builds the plan, the
  file moves to `docs/archive/` with `git mv`, and the line leaves the open items.
- An open item is one line in `docs/start/20-open-items.md`: the item, its state in one
  sentence, and the file that holds the detail. The line leaves in the commit that
  closes the item. A detail longer than three lines goes into a note in `docs/notes/`,
  and the line points at the note.
- `docs/start/30-state.md` is rewritten at every ending, never appended. What is done
  since the last ending stands there once. At the next ending it leaves.
- A note in `docs/notes/` is named with its date first. When a newer note replaces it
  on the same subject, the old note moves to `docs/archive/` in the same commit.
- The State section of a README changes in the commit that changes the state, with the
  commit hash there and not in the open items.
- Before an ending, run `amd check` and do what it says: archive the built plans, close
  the items, move the replaced notes. Then rewrite the state file.

atlasmd keeps these rules in four ways:

1. The text of the rules, in `docs/start/40-way-of-work.md`.
2. `amd check` reports each file and folder that breaks a rule. The next section gives
   the findings.
3. The hook refuses a Write of a new Markdown file whose name breaks the rule of its
   folder. When Claude writes a new source file in a folder that no `[[area]]` entry
   lists, the hook tells Claude once. See
   [How the hook refuses an edit](#how-the-hook-refuses-an-edit).
4. `/amd:end` runs `amd check` and does what it says before it writes the file in
   `start.state` again. `/amd:area <folder>` writes the README.md and the `[[area]]`
   entry of a folder.

atlasmd deletes no file. `amd check` names the file, Claude moves it to `docs/archive/`
with `git mv` at the end of a session, and git keeps every version.

## What amd check reports on the folders and the Markdown files

`amd check` reports nine findings under the headings `growth` and `cleaning`. The text
of each finding says the fix. A key under `[check]` in `atlasmd.toml` turns the
findings of its row off with `false` or `0`.

| Finding | The text, and what counts | Key under `[check]` |
|---|---|---|
| `no-readme` | `<folder>/ has source files and no README.md. Write one, or run /amd:area <folder>.` A folder counts when it holds a file with an extension that `amd scan` counts as source, and no README.md is in it or in a folder above it, below the root. `docs/`, folders whose names start with a dot, `node_modules`, `.venv`, `tests` and `test` do not count. | `folders` |
| `no-entry` | `<folder>/ has source files and no [[area]] entry in atlasmd.toml lists it. Run /amd:area <folder>.` The same folders, when the paths of no `[[area]]` entry hold a source file of the folder. | `folders` |
| `dead-entry` | `the [[area]] "<name>" lists <path>, which does not exist. Remove it or fix the path.` For each path under `paths`. | `folders` |
| `stale-readme` | `<README> did not change in the last <N> commits that changed <folder>/. Update its State section.` For each README.md under `pack`. The count starts at the last commit of the README. When the paths of the `[[area]]` entry hold the folder of the README, the commits that change that folder count. When the paths lie inside that folder, the commits that change those paths count, and the text names them. | `stale_readme`, 15 commits |
| `dead-pointer` | `docs/start/20-open-items.md names <path>, which does not exist. Fix the line or remove it.` A path is a text in backticks that has a `/` or ends in `.md`, from the root of the project. A text with a space, a URL and a text with `<` do not count. The file is `start.items`. | `dead_pointers` |
| `orphan-plan` | `docs/plans/<file> is named by no line of docs/start/20-open-items.md. Add a line, or move the plan to docs/archive/ if it is built.` | `plans` |
| `orphan-note` | `docs/notes/<file> is named by no Markdown file and is <days> days old. Point at it, or move it to docs/archive/.` The age comes from the date at the start of the name, else from the date of the last commit of the file. The list that `amd map` writes and the files in `docs/archive/` do not count as a name. | `notes`, 30 days |
| `no-index-line` | `docs/decisions/<file> has no line in docs/decisions/README.md. Add the line.` The number at the start of the file name must be in the index, for example `P012` or `P12` for `P012-policy.md`. | `decisions` |
| `stale-state` | `<state file> did not change in the last <N> commits. Rewrite it with /amd:end.` | `stale_state`, 20 commits |

The folders `docs/plans/`, `docs/notes/` and `docs/decisions/` are the folders under
`[naming]` whose last names are `plans`, `notes` and `decisions`. When a project does
not have one of these folders, its check does not run. The checks that count commits
run only in a git repository with a commit.

## The settings of a project: `atlasmd.toml`

The file is at the root of the project. `amd init` writes it with every default and a
comment on each key. Every path is relative to the folder of `atlasmd.toml`, with `/`
as the separator.

| Key | Default | What it does |
|---|---|---|
| `start.dir` | `"docs/start"` | At the start of a session and after a compaction, Claude gets the Markdown files of this folder, in name order. |
| `start.files` | `[]` | A list of paths in order. When it has paths, the hook uses it, not `start.dir`. |
| `start.also` | `[]` | More folders or files. Claude gets them after the files above. |
| `start.budget` | `30000` | The limit for these files, in estimated tokens. Above it, the hook gives Claude the list of the files and a warning, not their text. |
| `start.inject` | `true` | `true`: the hook puts the text of the files into Claude's context. `false`: the hook always gives the list of the files, and Claude reads them. |
| `start.state` | `"docs/start/30-state.md"` | The file that says where the work stands. `/amd:end` writes it again. |
| `start.map` | `"docs/start/10-map.md"` | The map file. `amd map` writes the list of every Markdown file and the table of the `[[area]]` entries into it. A subagent gets it at its start. |
| `start.line` | `"Say where things stand."` | The first message that a person sends in a fresh chat. `amd end` and `/amd:end` show it. |
| `start.items` | `"docs/start/20-open-items.md"` | The file of the open items. `amd check` reports a path in backticks in it that does not exist, and a plan that it does not name. |
| `guard.mode` | `"deny"` | `deny`, `remind` or `off`. See [How the hook refuses an edit](#how-the-hook-refuses-an-edit). |
| `guard.bash` | `true` | The hook also looks at the Bash commands that write a file. |
| `guard.new_folders` | `"remind"` | `remind` or `off`. With `remind`, when Claude writes a new source file in a folder that no `[[area]]` entry lists, the hook tells Claude once in the session to write the README.md of the folder and its entry. |
| `agents.inject` | `"map"` | What a subagent gets at its start: `map` (the file in `start.map`), `start` (the same files as a session) or `none`. |
| `private.files` | `[]` | Markdown files that Claude gets at the start but that git never commits. `amd init` writes them into `.git/info/exclude`. |
| `[naming]` | four rules | For each folder, the regular expression that a file name must match. The rule of the deeper folder wins. `amd check` reports a name that breaks the rule, and the hook refuses a Write of a new Markdown file whose name breaks it. |
| `check.folders` | `true` | `amd check` reports a folder with source files and no README.md or no `[[area]]` entry, and a path of an `[[area]]` entry that does not exist. |
| `check.stale_readme` | `15` | `amd check` reports a README.md under `pack` that did not change in the last 15 commits that changed its folder. `0` turns it off. |
| `check.dead_pointers` | `true` | `amd check` reports a path in backticks in `start.items` that does not exist. |
| `check.plans` | `true` | `amd check` reports a file in `docs/plans/` that no line of `start.items` names. |
| `check.notes` | `30` | `amd check` reports a note in `docs/notes/` that no Markdown file names and that is older than 30 days. `0` turns it off. |
| `check.decisions` | `true` | `amd check` reports a file in `docs/decisions/` without a line in `docs/decisions/README.md`. |
| `check.stale_state` | `20` | `amd check` reports the file in `start.state` when it did not change in the last 20 commits. `0` turns it off. |
| `[[area]]` | none | One table for each group of folders, with `name`, `paths` and `pack`. `paths` lists folders or files. `pack` lists the files that Claude must read before it changes a file in `paths`. |

An `[[area]]` entry looks like this:

```toml
[[area]]
name = "the API"
paths = ["api/"]
pack = ["api/README.md", "docs/decisions/P003-time-is-utc.md"]
```

With this entry, the hook refuses a change to a file in `api/` until Claude reads
`api/README.md` and `docs/decisions/P003-time-is-utc.md`. For example, the README of
`api/` says that every time is stored as UTC, so Claude knows it before it writes code
there.

A path that ends in `/` is a folder. A path without `/` at its end is one file. An entry
under `pack` can end in `#<anchor>`. Then the refusal names that section of the file,
and a read of the file counts.

## Your own settings

Two settings apply to every project on your computer. `amd set` writes them into
`~/.claude/plugins/data/amd/settings.toml`, and `amd setup` and `amd config` show them:

| Key | Default | What it does |
|---|---|---|
| `offer_setup` | `yes` | In a project without `atlasmd.toml`, the hook tells Claude once that `/amd:init` writes `atlasmd.toml` and `docs/start/`. |
| `token_chars` | `2.5` | The number of characters per token. atlasmd divides the characters of a file by this number to estimate its tokens. 2.5 is a careful value for English and code. |

The plugin also has the option `offer_setup` in Claude Code. When that option is set,
it wins over the settings file.

## The commands

| Command | What it does |
|---|---|
| `amd` | Prints the logo, one paragraph on what atlasmd does, and the commands. |
| `amd setup` | Opens a screen with five steps. Run it once after the install. You can run it again: it changes only your two settings, and `amd init` overwrites no file. |
| `amd config` | Opens a screen with the values of `atlasmd.toml` and your own settings. You can change `start.budget`, `start.inject`, `guard.mode`, `agents.inject` and your own settings there. The screen shows the `[[area]]` entries but cannot change them. `s` saves, `q` quits. |
| `amd scan` | Lists every Markdown file with its size in KB and its estimated tokens, the folders with source files and a README, and the files that `CLAUDE.md` names. `--json` gives the same as JSON. |
| `amd init` | Writes `atlasmd.toml`, the four files of `docs/start/`, and the folders `docs/decisions/`, `docs/plans/`, `docs/notes/` and `docs/archive/`. It overwrites nothing. `--areas-json <file>` adds the `[[area]]` entries of a JSON file. `--dry-run` writes nothing. |
| `amd check` | Reports the tokens of the files in `docs/start/` against `start.budget` and against the 10,000 characters of a hook, files under `pack` that do not exist, `[[area]]` entries whose paths overlap, file names that break the rule of their folder, Markdown files that no rule tells Claude to read, a map file that is out of date, and the nine findings of [What amd check reports on the folders and the Markdown files](#what-amd-check-reports-on-the-folders-and-the-markdown-files). Exit code 1 on a problem. `--json` for the skill. |
| `amd map` | Writes the list of every Markdown file and the table of the `[[area]]` entries into the map file, between marker lines. The text outside the markers stays. |
| `amd area <folder>` | Writes `<folder>/README.md` from a template when the folder has none, adds an `[[area]]` entry with `paths = ["<folder>/"]` and `pack = ["<folder>/README.md"]` at the end of `atlasmd.toml`, and writes the map file. The text and the comments of `atlasmd.toml` stay. `--name <name>` gives the name of the entry. The default is the name of the folder. It refuses a folder that does not exist, that holds no source files, or that an `[[area]]` entry lists already. |
| `amd status` | Shows, for each `[[area]]`, whether this session read all, some or none of the files under `pack`. It also shows the `[[area]]` entries where the session read a file or had an edit refused, and the last compaction. `--session <id>` and `--agent <id>` select the session or the subagent. |
| `amd why` | Shows the last edit that the hook refused, with the text that Claude got. `--session <id>` selects a session. |
| `amd end` | Shows what is not committed or not pushed, and the first message for a fresh chat, from `start.line`. Exit code 1 when something is not committed or not pushed. |
| `amd set <key> <value>` | Writes one of your own settings. |
| `amd version` | Prints the version. |

In a Claude Code session, seven skills run the command line for you:

| Skill | What it does |
|---|---|
| `/amd:init` | After one question, writes `atlasmd.toml`, fills `docs/start/`, lists the files to read before a change in each folder, and moves the files that you agree to move. |
| `/amd:check` | Runs `amd check`, explains each problem, and makes the fixes that you agree to. |
| `/amd:map` | Runs `amd map` and tells you what changed in the map file. |
| `/amd:area <folder>` | Runs `amd area <folder>`, then reads the files of the folder and writes its README.md: what the folder holds, how to run it, and its state. |
| `/amd:status` | Tells you which files under `pack` this session read, and which it did not read. |
| `/amd:why` | Explains the last refused edit: the file, the `[[area]]`, and the files to read. |
| `/amd:end` | Runs `amd check` and does what it says: moves the built plans and the replaced notes to `docs/archive/` with `git mv`, corrects the open items and the index of the decisions, and writes the missing READMEs and the State sections. Then it writes the file in `start.state` again, commits and pushes, and gives you the first message for a fresh chat. It tells you what moved, and what it left and why. |

## How the hook refuses an edit

The hook runs before each Edit, Write, MultiEdit and NotebookEdit, and before each Bash
command that writes a file, when `guard.bash` is `true`. It looks for the `[[area]]`
whose `paths` hold the file. If no `[[area]]` holds the file, the edit goes on. If
Claude did not read every file under `pack` of that `[[area]]` in this session, the
hook does what `guard.mode` says. A file under `pack` that does not exist does not stop
an edit, and `amd check` reports it.

The hook keeps a list of the files that each session reads, one list for each session
and one for each subagent, in `~/.claude/plugins/data/amd/ledgers/`. After a
compaction, the hook empties the list of the session, because the compaction removed
the files from Claude's context.

The values of `guard.mode`:

- `deny` refuses the edit. Claude gets the list of the files to read, reads them, and
  makes the edit again. `amd why` shows the last refused edit.
- `remind` permits the edit. With the result of the edit, Claude gets the list of the
  files to read.
- `off` stops these checks of edits. The files of `docs/start/` at the start and the
  lines in `compacts.log` stay.

The hook never refuses an edit of `atlasmd.toml`, of the files of `docs/start/`, of the
files in `start.state`, `start.map`, `start.items` and `private.files`, or of a file
under `pack`. So Claude can always change the files that it must read. The hook knows
only the common forms of Bash commands that write a file. It lets a form that it does
not know go through.

### A new file

Before a Write of a file that does not exist yet, the hook does two more checks:

- **A Markdown file whose name breaks the rule of its folder under `[naming]`.** With
  `guard.mode` `deny`, the hook refuses the Write with this text:
  `atlasmd: docs/notes/ names its files with the date as YYYY-MM-DD, a hyphen and the subject in lower case with hyphens, for example 2026-10-16-gate-run.md. Gate Run.md breaks that rule. Name the file so, then write it again.`
  The hook gives the four rules of `docs/start/`, `docs/decisions/`, `docs/notes/` and
  `docs/plans/` in words, and any other rule as its regular expression. The example
  gets the next free number or the date of today. With `remind`, the hook permits the
  Write and gives Claude the same text. With `off`, it does not look. `README.md`
  passes in every folder.
- **A source file in a folder that no `[[area]]` entry lists**, when
  `guard.new_folders` is `remind`. The hook permits the Write and gives Claude this
  text with the result:
  `atlasmd: tools/ has no [[area]] entry in atlasmd.toml. Make its README.md and add the entry, or run /amd:area tools.`
  When the Write makes new folders, the text names the first new folder. The hook
  gives the text once for each folder in a session, and again after a compaction. The
  list of the files that the session read keeps the folders that it named.
  `docs/`, folders whose names start with a dot, `node_modules`, `.venv`, `tests` and
  `test` do not get the text.

An Edit of a file that exists is never refused for its name. The hook looks only at the
Write tool for a new file. A Bash command that makes a file does not get these checks.

## What it costs in tokens

- **The files of `docs/start/`.** At most `start.budget`, 30,000 estimated tokens by
  default, at each start and after each compaction. Claude Code takes at most 10,000
  characters from a hook. When the files fit in that limit, the hook gives their text.
  When they do not fit, the hook gives the text of the first files as far as the limit
  lets, and the list of the rest. Claude reads each file of the list. A read costs the
  same tokens as the text, and one tool call per file.
- **The files to read before an edit.** One read of the files under `pack` of an
  `[[area]]` in each session, and again after a compaction. Nothing for an `[[area]]`
  whose paths the session does not change.
- **A subagent.** The map file at its start, by default. The same limit of 10,000
  characters applies: a longer map file comes as its path, and the subagent reads it.
  With `agents.inject = "none"`, nothing.
- **A refused edit.** A few lines with the list of the files.

`amd check` shows the tokens of each file in `docs/start/`, and the total against
`start.budget` and against the 10,000 characters.

## Python

Python 3.11 or newer, the standard library only. The tests run on Linux with 3.11 and
3.13, and on macOS and Windows with 3.13:

```
python3 -m unittest discover -s tests
```

## Privacy

Nothing leaves your computer. [PRIVACY.md](PRIVACY.md) says which files the plugin reads
and which files it keeps.

## Uninstall

```
claude plugin uninstall amd@atlasmd
```

Then remove the link to `amd` from your path. The lists of read files, `compacts.log`
and your settings stay in `~/.claude/plugins/data/amd/` until you delete that folder.
The files of your project, `atlasmd.toml` and `docs/start/`, stay in the project.

## License

MIT. See [LICENSE](LICENSE).
