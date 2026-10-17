# atlasmd

![tests](https://github.com/simon-init/atlasmd/actions/workflows/tests.yml/badge.svg)

atlasmd is a plugin for Claude Code. It tells Claude which Markdown files of a repository
to read at the start of a session. Before Claude changes a file in a folder, it makes sure
that Claude read the files for that folder. It is written in Python, needs no other
package, and comes with a command line, `amd`.

## Why a project keeps what Claude must know in Markdown files

Claude starts every session with an empty memory. Everything that Claude knows in a
session is text that it holds in memory, called the context. That is your messages, its
answers, and the files that it read. When the session ends, the context is gone. The next
session knows the code that it reads, and nothing more. It does not know why a decision
was made, what is open, what you agreed on last week, or how you want the work done.

The same happens inside a long session. When the chat grows too long for the context,
Claude Code compacts it: it replaces the chat with a short summary. This is a compaction.
After a compaction, Claude has the summary, and the files that it read are gone from the
context.

So a project writes what Claude must know into Markdown files in the repository. They
hold the decisions and their reasons, the state of the work, the open items, the rules,
and what each folder of code does. The next session reads these files and continues where
the last one stopped. The Markdown files are the memory of the project.

These files grow. In the project that atlasmd was built for, they grew to about 580,000
tokens. Every session read all of them at its start, and again after every compaction. A
token is the unit in which the model counts text, about 2.5 characters of English or code.
One start cost 13 percent of the usage limit of five hours. That is the problem that
atlasmd solves. It answers two questions for every Markdown file. Does a session read it
at the start? Before a change in which folder must Claude read it?

## What atlasmd does

atlasmd is a hook inside Claude Code. A hook is a small program that Claude Code runs at
fixed moments. The moments are: when a session starts, before Claude uses a tool, after a
tool ran, and after a compaction. At these moments, atlasmd does four things:

1. **At the start of a session, and after every compaction,** it gives Claude the
   Markdown files in `docs/start/` of the repository, not the whole repository. Claude
   Code lets a hook give Claude at most 10,000 characters of text at one time. When the
   files in `docs/start/` together are shorter than that, Claude gets their full text at
   once. When they are longer, Claude gets the full text of the first files up to that
   limit. After that text come the names of the files that did not fit. Claude then reads
   each of these files itself, with one Read call per file. In both cases, a fresh session
   and a session after a compaction start with the same files.
2. **Before every edit,** it looks whether the file is in a folder that `atlasmd.toml`
   lists. `atlasmd.toml` is the settings file of atlasmd at the root of the repository.
   For each listed folder, it names the files that Claude must read before a change
   there. Examples are the README of the folder and the decisions behind the code. If
   Claude did not read these files in this session, the hook refuses the edit and names
   the files. Claude reads them and makes the edit again. After a compaction, Claude reads
   them again before its next edit there. The hook also refuses a new Markdown file whose
   name breaks the name rule of its folder. When Claude writes a new source file in a
   folder that `atlasmd.toml` does not list, the hook tells Claude once. The message says:
   write the README.md of the folder and its entry in `atlasmd.toml`.
3. **After every compaction,** it writes one line to the file `compacts.log`. The line
   holds the date and time, the repository, who started the compaction (you or Claude
   Code), and the size of the summary in characters. So you can see what each compaction
   cost.
4. **At every one of these moments,** it adds the token counts of the session to one
   record per session. Claude Code writes every session into a file, the transcript. Each
   answer of the model in it holds the token counts of its request. The command
   `amd meter` shows these records and compares a session with atlasmd on against a
   session with atlasmd off. See [The meter](#the-meter).

Repositories that belong together, for example an API, a web app and the server that
runs them, can share their files of `docs/start/`. See
[Several repositories as one group](#several-repositories-as-one-group).

## What you need

- Claude Code. The in-session install needs version 2.1.275 or newer.
- Python 3.11 or newer. The plugin installs no package.
- git.
- The three screens, `amd setup`, `amd config` and `amd meter`, need the Python module
  curses. Linux and macOS have it. On Windows, install it with `pip install
  windows-curses`. Every other command works without it.

## Install

Claude Code gets a plugin from a marketplace. A marketplace is a git repository with a
file that lists plugins. The atlasmd repository is its own marketplace, with one plugin in
it, named `amd`. An install does two things on your computer:

- It clones the repository into `~/.claude/plugins/marketplaces/atlasmd/` and remembers it
  as a marketplace named `atlasmd`.
- It copies the plugin into `~/.claude/plugins/cache/atlasmd/amd/<version>/`. Then it
  writes one entry into `~/.claude/settings.json`, which turns the plugin on in every
  session on this computer.

The repository is private at this time. Claude Code clones it with the git access that
your computer already has. It uses SSH when your SSH key works for github.com, else HTTPS
with a stored credential. It never asks for a password. If neither works, the first
command fails and says so.

Nothing changes in your repositories at the install. The hook starts to work at the next
session. Until you set a repository up, it does one thing there: it tells Claude once
that `/amd:init` sets atlasmd up. See [Set up a repository](#set-up-a-repository).

There are three ways to install atlasmd.

**In a terminal.** The first command clones the repository and remembers it as a
marketplace. The second command copies the plugin out of it and turns it on. Claude Code
does not have to run.

```
claude plugin marketplace add simon-init/atlasmd
claude plugin install amd@atlasmd
```

**In a Claude Code session.** This one command does both steps. Claude Code first shows
the repository that it resolved and asks you to confirm the marketplace. Then it opens
the plugin in its plugin panel. There you pick where the plugin is on: for you in every
project, or in this repository only. It needs Claude Code 2.1.275 or newer.

```
/plugin install amd --marketplace simon-init/atlasmd
```

**From a clone on your computer.** This is for a person who changes the plugin. With a
marketplace from a local folder, Claude Code runs the plugin in place, from that folder.
A change in the folder is live at the next session start, without a new install. The
first command clones the repository into `~/atlasmd`. The second command remembers that
folder as the marketplace. The third turns the plugin on.

```
git clone https://github.com/simon-init/atlasmd ~/atlasmd
claude plugin marketplace add ~/atlasmd
claude plugin install amd@atlasmd
```

### The command amd in your terminal

In a Claude Code session, the skills of atlasmd run `amd` by the full path of the plugin,
so Claude needs nothing more. In your own terminal, your shell finds a command only in the
folders of your PATH. There are three ways to run `amd` there.

**By its full path.** Nothing to set up. After an install from GitHub, the command is in
the clone of the repository:

```
~/.claude/plugins/marketplaces/atlasmd/bin/amd
```

After an install from a clone in `~/atlasmd`, it is `~/atlasmd/bin/amd`. Every command of
this README that starts with `amd` works with the full path in its place, for example
`~/.claude/plugins/marketplaces/atlasmd/bin/amd check`.

**With a link that the setup makes.** `amd setup` has a step named "The command amd". If
you pick "Put amd on my PATH now" there, the setup makes two things. It makes the folder
`~/.local/bin` when it is missing, and a link `~/.local/bin/amd` that points at `bin/amd`
of the plugin. A link is a second name for a file, so `amd` then runs `bin/amd`. Nothing
else in your home folder changes. The setup then says whether `~/.local/bin` is on the PATH of your shell.
When it is not, it gives you the one line for the start file of fish, zsh or bash, and you
add that line yourself. If you pick "Not now", the setup shows the command below, to run
later.

**With a link that you make yourself.** On Linux and macOS, this command makes the same
link as the setup, for an install from GitHub. It needs the folder `~/.local/bin` to
exist and to be on your PATH.

```
ln -s ~/.claude/plugins/marketplaces/atlasmd/bin/amd ~/.local/bin/amd
```

After an install from a clone in `~/atlasmd`, the first path is `~/atlasmd/bin/amd`.

On Windows, the setup does not change the PATH. Add the `bin` folder of the plugin to your
PATH yourself. The command in that folder is `amd.cmd`. After an install from GitHub, the
folder is:

```
%USERPROFILE%\.claude\plugins\marketplaces\atlasmd\bin
```

## Set up a repository

A setup makes two things in a repository:

- `atlasmd.toml` at the root. It holds the settings of atlasmd for this repository, with
  a comment on each key. The most important part of it is the `[[area]]` entries. One
  entry names a folder, or a group of folders and files, and the files that Claude must
  read before it changes a file there. The section
  [The settings of a repository](#the-settings-of-a-repository-atlasmdtoml) shows one.
- The folder `docs/start/` with four Markdown files. Claude gets these files at the start
  of every session. They say what the project is, where its files are, what is open,
  where the work stands, and the rules. The section
  [Where the Markdown files go, and their names](#where-the-markdown-files-go-and-their-names)
  gives each file.

A setup does not need a Claude Code session. The hook reads `atlasmd.toml` at the start
of every session. So the first session in the repository after the setup gets the four
files. From then on, the hook refuses an edit in a listed folder until Claude reads the
files named for it.

There are three ways to set up a repository.

**In a Claude Code session, with `/amd:init`.** This is the best way for a repository
that has Markdown files already, because Claude fills the four files from them. Claude
first runs `amd scan`, which lists every Markdown file with its size and the folders that
hold code. Claude reads the `CLAUDE.md` and the README at the root, and nothing more. Then
Claude proposes the setup to you in one message, as three lists, and asks once for your
yes or your corrections:

- the `[[area]]` entries: for each folder with code, a name, and the files that Claude
  must read before it changes a file there,
- the text for the four files of `docs/start/`, and which existing files it comes from,
- the Markdown files to move into `docs/decisions/`, `docs/plans/`, `docs/notes/` or
  `docs/archive/`, and the files to give a new name.

Claude writes nothing before your yes. After it, Claude writes `atlasmd.toml` and the four
files. It moves the files that you agreed to move with `git mv`, and corrects the links
that a move breaks. It commits nothing unless you ask. Type this in a session, in the
repository:

```
/amd:init
```

**In a terminal, with `amd init`.** This is the way for a new repository, or when you want
to fill the files yourself. The command writes:

- `atlasmd.toml`, with every default and a comment on each key,
- the four files of `docs/start/`, with their headings and nothing under them,
- the empty folders `docs/decisions/`, `docs/plans/`, `docs/notes/` and `docs/archive/`.

It overwrites nothing. A file or a folder that exists stays as it is, and the command says
what it made and what it kept. After it, you fill the four files, and you add one
`[[area]]` entry for each folder with code. The command `amd area <folder>` adds one entry
with a README. Run `amd init` in the root of the repository, or in a folder under it:

```
amd init
```

**In a terminal, with `amd setup`.** This is the way once after the install. It opens a
screen with six steps, printed one under the other as a terminal does. The steps are:
what atlasmd does, how it works, the command `amd` on your PATH, your own two settings,
this repository, and three commands to remember. On the step "This repository", it offers
to run `amd init` in the repository that you are in. The screen writes your settings at
the last step. You can run it again at any time. It changes only your two settings, makes
the link only when you pick it, and `amd init` overwrites no file. Run it in the root of
the repository:

```
amd setup
```

After a setup in the terminal, `/amd:init` in a session still helps. It fills the four
files from the Markdown files of the repository and proposes the `[[area]]` entries.

### What a session looks like after the setup

At the start of a session in the repository, Claude gets the four files of `docs/start/`.
The first line of that text says where they come from, for example:

```
atlasmd: my-api has 4 files to read at the start, about 3,200 tokens.
```

Under it come the rules of the hook in a few sentences, and then the files. Claude knows
the project before you write your first message.

When Claude is about to change a file in a listed folder without a read of the files named
for it, the edit is refused. Claude gets a text that starts like this and then names the
files:

```
atlasmd: this change to api/routes.py is refused until you read the files that atlasmd.toml lists for "the API":
```

Claude reads the files and makes the change again. You see the refusal and the reads in
the chat. The command `amd why` shows the last refused edit, and `/amd:why` explains it.

After a compaction, Claude gets the four files again, and the hook forgets which files
Claude read before the compaction. So the next edit in a listed folder reads the files
named for it again.

## Where the Markdown files go, and their names

The folder of a file says when Claude reads it. The name of the file says the order, the
date or the number, and the subject. The subject is one to four words, in lower case,
joined by hyphens, in ASCII. The name has no prefix for the kind of file, because the
folder gives the kind.

| Folder | When Claude reads it | Name |
|---|---|---|
| `docs/start/` | at the start of every session and after every compaction, in name order. The hook gives these files to Claude | `NN-<subject>.md`. Two digits set the order: `10-map.md`, `20-open-items.md`, `30-state.md`, `40-way-of-work.md` |
| `<code folder>/README.md` | before a change in that folder, when an `[[area]]` entry in `atlasmd.toml` names the README under `pack` | `README.md`, next to its code |
| `docs/decisions/` | before a change in a folder, when an `[[area]]` entry names the decision under `pack` | `P<NNN>-<subject>.md`, one file per decision, and `README.md` as the index with one line for each decision |
| `docs/plans/` | when the work of the plan starts | `<subject>.md`. When the plan is built, the file moves to `docs/archive/` |
| `docs/notes/` | when the subject of the note comes up | `YYYY-MM-DD-<subject>.md`. The date comes first, so the files sort by time |
| `docs/archive/` | never at the start. This folder holds old files | the name that the file had |

`pack` is the key of an `[[area]]` entry that names the files to read before a change.
The four files that `amd init` writes into `docs/start/`:

- `10-map.md`, the map file. It says what the project is, which files to read before a
  change in each folder, and where each kind of fact lives. It ends with the names of
  every Markdown file of the repository, as a tree. `amd map` writes the table of the
  folders and the tree.
- `20-open-items.md`: one line for each open item, with the path of the file that holds
  the details.
- `30-state.md`: where the work stands. `/amd:end` writes it again at the end of a
  session.
- `40-way-of-work.md`: the rules that Claude follows in every session.

`amd check` reports a file whose name does not match the rule of its folder. It also
reports a Markdown file that is not in `docs/start/`, not under `pack`, and not in a
folder under `[naming]`. No rule says when Claude reads such a file. The check
does not report files at the root of the repository, files in folders whose names start
with a dot, `CLAUDE.md`, `AGENTS.md` and `SKILL.md`. These files are for people and
for Claude Code. The check renames nothing.

## How the Markdown files live

The files grow, so the project needs rules for when a file is made, moved and removed.
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
| `no-readme` | `<folder>/ has source files and no README.md. Write one, or run /amd:area <folder>.` A folder counts when it holds a file with an extension that `amd scan` counts as source. It must have no README.md in it or in a folder above it, below the root. `docs/`, folders whose names start with a dot, `node_modules`, `.venv`, `tests` and `test` do not count. | `folders` |
| `no-entry` | `<folder>/ has source files and no [[area]] entry in atlasmd.toml lists it. Run /amd:area <folder>.` The same folders, when the paths of no `[[area]]` entry hold a source file of the folder. | `folders` |
| `dead-entry` | `the [[area]] "<name>" lists <path>, which does not exist. Remove it or fix the path.` For each path under `paths`. | `folders` |
| `stale-readme` | `<README> did not change in the last <N> commits that changed <folder>/. Update its State section.` For each README.md under `pack`. The count starts at the last commit of the README. When the paths of the `[[area]]` entry hold the folder of the README, the commits that change that folder count. When the paths lie inside that folder, the commits that change those paths count, and the text names them. | `stale_readme`, 15 commits |
| `dead-pointer` | `docs/start/20-open-items.md names <path>, which does not exist. Fix the line or remove it.` A path is a text in backticks that has a `/` or ends in `.md`, from the root of the repository. A text with a space, a URL and a text with `<` do not count. The file is `start.items`. | `dead_pointers` |
| `orphan-plan` | `docs/plans/<file> is named by no line of docs/start/20-open-items.md. Add a line, or move the plan to docs/archive/ if it is built.` | `plans` |
| `orphan-note` | `docs/notes/<file> is named by no Markdown file and is <days> days old. Point at it, or move it to docs/archive/.` The age comes from the date at the start of the name, else from the date of the last commit of the file. The tree that `amd map` writes and the files in `docs/archive/` do not count as a name. | `notes`, 30 days |
| `no-index-line` | `docs/decisions/<file> has no line in docs/decisions/README.md. Add the line.` The number at the start of the file name must be in the index, for example `P012` or `P12` for `P012-policy.md`. | `decisions` |
| `stale-state` | `<state file> did not change in the last <N> commits. Rewrite it with /amd:end.` | `stale_state`, 20 commits |

The folders `docs/plans/`, `docs/notes/` and `docs/decisions/` are the folders under
`[naming]` whose last names are `plans`, `notes` and `decisions`. When a repository does
not have one of these folders, its check does not run. The checks that count commits
run only in a git repository with a commit.

## The settings of a repository: `atlasmd.toml`

The file is at the root of the repository. `amd init` writes it with every default and a
comment on each key. Every path is relative to the folder of `atlasmd.toml`, with `/`
as the separator.

| Key | Default | What it does |
|---|---|---|
| `group` | none | Repositories with the same group name share their `docs/start/` at the start of a session. The key stands at the top of the file, above the first table. See [Several repositories as one group](#several-repositories-as-one-group). |
| `start.dir` | `"docs/start"` | At the start of a session and after a compaction, Claude gets the Markdown files of this folder, in name order. |
| `start.files` | `[]` | Paths in order. When it has paths, the hook uses them, not `start.dir`. |
| `start.also` | `[]` | More folders or files. Claude gets them after the files above. |
| `start.budget` | `30000` | The limit for these files, in estimated tokens. Above it, the hook gives Claude the names of the files and a warning, not their text. |
| `start.inject` | `true` | It says whether the start files go in as text, when they fit, or always as the names of the files. `true`: Claude gets the text of the start files when they fit in 10,000 characters. `false`: Claude always gets the names of the files and reads each one. The screen of `amd config` calls it "start files as text". |
| `start.state` | `"docs/start/30-state.md"` | The file that says where the work stands. `/amd:end` writes it again. |
| `start.map` | `"docs/start/10-map.md"` | The map file. `amd map` writes the tree of every Markdown file and the table of the `[[area]]` entries into it. A subagent gets it at its start. A subagent is a second Claude that the session starts for one task. |
| `start.line` | `"Say where things stand."` | The first message that a person sends in a fresh chat. `amd end` and `/amd:end` show it. |
| `start.items` | `"docs/start/20-open-items.md"` | The file of the open items. `amd check` reports a path in backticks in it that does not exist, and a plan that it does not name. |
| `guard.mode` | `"deny"` | `deny`, `remind` or `off`. See [How the hook refuses an edit](#how-the-hook-refuses-an-edit). |
| `guard.bash` | `true` | The hook also looks at the Bash commands that write a file. |
| `guard.new_folders` | `"remind"` | `remind` or `off`. With `remind`, the hook tells Claude once in the session when it writes a new source file in a folder that no `[[area]]` entry lists. The message says: write the README.md of the folder and its entry. |
| `agents.inject` | `"map"` | What a subagent gets at its start: `map` (the file in `start.map`), `start` (the same files as a session) or `none`. |
| `private.files` | `[]` | Markdown files that Claude gets at the start but that git never commits. `amd init` writes them into `.git/info/exclude`, the file where git keeps the paths that it ignores on this computer only. |
| `[naming]` | four rules | For each folder, the regular expression that a file name must match. The rule of the deeper folder wins. `amd check` reports a name that breaks the rule, and the hook refuses a Write of a new Markdown file whose name breaks it. |
| `check.folders` | `true` | `amd check` reports a folder with source files and no README.md or no `[[area]]` entry, and a path of an `[[area]]` entry that does not exist. |
| `check.stale_readme` | `15` | `amd check` reports a README.md under `pack` that did not change in the last 15 commits that changed its folder. `0` turns it off. |
| `check.dead_pointers` | `true` | `amd check` reports a path in backticks in `start.items` that does not exist. |
| `check.plans` | `true` | `amd check` reports a file in `docs/plans/` that no line of `start.items` names. |
| `check.notes` | `30` | `amd check` reports a note in `docs/notes/` that no Markdown file names and that is older than 30 days. `0` turns it off. |
| `check.decisions` | `true` | `amd check` reports a file in `docs/decisions/` without a line in `docs/decisions/README.md`. |
| `check.stale_state` | `20` | `amd check` reports the file in `start.state` when it did not change in the last 20 commits. `0` turns it off. |
| `[[area]]` | none | One table for each folder or group of folders, with `name`, `paths` and `pack`. `paths` names folders or files. `pack` names the files that Claude must read before it changes a file in `paths`. |

An `[[area]]` entry looks like this:

```toml
[[area]]
name = "the API"
paths = ["api/"]
pack = ["api/README.md", "docs/decisions/P003-time-is-utc.md"]
```

With this entry, the hook refuses a change to a file in `api/` until Claude reads
`api/README.md` and `docs/decisions/P003-time-is-utc.md`. For example, the README of
`api/` says that every time is stored as UTC. An agent that did not read it writes local
time, and the bug sits in the data for weeks. With the entry, Claude knows the rule before
it writes code there.

A path that ends in `/` is a folder. A path without `/` at its end is one file. An entry
under `pack` can end in `#<anchor>`. Then the refusal names that section of the file,
and a read of the file counts.

## Several repositories as one group

A project can have more than one repository. Give each repository of the project the
same `group` in its `atlasmd.toml`, at the top of the file, above the first table:

```toml
group = "my-project"
```

The name is letters, digits and hyphens. `amd init` writes the key as a comment. The
command `amd config --set . group my-project` writes the value, and the key `g` on the
screen of `amd config` types it.

atlasmd keeps a table of the repositories that it knows in the file
`~/.claude/plugins/data/amd/projects.toml`. This README calls it the repository table.
Each row has the path of the repository, the name of its folder, its group and the time
of the last session start there. `amd init` and `amd config` add the repository where
they run. The hook adds or refreshes the row at every session start in a repository with
`atlasmd.toml`. A row whose folder does not exist leaves the table at the next write.

At the start of a session in a repository with a group, Claude gets the files of this
repository first, as without a group. Then Claude gets the files of `start.dir` or
`start.files` of every other repository with the same group in the repository table. They
come in the order of the names of the repositories. Claude gets each file once. The first
line of the text says so:

```
atlasmd: api and 2 more repositories of the group "my-project" have 9 files to read at the start, about 17,106 tokens.
```

The limit of 10,000 characters applies as for one repository: the text of the first
files, then the names of the rest. `start.also` stays for a folder or a file that you
name by hand. The hook reads the group of each repository from its `atlasmd.toml` at the
session start, not from the repository table.

`amd check` prints one line under `start`: the group and the repositories that it found,
or that the group has no other repository on this computer.

A repository gets into the repository table only when `amd init` or `amd config` runs
there, or when a session starts there. If no session started yet in a repository of the
group, run `amd config --list` in it once.

## The screen of amd config

`amd config` opens a screen with four stations on a route:

1. **About.** What atlasmd does in three sentences. How to set up a repository in three
   steps: `amd init` in the root, or `/amd:init` in a session, then `amd map`, then
   `amd check`. Every command of `amd` with one line each, the seven skills, and the
   three ways to turn atlasmd off. `↑` and `↓` scroll.
2. **Repositories.** The repository table: the name, the path, the group, `guard.mode`,
   "start files as text" (`start.inject`), `start.budget`, the start files and their
   tokens, and the number of Markdown files. The table sorts by the name of the group,
   with the repositories without a group last, and by name inside a group. The start
   files are the files that a session there gets at the start. When some come from
   `start.also` or from the group, the word follows the number. `4` are the repository's
   own files. `4 from group` come from the other repositories of the group.
   `2 + 3 from also` are two own files and three from `start.also`. A repository whose
   sessions get nothing shows `0`, and a sentence under the table says so. On a row, `g`
   types the group, and the row moves to its group at once. `m` changes `guard.mode` to
   deny, remind or off, `i` changes "start files as text", and `b` types `start.budget`.
   A changed value shows in the accent color until you save it. `r` removes the
   repository from the table after one question. Enter opens the settings of the row.
3. **The settings of one repository**, with its name on the route. The values of its
   `atlasmd.toml`, its `[[area]]` entries and your own settings. You can change
   `start.budget`, "Give the start files as text when they fit in 10,000 characters"
   (`start.inject`), `guard.mode`, what a subagent gets (`agents.inject`) and your own
   settings there. The screen shows the `[[area]]` entries but cannot change them.
4. **Files.** The Markdown files of the repository as a tree, from `amd scan`, with
   their tokens. The word `private` marks a file that `[private] files` names. `p` on a
   file adds it to `[private] files` and to `.git/info/exclude`, so git does not commit
   it. `p` on a private file removes it from both. `p` writes at once.

`r` and `amd config --remove <path>` remove a repository from the repository table, and
nothing else. `atlasmd.toml`, `docs/start/` and every other file of the repository stay.
The other repositories of its group stop getting its `docs/start/`. `amd init`,
`amd config` or the next session start in that repository puts it back. To turn atlasmd
off in a repository and keep it in the table, set `guard.mode` to off with `m`: the hook
then refuses no edit there. To stop the start files too, delete `atlasmd.toml` in that
repository.

`tab` goes to the next station, shift-tab to the one before, and Escape to Repositories.
`s` saves, `q` quits. In a repository, the screen opens on the settings of that
repository. Outside a repository, it opens on Repositories.

A save writes each changed key into `atlasmd.toml` of its repository. A key that exists
gets the new value in its place. A key that stands as a comment, such as
`# group = "my-project"`, loses the `#` and gets the value. A missing key goes after the
last key of its table. Every other line and every comment stays as it is.

Four plain forms do the same without the screen, for a script or a skill:

| Command | What it does |
|---|---|
| `amd config --list` | Prints the repository table, and the sentence for each repository whose sessions get nothing at the start. |
| `amd config --set <path> <key> <value>` | Writes one key into `atlasmd.toml` of the repository at `<path>`, or of the repository of the table with that name. The keys are `group`, `guard.mode`, `start.inject` and `start.budget`. |
| `amd config --json` | Prints the repository table as JSON. `start_files` and `start_tokens` are the files that a session gets at the start, `own_files` the files of the repository itself, and `start_from` is `also`, `group`, both or empty. |
| `amd config --remove <path>` | Removes the repository at `<path>`, or the repository of the table with that name, from the repository table. No file of the repository changes. |

## The meter

The meter counts the tokens of each session. With it, you can compare a session with
atlasmd on against a session with atlasmd off in the same repository.

Claude Code writes each session into a transcript, a file with one line of JSON per
event, under `~/.claude/projects/`. Each answer of the model in the transcript holds the
token counts of its request: `input_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens` and `output_tokens`. At every hook event of a session in a
repository with `atlasmd.toml`, the hook reads the lines that the transcript got after its
last read. The events are the session start, each tool call that the hook sees, and the
compaction. The hook adds the counts of each new request to one record per session, in
`~/.claude/plugins/data/amd/meter/<session id>.json`. It reads the counts, the model, the
compaction lines and the names of the tools, never the text of a message.

A token count of the meter is the sum of the four counts of each request. Most of it is
cache reads, because each request reads the whole context again. These are the numbers
that Claude Code wrote, not an estimate of atlasmd. The one estimate is the bar of
`docs/start/`, below.

The record of a session holds:

- the repository and its group, and whether atlasmd was on,
- the time of the first request, and the model,
- the four counts in total, and the number of requests,
- `start`: the tokens from the start of the session up to the first Edit or Write, with
  the request that made it. This is what the start of a session costs,
- one block for each compaction cycle with its counts, and the number of compactions. A
  cycle is the part of a session between two compactions.

A subagent has its own transcript, and the meter does not count it.

### amd meter

`amd meter` in a repository opens a screen. At the top it shows the newest session of the
repository:

- `docs/start/`: a bar in the accent color with the estimated tokens of the files that
  the hook gave at the start, against `start.budget`.
- `cycle`: the cycle that the session is in, with a bar of the tokens in the context at
  its last request, against the size of the context.
- `start`: the tokens up to the first Edit or Write.
- `session`: the tokens so far, the requests and the compactions.

Under it, the history of the repository: one row for each session, with the date and
time, on or off, the start tokens, the total and the compactions. Enter on two rows, or
`c` on a row, opens the comparison. `c` compares the row with the newest session of the
other kind, off with on. The comparison has a column for off, a column for on, and a
column with the difference and the percent saved. `q` quits. The comparison looks like
this, here with example numbers:

```
                     off          on    difference
start          8,462,173   1,204,881    -7,257,292  86% saved
total        390,751,680  98,005,112  -292,746,568  75% saved
requests             841         210          -631  75% saved
compactions            4           1            -3  75% saved
```

The plain forms:

| Command | What it does |
|---|---|
| `amd meter --list` | Prints the newest session and the history. In a folder without `atlasmd.toml` above it, it prints the sessions of every repository, the newest first. |
| `amd meter --compare <session> <session>` | Prints the comparison of two sessions. The first characters of a session id are enough. |
| `amd meter --json` | Prints the records of this repository as JSON. |

### The status line

Claude Code can show one line under the chat, the status line. It runs a command of your
choice after each answer of the model and shows what the command prints. `amd statusline`
is such a command. It prints one line with the state of atlasmd, the tokens up to the
first edit, the tokens of the session, and the compactions:

```
atlasmd on · start 16,101 · session 212,480 · 1 compaction
```

To get this line under your chat, put this setting into `~/.claude/settings.json`, the
settings file of Claude Code for your user. If the file has other settings, add the key
`statusLine` next to them:

```json
{
  "statusLine": {
    "type": "command",
    "command": "amd statusline"
  }
}
```

If `amd` is not on the PATH of Claude Code, write the full path of `bin/amd` in
`command`. Claude Code runs the command after each answer of the model and gives it the
data of the session as JSON. The line shows Claude Code's own numbers. They are the counts
that Claude Code wrote into the transcript, and the size of the context that Claude Code
gives the status line.

### A session without atlasmd

The comparison needs a session with atlasmd off in the same repository. The environment
variable `ATLASMD=off` gives you one without an uninstall. In such a session, the hook
gives no files at the start, refuses no edit, gives no reminder and makes no offer of
`/amd:init`. The meter still records the session, marked off, so `amd meter` and the
status line say `off` for it. The hook reads `ATLASMD` at every event. Start Claude Code
so, in a terminal:

```
ATLASMD=off claude
```

## Your own settings

Two settings apply to every repository on your computer. `amd set` writes them into
`~/.claude/plugins/data/amd/settings.toml`, and `amd setup` and `amd config` show them:

| Key | Default | What it does |
|---|---|---|
| `offer_setup` | `yes` | In a repository without `atlasmd.toml`, the hook tells Claude once that `/amd:init` writes `atlasmd.toml` and `docs/start/`. |
| `token_chars` | `2.5` | The number of characters per token. atlasmd divides the characters of a file by this number to estimate its tokens. 2.5 is a careful value for English and code. |

The plugin also has the option `offer_setup` in Claude Code, under `/plugin` and
"Configure options". When that option is set, it wins over the settings file.

## The commands

| Command | What it does |
|---|---|
| `amd` | Prints the logo, one paragraph on what atlasmd does, and the commands. |
| `amd setup` | Opens a screen with six steps. Run it once after the install. You can run it again: it changes only your two settings, the link `~/.local/bin/amd` when you pick it, and `amd init` overwrites no file. |
| `amd config` | Opens a screen with the commands, the repository table, the settings of each repository and its Markdown files. See [The screen of amd config](#the-screen-of-amd-config). `--list`, `--set`, `--json` and `--remove` do the same without the screen. |
| `amd scan` | Prints every Markdown file with its size in KB and its estimated tokens, the folders with source files and a README, and the files that `CLAUDE.md` names. `--json` gives the same as JSON. |
| `amd init` | Writes `atlasmd.toml`, the four files of `docs/start/`, and the folders `docs/decisions/`, `docs/plans/`, `docs/notes/` and `docs/archive/`. It overwrites nothing. `--areas-json <file>` adds the `[[area]]` entries of a JSON file. `--dry-run` writes nothing. |
| `amd check` | Reports the tokens of the files in `docs/start/` against `start.budget` and against the 10,000 characters of a hook, files under `pack` that do not exist, `[[area]]` entries whose paths overlap, file names that break the rule of their folder, Markdown files that no rule tells Claude to read, a map file that is out of date, and the nine findings of [What amd check reports on the folders and the Markdown files](#what-amd-check-reports-on-the-folders-and-the-markdown-files). Exit code 1 on a problem. `--json` for the skill. |
| `amd map` | Writes the tree of every Markdown file and the table of the `[[area]]` entries into the map file, between marker lines. The text outside the markers stays. |
| `amd area <folder>` | Writes `<folder>/README.md` from a template when the folder has none, adds an `[[area]]` entry with `paths = ["<folder>/"]` and `pack = ["<folder>/README.md"]` at the end of `atlasmd.toml`, and writes the map file. The text and the comments of `atlasmd.toml` stay. `--name <name>` gives the name of the entry. The default is the name of the folder. It refuses a folder that does not exist, that holds no source files, or that an `[[area]]` entry lists already. |
| `amd status` | Shows, for each `[[area]]`, whether this session read all, some or none of the files under `pack`. It also shows the `[[area]]` entries where the session read a file or had an edit refused, and the last compaction. `--session <id>` and `--agent <id>` select the session or the subagent. |
| `amd why` | Shows the last edit that the hook refused, with the text that Claude got. `--session <id>` selects a session. |
| `amd end` | Shows what is not committed or not pushed, and the first message for a fresh chat, from `start.line`. Exit code 1 when something is not committed or not pushed. |
| `amd meter` | Opens a screen with the tokens of the sessions in this repository, and compares a session with atlasmd off against one with atlasmd on. See [The meter](#the-meter). `--list`, `--compare` and `--json` do the same without the screen. |
| `amd statusline` | Prints one line for the status line of Claude Code. See [The status line](#the-status-line). |
| `amd set <key> <value>` | Writes one of your own settings. |
| `amd version` | Prints the version. |

`amd check`, `amd map`, `amd area`, and `amd meter` without `--list`, need `atlasmd.toml`.
In a folder without `atlasmd.toml` in it or above it, they print this sentence and exit
with code 1:

```
Run this in a repository that has atlasmd.toml, in its root or in a folder under it. amd init sets one up.
```

`amd`, `amd setup`, `amd config`, `amd meter --list` and `amd version` work in any
folder. Every other command works without `atlasmd.toml`. `/amd:init` runs `amd scan` and
`amd init` before the file exists.

In a Claude Code session, seven skills run the command line for you. A skill is a text
that tells Claude what to do when you type its name:

| Skill | What it does |
|---|---|
| `/amd:init` | After one question, writes `atlasmd.toml`, fills `docs/start/`, names the files to read before a change in each folder, and moves the files that you agree to move. |
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

The hook keeps a record of the files that each session read: one small file per session
and one per subagent, in `~/.claude/plugins/data/amd/ledgers/`. After a compaction, the
hook empties the record of the session, because the compaction removed the files from
the context of Claude.

The values of `guard.mode`:

- `deny` refuses the edit. Claude gets the names of the files to read, reads them, and
  makes the edit again. `amd why` shows the last refused edit.
- `remind` permits the edit. With the result of the edit, Claude gets the names of the
  files to read.
- `off` stops these checks of edits. The files of `docs/start/` at the start and the
  lines in `compacts.log` stay.

`ATLASMD=off` in the environment of Claude Code stops the hook for one session: it
refuses no edit and gives no reminder. See
[A session without atlasmd](#a-session-without-atlasmd).

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
  record of the files that the session read keeps the folders that it named.
  `docs/`, folders whose names start with a dot, `node_modules`, `.venv`, `tests` and
  `test` do not get the text.

An Edit of a file that exists is never refused for its name. The hook looks only at the
Write tool for a new file. A Bash command that makes a file does not get these checks.

## What it costs in tokens

- **The files of `docs/start/`.** At most `start.budget`, 30,000 estimated tokens by
  default, at each start and after each compaction. Claude Code lets a hook give at most
  10,000 characters at one time. When the files fit in that limit, the hook gives their
  text. When they do not fit, the hook gives the text of the first files up to the limit,
  and the names of the rest. Claude reads each named file. A read costs the same tokens
  as the text, and one tool call per file.
- **The files to read before an edit.** One read of the files under `pack` of an
  `[[area]]` in each session, and again after a compaction. Nothing for an `[[area]]`
  whose paths the session does not change.
- **A subagent.** The map file at its start, by default. The same limit of 10,000
  characters applies: a longer map file comes as its path, and the subagent reads it.
  With `agents.inject = "none"`, nothing.
- **A refused edit.** A few lines with the names of the files.

`amd check` shows the tokens of each file in `docs/start/`, and the total against
`start.budget` and against the 10,000 characters.

## Python

Python 3.11 or newer, the standard library only. The tests run on Linux with 3.11 and
3.13, and on macOS and Windows with 3.13. This command runs them in a clone of the
repository:

```
python3 -m unittest discover -s tests
```

## Privacy

Nothing leaves your computer. [PRIVACY.md](PRIVACY.md) says which files the plugin reads
and which files it keeps.

## Uninstall

This command removes the plugin from Claude Code: the copy under
`~/.claude/plugins/cache/atlasmd/` and the entry in `~/.claude/settings.json`. The hook
then runs in no session.

```
claude plugin uninstall amd@atlasmd
```

Three things stay, and you remove each one yourself if you want it gone:

- The link `~/.local/bin/amd`, if you made it. Delete it.
- The files that atlasmd kept in `~/.claude/plugins/data/amd/`: the records of read
  files, `compacts.log`, your settings, the repository table and the records of the
  meter. Delete that folder.
- The clone of the repository in `~/.claude/plugins/marketplaces/atlasmd/`. The command
  `claude plugin marketplace remove atlasmd` removes the marketplace from Claude Code.

The files of your repositories stay as they are: `atlasmd.toml`, `docs/start/`, and every
file that a setup moved. Without the plugin they are plain Markdown files.

## License

MIT. See [LICENSE](LICENSE).
