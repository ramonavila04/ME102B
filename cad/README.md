# CAD

`cad/onshape/` holds STEP and STL files exported automatically from the team's
Onshape documents. **Don't edit these by hand.** Edit in Onshape, and the sync
overwrites these files.

## One-time setup (about 10 minutes, by someone with access to the Onshape documents)

1. Create API keys: Onshape → your account menu → **Developer portal** →
   **API keys** → **Create new API key**. Tick **Read** access (OAuth2Read is
   enough). Copy the access key and secret key; the secret is shown only once.
2. Store them in GitHub: repo **Settings → Secrets and variables → Actions →
   New repository secret**. Create `ONSHAPE_ACCESS_KEY` and
   `ONSHAPE_SECRET_KEY`. Never paste them into a file or chat.
3. List the tabs to export in `cad/onshape_documents.json`. Open each Part
   Studio or Assembly in Onshape, copy the browser URL, and add an entry. Delete
   the example entry.
4. Run it: **Actions → Onshape CAD sync → Run workflow**. It commits the
   exports to `cad/onshape/` together with `manifest.json`, which records each
   source URL.

After that, the files refresh every night at 02:17 Pacific, or whenever someone
clicks **Run workflow**.

Notes:
- The API keys can read every Onshape document their owner can see. Create
  them from an account that only needs the project documents, and revoke them
  at the end of the semester.
- A URL with `/w/` exports the live workspace. A URL with `/v/` exports a saved
  version, which never changes. Use versions for anything the team signs off on.
- Running locally: set the two environment variables, then
  `python tools/onshape_sync.py --dry-run` to check access.
