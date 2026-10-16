---
name: init
description: Set up atlasmd for this project, the start reading, the areas and their guides, and the naming of the Markdown files
---

Set up atlasmd for this project in four steps. Ask the person once, at step 2, and otherwise work on your own.

1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" scan --json`. It lists every Markdown file with its size, the folders that hold code and a README, and whether `atlasmd.toml` and `docs/start/` exist. Then read `CLAUDE.md` of the project if it exists, and the README at the root. Do not read every Markdown file.

2. Propose the setup to the person in one message, as three lists, and ask for a yes or corrections:
   - The areas: one per folder that holds code and a README, with a name in plain words, its code paths, and its pack. A pack is the README beside the code, the plans that name the area, and the decisions the area depends on. Keep a pack under about 60,000 tokens, and say the estimate.
   - The start reading: the four files of `docs/start/`, and what from the project's existing files goes into each. The map gets what the project is and where each kind of fact lives. The open items get the state of the work as one line per item. The state file gets where things stand now. The way of work gets the rules every session needs. Keep the four files under 30,000 tokens in all.
   - The moves: which existing Markdown files move into `docs/decisions/` (one file per decision), `docs/plans/`, `docs/notes/` and `docs/archive/`, and which files get a new name under the convention. The convention: the folder says when a file is read, the name says the order, the date or the number and then the subject, lower case with hyphens.

3. After the yes: write the areas as JSON to a file in your scratchpad and run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" init --areas-json <that file>`. It writes `atlasmd.toml`, the four template files and the folders, and overwrites nothing. Then fill the four start files from what you read, with `git mv` for every move and rename, and update every link that a move breaks. Add this line to `CLAUDE.md`, or make the file with it: `atlasmd injects the start reading of docs/start/ at every start. Read an area's guide before you change the area: the guard refuses a change until the guide was read. The areas are in atlasmd.toml.` Remove from `CLAUDE.md` any list of files to read at the start, because the start reading replaces it.

4. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" map`, then `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check`. Fix what the check names. Report to the person: the budget used of the start reading, the areas with the size of each pack, the files moved and renamed, and what you left for the person. Commit nothing unless the person asked for a commit.
