---
name: end
description: End the session. Write the file in start.state again, commit and push, and give the first message for a fresh chat
---

End the session in three steps.

1. Write again the file that `atlasmd.toml` names under `start.state`, `docs/start/30-state.md` by default: what was done since the last `/amd:end`, what the person must look at, what waits on a person, and what comes next. Write each as short lines, with the path of the file that holds the details. Keep the file under 12,000 characters. Move out of it what is no longer current. Then update `docs/start/20-open-items.md` the same way.

2. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" check`, fix what it reports, and commit the changed files by name. Push, unless the rules of the project say when a push must wait. Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" end`: it shows what is not committed or not pushed.

3. Give the person the first message for a fresh chat, in a code block, with the path of the file in `start.state` beside it. The message is `start.line` of `atlasmd.toml`. The fresh chat gets the files of `docs/start/` from the hook, so the message asks for nothing else.
