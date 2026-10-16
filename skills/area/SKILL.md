---
name: area
description: Give a folder with source files its README.md and an [[area]] entry in atlasmd.toml, write the map file, then fill the README from the files of the folder
argument-hint: <folder>
---

Give the folder `$ARGUMENTS` its README.md and its `[[area]]` entry in three steps.

1. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" area $ARGUMENTS`. When the folder has no README.md, the command writes one from a template. It adds an `[[area]]` entry at the end of `atlasmd.toml`, with the folder under `paths` and its README.md under `pack`, and it writes the map file. The command refuses a folder that does not exist, a folder that holds no source files, and a folder that an `[[area]]` entry lists already. If it refuses, tell the person its sentence and stop.

2. Read the files of the folder. Then write the README.md: what the folder holds, in one or two sentences, the commands that run it from the root of the repository, and the State section. The State section gets the date of today, what works, what does not, and the hash of the last commit that changed the folder, from `git log -1 --format=%h -- <folder>`. If the README.md existed before step 1, keep its text and add only the sections that it does not have.

3. Tell the person what you wrote: the path of the README.md, the name of the `[[area]]` entry, and the facts in the State section. Commit nothing unless the person asked for a commit.
