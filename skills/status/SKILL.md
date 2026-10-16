---
name: status
description: Show which files under pack in atlasmd.toml this session read, which it did not read, and the last compaction
---

Run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" status --session "${CLAUDE_SESSION_ID}"`. If that variable is empty, run `"${CLAUDE_PLUGIN_ROOT}/bin/amd" status`, which shows the last session that read a file.

Tell the person, in short lines:
- each `[[area]]` whose files under `pack` this session read in full,
- each `[[area]]` whose files under `pack` it read in part, with the files that it did not read,
- the `[[area]]` entries where it read a file in the paths, or had an edit refused,
- the time of the last compaction, and whether it was manual or automatic.

Then say this: when `guard.mode` is `deny`, the hook refuses an edit in the paths of an `[[area]]` until the session reads every file under its `pack`. After a compaction, the session must read those files again before its next edit there.
