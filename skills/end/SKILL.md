---
name: end
description: End the session so a fresh chat or a compaction starts well, the state file, the push and the opening line
---

End the session in three steps.

1. Rewrite the state file that `atlasmd.toml` names under `start.state`: what was done since the last ending, what the person looks at, what waits on a person, and what comes next, each as short lines with a pointer to the file that holds the detail. Keep it under 12,000 characters. Move what is no longer current out of it. Then update `docs/start/20-open-items.md` the same way.

2. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check`, fix what it names, and commit the records by name. Push, unless the project's rules say when a push must wait. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" end`: it shows what is not committed or not pushed.

3. Give the person the opening line for a fresh chat, in a code block, with the path of the state file beside it. The line is `start.line` of `atlasmd.toml`. The start reading goes into the fresh chat by itself, so the line asks for nothing else.
