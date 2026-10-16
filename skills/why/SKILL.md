---
name: why
description: Explain the last edit that the atlasmd hook refused, and which files Claude must read before that edit
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" why --session "${CLAUDE_SESSION_ID}"`. If that variable is empty, run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" why`, which shows the newest refused edit of all sessions.

Explain the refused edit to the person in plain words:
- the file that the edit was for, and the `[[area]]` in `atlasmd.toml` whose paths hold it,
- the files under `pack` of that `[[area]]` that this session did not read,
- that the session must read every one of those files before the edit, and that the hook then permits the edit.

Say that `guard.mode` in `atlasmd.toml` sets what the hook does: `deny` refuses the edit, `remind` permits it and names the files to read, and `off` stops these checks. Do not change the mode yourself. Then read the missing files, if the person agrees, and make the edit again.
