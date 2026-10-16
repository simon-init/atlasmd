# atlasmd

![tests](https://github.com/simon-init/atlasmd/actions/workflows/tests.yml/badge.svg)

atlasmd is a Claude Code plugin for the Markdown files of a project. It gives every
session the same small start reading, also after a compaction. It makes an agent read
the guide of an area before the agent changes the area. It writes one line to a log
after each compaction, so you can see what a compaction costs. It is a set of command
hooks in Python, with no dependencies, and a command line, `amd`.

## What it does

1. **The start reading.** A project keeps the files that every session must read first
   in one folder, `docs/start/`, numbered in the order of the read. At each session
   start and after each compaction, the hook gives these files to the session, within
   a budget of tokens. When the files fit in the 10,000 characters that Claude Code
   takes from a hook, the hook gives their content. When they do not fit, it gives the
   content of the first files as far as the limit lets, and the list of the rest, and
   the session reads each file of the list. So a fresh session and a
   compacted session start with the same small reading.
2. **The guard.** A project names its areas. Each area has code paths and a pack: the
   Markdown files to read before a change in the area. The hook refuses an Edit or a
   Write in an area until the agent read every file of the pack in this session. After
   a compaction, the first change in an area reads the pack again.
3. **The measurement.** After each compaction, one line goes into a log: the time, the
   folder of the project, the trigger and the size of the summary.

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

The hook and the command line need Python 3.11 or newer and git. Nothing else is
installed. The two screens, `amd setup` and `amd config`, need the curses module. Linux
and macOS have it. On Windows, Python gets it with `pip install windows-curses`, and
every other command works without it.

## Quick start

In a Claude Code session, in your project:

```
/amd:init
```

Claude reads the list of your Markdown files, proposes the areas, the start reading and
the moves in one message, and asks you once. After your yes, it writes `atlasmd.toml`,
fills the four files of `docs/start/`, and moves the files that you agreed to move. It
commits nothing unless you ask.

In a terminal, once after the install:

```
amd setup
```

A screen with five steps: what atlasmd does, how it works, your own settings, this
project, and the three commands to remember. It writes nothing before the last step,
except the files of `amd init` if you choose to run it on the step for this project.

## The convention

The folder says when a file is read and what kind of file it is. The name says the
order, the date or the number, and the subject. The subject is one to four words, in
lower case, joined by hyphens, in ASCII. The name has no prefix for the kind, because
the folder gives the kind.

| Folder | Read | Name |
|---|---|---|
| `docs/start/` | at every start and after every compaction, in name order | `NN-<subject>.md`. Two digits set the order: `10-map.md`, `20-open-items.md`, `30-state.md`, `40-way-of-work.md` |
| `<code folder>/README.md` | before a change in that area, as part of its pack | `README.md`, next to its code |
| `docs/decisions/` | by number, when the pack of an area names the decision | `P<NNN>-<subject>.md`, one file per decision, and `README.md` as the index with one line each |
| `docs/plans/` | when the work of the plan starts | `<subject>.md`. A built plan moves to `docs/archive/` |
| `docs/notes/` | when the subject of the note comes up | `YYYY-MM-DD-<subject>.md`. The date comes first, so the files sort by time |
| `docs/archive/` | never at a start. This folder holds history | the name that the file had |

`amd check` reports a file whose name does not match the rule of its folder. It also
reports a Markdown file that no folder rule, no pack and no start reading covers, so
you can see what nothing reads. Files at the root of the project, files in folders
whose names start with a dot, `CLAUDE.md`, `AGENTS.md` and `SKILL.md` are for people
and for Claude Code, and the check does not report them. The check renames nothing.

## The settings of a project: `atlasmd.toml`

The file is at the root of the project. `amd init` writes it with every default and a
comment on each key. Every path is relative to the folder of `atlasmd.toml`, with `/`
as the separator.

| Key | Default | What it does |
|---|---|---|
| `start.dir` | `"docs/start"` | The Markdown files of this folder, in name order, are the start reading. |
| `start.files` | `[]` | A list of paths in order. When it has paths, the hook uses it, not `start.dir`. |
| `start.also` | `[]` | More folders or files, read after the files above. |
| `start.budget` | `30000` | The limit of the start reading, in estimated tokens. Above it, the hook gives the list of files and a warning, not their content. |
| `start.inject` | `true` | With `false`, the hook always gives the list of files and tells the session to read them. |
| `start.state` | `"docs/start/30-state.md"` | The state file, which the ending writes again. |
| `start.map` | `"docs/start/10-map.md"` | The map. A subagent gets it at its start, and `amd map` writes into it. |
| `start.line` | `"Say where things stand."` | The message that a person sends to a fresh chat. |
| `guard.mode` | `"deny"` | `deny`, `remind` or `off`. See the section on the guard. |
| `guard.bash` | `true` | The guard also examines the Bash commands that write a file. |
| `agents.inject` | `"map"` | What a subagent gets at its start: `map`, `start` or `none`. |
| `private.files` | `[]` | Markdown files of the start reading that git never commits. `amd init` writes them into `.git/info/exclude`. |
| `[naming]` | four rules | For each folder, the regular expression that a file name must match. The rule of the deeper folder wins. |
| `[[area]]` | none | One table per area, with `name`, `paths` and `pack`. |

An area looks like this:

```toml
[[area]]
name = "the scrubber"
paths = ["services/scrubber/scrubber/", "services/scrubber/policy/"]
pack = ["services/scrubber/README.md", "docs/decisions/P008-default-policy.md", "docs/product-decisions.md#P15"]
```

A path that ends in `/` is a folder. A path without `/` at its end is one file. A pack
entry can end in `#<anchor>`. Then the refusal names that section of the file, and a
read of the file counts.

## Your own settings

Two settings apply to every project on your computer. `amd set` writes them into
`~/.claude/plugins/data/amd/settings.toml`, and `amd setup` and `amd config` show them:

| Key | Default | What it does |
|---|---|---|
| `offer_setup` | `yes` | In a project without `atlasmd.toml`, the session says once that `/amd:init` sets it up. |
| `token_chars` | `2.5` | The characters per token for every estimate. 2.5 is a careful value for English and code. |

The plugin also has the option `offer_setup` in Claude Code. When that option is set,
it wins over the settings file.

## The commands

| Command | What it does |
|---|---|
| `amd` | The help: the logo, what atlasmd is, and the commands. |
| `amd setup` | The guided screen. Run it once after the install. It is safe to run again. |
| `amd config` | The settings screen of the project and of you. The budget, the two inject values, the guard mode and your own settings can change there. The areas are read only. `s` saves, `q` quits. |
| `amd scan` | Every Markdown file with its size in KB and its estimated tokens, the folders with source files and a README, and the files that `CLAUDE.md` names. `--json` gives the same as JSON. |
| `amd init` | Writes `atlasmd.toml`, the four files of `docs/start/` and the folders of the convention, and overwrites nothing. `--areas-json <file>` fills the areas. `--dry-run` writes nothing. |
| `amd check` | The start reading against the budget and against the 10,000 characters of a hook, the packs, the overlaps of areas, the names, the files that nothing reads, and the map. Exit code 1 on a problem. `--json` for the skill. |
| `amd map` | Writes the tree of every Markdown file and the area table into the map, between marker lines. The text outside the markers stays. |
| `amd status` | The packs that this session read in full and in part, the areas it touched, and the last compaction. `--session <id>` and `--agent <id>` select the ledger. |
| `amd why` | The last refusal of the guard, with its text. `--session <id>` selects a session. |
| `amd end` | What is not committed or not pushed, and the opening line for a fresh chat. Exit code 1 when something is not committed or not pushed. |
| `amd set <key> <value>` | Writes one of your own settings. |
| `amd version` | The version. |

In a Claude Code session, six skills run the command line for you:

| Skill | What it does |
|---|---|
| `/amd:init` | Sets up the project: the areas, the start reading and the moves, after one question. |
| `/amd:check` | Runs the check, explains each finding, and applies the fixes that you agree to. |
| `/amd:map` | Writes the map again and tells you what changed. |
| `/amd:status` | Tells you which packs this session read and which it did not. |
| `/amd:why` | Explains the last refusal: the area, the files, and what to read. |
| `/amd:end` | Writes the state file again, commits and pushes, and gives you the opening line. |

## How the guard works

The hook runs before each Edit, Write, MultiEdit and NotebookEdit, and before each Bash
command that writes a file, when `guard.bash` is `true`. It finds the area of the file
from the code paths. If the file is in no area, the change goes on. If the agent did
not read every file of the pack of the area in this session, the guard acts by its
mode. A pack file that does not exist does not block a change, and `amd check` reports
it.

The hook records each file that a session reads in a ledger, one ledger per session
and one per subagent. After a compaction, the ledger of the session starts again,
because the compaction removed the files from the context.

The two modes:

- `deny` refuses the change. Claude gets the list of the files to read, reads them, and
  makes the change again. `amd why` shows the last refusal.
- `remind` lets the change through and gives Claude the list of the files to read with
  the result of the change.

`off` stops the guard. The start reading and the log stay.

The file `atlasmd.toml`, the start reading, the state file, the map, the private files
and every pack file are always free to change, so the guard never blocks the work on
the guides themselves. The parser of Bash commands knows the common forms only. A form
that it does not know goes through.

## What it costs in tokens

- **The start reading.** At most the budget, 30,000 estimated tokens by default, at
  each start and after each compaction. Claude Code takes at most 10,000 characters
  from a hook. When the start reading fits in that limit, the hook gives the content.
  When it does not fit, the hook gives the list of the files, and the session reads
  each file. The reads cost the same tokens as the content, and one tool call per file.
- **The guard.** One read of a pack per area per session, and again after a
  compaction. Nothing for an area that the session does not touch.
- **A subagent.** The map at its start, by default. The same limit of 10,000
  characters applies: a longer map comes as its path, and the subagent reads it. With
  `agents.inject = "none"`, nothing.
- **A refusal.** A few lines with the list of the files.

`amd check` shows the tokens of each start file and the total against the budget and
the 10,000 characters.

## Python

Python 3.11 or newer, the standard library only. The tests run on Linux with 3.11 and
3.13, and on macOS and Windows with 3.13:

```
python3 -m unittest discover -s tests
```

## Privacy

Nothing leaves your computer. [PRIVACY.md](PRIVACY.md) says what the plugin reads and
what it keeps.

## Uninstall

```
claude plugin uninstall amd@atlasmd
```

Then remove the link to `amd` from your path. The plugin data stays in
`~/.claude/plugins/data/amd/` until you delete that folder. The files of your project,
`atlasmd.toml` and `docs/start/`, stay in the project.

## License

MIT. See [LICENSE](LICENSE).
