---
name: status
description: Show which area guides this session read, which it did not, and the last compaction
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" status --session "${CLAUDE_SESSION_ID}"`. If that variable is empty, run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" status`, which reads the newest ledger.

Tell the person, in short lines:
- the packs that this session read in full,
- the packs that it read in part, with the files that are missing,
- the areas that it changed or tried to change,
- the time and the trigger of the last compaction.

Then say that the guard refuses a change in an area until its whole pack was read, and that a compaction makes the next change in an area read the pack again.
