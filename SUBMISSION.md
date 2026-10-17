# How to list atlasmd in Anthropic's directory

The directory at https://claude.ai/directory is where people add plugins on claude.ai, in
Cowork and in Claude Code. You submit from the developer portal at
https://claude.ai/directory/manage. Nothing is uploaded by hand: the portal reads the
GitHub repository, and the listing shows the name and description from
`.claude-plugin/plugin.json` and the README as its text. The logo is the image at the top
of the README.

## What must be true before you start

- You are on a paid claude.ai plan (Pro, Max, Team or Enterprise).
- Your GitHub account is connected on claude.ai, in the organization that you submit from.
  The portal checks that this account can push to `simon-init/atlasmd`.
- The repository can stay private while you validate and submit. Then the portal asks you
  to accept that the source is uploaded to Anthropic for the scan, and the Claude GitHub
  App must be installed on the repository. The repository must be public before the
  listing goes live.
- The plugin passes `claude plugin validate --strict .` (it does), has a README over 40
  words (it has), a LICENSE file (MIT), and `description`, `author` and `version` in
  `plugin.json` (it has).

## The steps in the portal

1. Open https://claude.ai/directory/manage and select **Submit new**, then **Plugin bundle**.
2. On **Source**, enter `simon-init/atlasmd`. Leave the plugin path empty (the plugin is at
   the root) and the branch empty (the directory follows `master`).
3. Select **Validate**. Fix anything marked **Blocking**, push, and select **Re-validate**.
4. **Listing details** come from `plugin.json` and the README. To change them, edit the
   files and validate again.
5. **Data handling**, the answers that fit atlasmd:
   - Reads or stores personal data: it reads the Markdown files of the repository and the
     session transcript on the user's computer, and keeps file paths, token counts and
     dates in `~/.claude/plugins/data/amd/`. It keeps no message text.
   - Sends data to other services: no. The plugin makes no network call.
   - How long it keeps data: the records of read files for 14 days, the token records and
     `compacts.log` until the user deletes the folder.
   - For people under 18: no.
6. **Compliance**: check the contact email, select the four acknowledgements.
7. **Review and submit**: keep **GitHub push webhook**, select **Submit for review**.

## After the submission

Every push to `master` becomes a new version that the directory scans. Raise `version` in
`plugin.json`, `marketplace.json` and `atlasmd/__init__.py` with every release. A version
that passes is published when you select **Publish**, by default after an Anthropic
reviewer looks at it. The status of the submission is on the plugin's page in the portal.
