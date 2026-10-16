---
name: why
description: Explain the last change that the atlasmd guard refused, and what to read before the change
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" why --session "${CLAUDE_SESSION_ID}"`. If that variable is empty, run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" why`, which reads the newest ledger.

Explain the refusal to the person in plain words:
- the file that the change was for, and the area that holds it,
- the files of the area's pack that were not read in this session,
- that every one of those files must be read before the change, and the guard then lets the change through.

Say that the guard mode is `guard.mode` in `atlasmd.toml`: `deny` refuses the change, `remind` lets it through with a reminder, and `off` stops the guard. Do not change the mode yourself. Then read the missing files, if the person agrees, and make the change again.
