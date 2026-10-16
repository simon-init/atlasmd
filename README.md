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
   them again before its next edit there.
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
| `guard.mode` | `"deny"` | `deny`, `remind` or `off`. See [How the hook refuses an edit](#how-the-hook-refuses-an-edit). |
| `guard.bash` | `true` | The hook also looks at the Bash commands that write a file. |
| `agents.inject` | `"map"` | What a subagent gets at its start: `map` (the file in `start.map`), `start` (the same files as a session) or `none`. |
| `private.files` | `[]` | Markdown files that Claude gets at the start but that git never commits. `amd init` writes them into `.git/info/exclude`. |
| `[naming]` | four rules | For each folder, the regular expression that a file name must match. The rule of the deeper folder wins. |
| `[[area]]` | none | One table for each group of folders, with `name`, `paths` and `pack`. `paths` lists folders or files. `pack` lists the files that Claude must read before it changes a file in `paths`. |

An `[[area]]` entry looks like this:

```toml
[[area]]
name = "the scrubber"
paths = ["services/scrubber/scrubber/", "services/scrubber/policy/"]
pack = ["services/scrubber/README.md", "docs/decisions/P008-default-policy.md", "docs/product-decisions.md#P15"]
```

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
| `amd check` | Reports the tokens of the files in `docs/start/` against `start.budget` and against the 10,000 characters of a hook, files under `pack` that do not exist, `[[area]]` entries whose paths overlap, file names that break the rule of their folder, Markdown files that no rule tells Claude to read, and a map file that is out of date. Exit code 1 on a problem. `--json` for the skill. |
| `amd map` | Writes the list of every Markdown file and the table of the `[[area]]` entries into the map file, between marker lines. The text outside the markers stays. |
| `amd status` | Shows, for each `[[area]]`, whether this session read all, some or none of the files under `pack`. It also shows the `[[area]]` entries where the session read a file or had an edit refused, and the last compaction. `--session <id>` and `--agent <id>` select the session or the subagent. |
| `amd why` | Shows the last edit that the hook refused, with the text that Claude got. `--session <id>` selects a session. |
| `amd end` | Shows what is not committed or not pushed, and the first message for a fresh chat, from `start.line`. Exit code 1 when something is not committed or not pushed. |
| `amd set <key> <value>` | Writes one of your own settings. |
| `amd version` | Prints the version. |

In a Claude Code session, six skills run the command line for you:

| Skill | What it does |
|---|---|
| `/amd:init` | After one question, writes `atlasmd.toml`, fills `docs/start/`, lists the files to read before a change in each folder, and moves the files that you agree to move. |
| `/amd:check` | Runs `amd check`, explains each problem, and makes the fixes that you agree to. |
| `/amd:map` | Runs `amd map` and tells you what changed in the map file. |
| `/amd:status` | Tells you which files under `pack` this session read, and which it did not read. |
| `/amd:why` | Explains the last refused edit: the file, the `[[area]]`, and the files to read. |
| `/amd:end` | Writes the file in `start.state` again, commits and pushes, and gives you the first message for a fresh chat. |

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
files in `start.state`, `start.map` and `private.files`, or of a file under `pack`. So
Claude can always change the files that it must read. The hook knows only the common
forms of Bash commands that write a file. It lets a form that it does not know go
through.

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
