# atlasmd

![atlasmd](assets/logo-128.png)

![tests](https://github.com/simon-init/atlasmd/actions/workflows/tests.yml/badge.svg)

A plugin for Claude Code. It tells Claude which Markdown files to read at the start of a
session, and refuses a change in a folder until Claude read the files for that folder.
Python, no other package, and a command line, `amd`.

| Where | How you type a command | Example |
|---|---|---|
| In a Claude Code session | `/atlasmd:` and the name, or ask Claude in plain words | `/atlasmd:init`, or "set up atlasmd here" |
| In a terminal | `amd` and the name | `amd check` |

## Why

Claude starts every session with an empty memory. It knows the code that it reads, and
nothing more: not why a decision was made, not what is open, not how you want the work
done. The same happens after a compaction, when Claude Code replaces a long chat with a
short summary. So a project writes what Claude must know into Markdown files, and the
next session reads them. These files grow. In the project that atlasmd was built for,
they grew to about 580,000 tokens, and every session read all of them at its start.
atlasmd decides which files a session reads at the start, and which files Claude reads
before a change in each folder.

atlasmd was tested on that project. A new session started at about 85,000 tokens, grew
only as the work needed, and showed almost no loss in quality.

## What it does

- **At the start of a session, and after every compaction,** Claude gets the Markdown
  files in `docs/start/`. Claude Code takes at most 10,000 characters from a hook. Above
  that, Claude gets the text of the first files, then the names of the rest, and reads
  those itself.
- **Before an edit** in a folder that `atlasmd.toml` lists, the hook refuses the edit
  until Claude read the files named for that folder, for example its README. After a
  compaction, Claude reads them again.
- **After every compaction,** one line goes to `compacts.log`: when, which repository,
  and the size of the summary.
- **The meter** records the tokens of every session. `amd meter` compares a session with
  atlasmd on against one with atlasmd off.

## Install

Needs Claude Code, Python 3.11 or newer, and git. In a terminal:

```
claude plugin marketplace add simon-init/atlasmd
claude plugin install atlasmd@atlasmd
```

The first command prints `Successfully added marketplace: atlasmd`, the second
`Successfully installed plugin: atlasmd@atlasmd (scope: user)`. The plugin is on in every
session from the next session on. In a Claude Code session, this one command does the
same: `/plugin install atlasmd --marketplace simon-init/atlasmd`.

Nothing changes in a repository until you set it up. Until then, Claude gets one sentence
at the start of a session there: run `/atlasmd:init` once.

### amd in your terminal

The skills in a session run `amd` by its full path. In your terminal, the command is:

```
~/.claude/plugins/marketplaces/atlasmd/bin/amd
```

`amd setup` offers to link it to `~/.local/bin/amd`, so that `amd` alone works.

## Set up a repository

The setup writes `atlasmd.toml` at the root and four files in `docs/start/`. The hook
reads `atlasmd.toml` at every session start, so the next session in the repository gets
the files. No session is needed for the setup. Three ways:

**`amd setup`**, in the root of the repository, once after the install. It opens a screen
with six steps: what atlasmd does, how it works, the link for `amd`, your two settings,
this repository, done. On "This repository" it runs `amd init` for you.

**`amd init`**, in the root of the repository. It writes the files with their headings
and nothing under them. It overwrites nothing. You fill the four files yourself.

```
❯ amd init
atlasmd init  /home/you/api

Made:
  atlasmd.toml
  docs/start/
  docs/start/10-map.md
  docs/start/20-open-items.md
  docs/start/30-state.md
  docs/start/40-way-of-work.md
  docs/decisions/
  docs/plans/
  docs/notes/
  docs/archive/

Left as it was:
  nothing

Next: write the text of the files in docs/start/, then run amd map and amd check. Wrong folder? amd init --undo removes all of this while none of it changed.
```

Wrong folder? `amd init --undo` removes exactly these files and folders, as long as none
of them changed. One changed file stops it, and the message names the file.

```
❯ amd init --undo
atlasmd init --undo  /home/you/api

Removed:
  atlasmd.toml
  docs/start/10-map.md
  docs/start/20-open-items.md
  docs/start/30-state.md
  docs/start/40-way-of-work.md
  docs/start/
  docs/decisions/
  docs/plans/
  docs/notes/
  docs/archive/
  docs/

Left as it was:
  nothing
```

**`/atlasmd:init`**, in a Claude Code session. Claude reads the names of your Markdown files
and your code folders. It proposes in one message what goes into the four files, an entry
for every code folder with the files to read before a change there, and which files to
move, and asks once. After your yes it writes the files, writes a README for every code
folder that has none, and moves what you agreed to. It commits nothing.

Nothing sorts the Markdown files that the repository has already. `amd init` and
`amd setup` leave them where they are. `/atlasmd:init` is the one that proposes where each
file goes and moves it after your yes. It works also after `amd init`.

### Add a code folder

`/atlasmd:init` covers every code folder at the setup. `amd area <folder>` is for one folder
with code that comes later, inside the repository, not for the repository itself. It writes `<folder>/README.md` and tells the hook: before a change in
this folder, read this README. Run it in the root of the repository with the name of the
folder, or inside the folder with `.`:

```
❯ amd area api
atlasmd area  /home/you/api

Made:
  api/README.md, from the template
  the [[area]] "api" at the end of atlasmd.toml, with paths = ["api/"] and pack = ["api/README.md"]
  docs/start/10-map.md: the table of the [[area]] entries and the tree of the Markdown files

Left as it was:
  nothing

Next: write in api/README.md what the folder holds, how to run it, and its state, from the files of api/. Then run amd check.
```

A folder that does not exist, that holds no code, or that is listed already, gets one
sentence and `amd area made nothing`. In a session, `/atlasmd:area api` also writes the
README from the files of the folder.

### Check

`amd check` prints one line per check, `✓` or `✗`, and what to fix. It ends with
`No problems.` or with the exit code 1.

### Remove atlasmd from a repository

`amd config` shows every repository that atlasmd knows. `r` on a repository there, or
`amd config --remove <path>` in a terminal, removes atlasmd from it: it deletes that
repository's `atlasmd.toml`, so the hook gives no start files and refuses nothing there.
`docs/start/` and every other file stay. `amd init` there sets it up again.

## What happens by itself, and what you do

**By itself, in every session, without a command.** The hook:

- gives Claude the files of `docs/start/` at the start and after every compaction,
- refuses an edit in a listed folder until Claude read the files named for it,
- refuses a new Markdown file whose name breaks the rule of its folder,
- tells Claude once when it writes code in a folder without an `[[area]]` entry,
- writes the line in `compacts.log` and the token record of the session,
- says once, in a repository without `atlasmd.toml`: run `/atlasmd:init`.

**Claude does in a session, because `docs/start/40-way-of-work.md` tells it to.** At
`/atlasmd:init`, every code folder gets its entry and its README. Later, when Claude writes
code in a new folder, the hook reminds it once, and Claude writes the README and the
entry. A decision gets a file in `docs/decisions/`. An open item gets a line. The state file is
rewritten at the end. This is what Claude usually does, not a guarantee: `amd check`
shows what it missed.

**Only when you ask.** `/atlasmd:init` asks once, then writes and moves. `/atlasmd:area` writes
the README of one folder. `/atlasmd:check` makes the fixes that you agree to. `/atlasmd:end`
makes the fixes, rewrites the state file, commits and pushes. Every `amd` command in a
terminal.

**Never.** atlasmd deletes no file of yours. `amd init --undo` removes its own unchanged
files, and `r` in `amd config` deletes only `atlasmd.toml`. It moves no file without your
yes, and it commits nothing except `/atlasmd:end` when you type it.

## In a session

The first line of what Claude gets at the start:

```
atlasmd: api has 4 files to read at the start, about 1,411 tokens.
```

A refused edit:

```
atlasmd: this change to api/routes.py is refused until you read the files that atlasmd.toml lists for "api":
```

Claude reads the files and makes the change again. `amd why` shows the last refusal.

## The files

The folder says when Claude reads a file. The name gives the order, the date or the number,
then the subject in lower case with hyphens.

| Folder | When Claude reads it | Name |
|---|---|---|
| `docs/start/` | at every start and after every compaction | `10-map.md`, `20-open-items.md`, `30-state.md`, `40-way-of-work.md` |
| `<folder>/README.md` | before a change in that folder | `README.md` |
| `docs/decisions/` | before a change in a folder that depends on it | `P001-subject.md`, plus `README.md` as the index |
| `docs/plans/` | when the work starts | `subject.md`. Built: move to `docs/archive/` |
| `docs/notes/` | when the subject comes up | `2026-10-16-subject.md` |
| `docs/archive/` | never at the start | the old name |

The hook refuses a new Markdown file with a wrong name. `amd init` writes the rules for
new files, plans, notes and decisions into `docs/start/40-way-of-work.md`, and `amd check`
reports what breaks them. `/atlasmd:end` makes the fixes at the end of a session.

## atlasmd.toml

`amd init` writes every key with a comment. The parts that matter:

```toml
group = "my-project"        # repositories with the same group share their docs/start/

[start]
budget = 30000              # limit for docs/start/, in tokens

[guard]
mode = "deny"               # deny, remind or off

[[area]]
name = "api"
paths = ["api/"]
pack = ["api/README.md", "docs/decisions/P003-time-is-utc.md"]
```

With this `[[area]]`, a change in `api/` is refused until Claude read both files. `amd
config` opens a screen with every repository, its settings and its files. `amd config
--list` prints the same as a table.

## Commands

| Command | What it does |
|---|---|
| `amd setup` | the six steps, once after the install |
| `amd init` | write `atlasmd.toml` and `docs/start/`, overwrite nothing |
| `amd init --undo` | remove what `amd init` made, while none of it changed |
| `amd area <folder>` | README and `[[area]]` entry for one code folder |
| `amd check` | report what to fix |
| `amd map` | write the tree of the Markdown files into `docs/start/10-map.md` |
| `amd scan` | print every Markdown file with its tokens |
| `amd status` | which files this session read |
| `amd why` | the last refused edit |
| `amd end` | what is not committed or pushed, and the first message for a fresh chat |
| `amd config` | every repository, its settings and its files. `--remove <path>` removes atlasmd from one |
| `amd meter` | the tokens of the sessions, on against off |
| `amd statusline` | one line for the status line of Claude Code |
| `amd set <key> <value>` | your two settings: `offer_setup`, `token_chars` |

In a session, the skills `/atlasmd:init`, `/atlasmd:area`, `/atlasmd:check`, `/atlasmd:map`,
`/atlasmd:status`, `/atlasmd:why` and `/atlasmd:end` run these for you and explain the result.

## The meter

Claude Code writes the token counts of every request into the transcript of the session.
The hook adds them up per session in `~/.claude/plugins/data/amd/meter/`. `amd meter`
shows the newest session and the history, and compares two sessions:

```
                     off          on    difference
start          8,462,173   1,204,881    -7,257,292  86% saved
total        390,751,680  98,005,112  -292,746,568  75% saved
```

For the off side, start one session with `ATLASMD=off claude`. The hook then gives
nothing and refuses nothing, and the meter marks the session off.

For a status line under the chat, put this into `~/.claude/settings.json`. It then shows
`atlasmd on · start 16,101 · session 212,480 · 1 compaction`:

```json
{ "statusLine": { "type": "command", "command": "amd statusline" } }
```

## What it runs, reads and keeps

The hook is a Python script that Claude Code runs on your computer at the start of a
session, before an edit, after a read and after a compaction. It reads `atlasmd.toml` and
the Markdown files that it names, the paths of the files that Claude reads and changes,
and the transcript of the session for the token counts. It keeps the paths of read files,
the counts and the dates under `~/.claude/plugins/data/amd/`, never the text of a message.
The hook and the `amd` command send nothing anywhere. One skill sends data: `/atlasmd:end`
tells Claude to run `git push`, which sends your commits to the remote of your repository,
as a push without the plugin does. [PRIVACY.md](PRIVACY.md) has the full list.

The hook never approves a tool call. It refuses one with a reason, or it says nothing. The
plugin reads these variables of the environment by name, and no other: `ATLASMD`,
`ATLASMD_DATA`, `CLAUDE_PLUGIN_OPTION_OFFER_SETUP`, `CLAUDE_PROJECT_DIR`, `NO_COLOR`, `PATH`,
`SHELL` and `TERM`, and the home folder.

## Uninstall

```
claude plugin uninstall atlasmd@atlasmd
```

The files of atlasmd stay in `~/.claude/plugins/data/amd/` until you delete that folder.
Your repositories keep `atlasmd.toml` and `docs/start/` as plain files.

MIT license, see [LICENSE](LICENSE).
