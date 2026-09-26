# Working agreement

## Check before answering

Ophir's standing instruction, and it is the first thing to honour in a session:
**do not give an answer before checking.** No diagnosis from general knowledge,
no UI click-paths from memory of how a plugin usually looks, no "the usual
cause is X" before looking. Check first, then answer. If something genuinely
cannot be checked from the current environment, say that it could not be
checked — do not fill the gap with a plausible answer.

Read this file and any memory directory at the START of a session, not when
prompted.

## Where things actually live

This repo (`Shipo--website`) holds monitoring and strategy docs only. It
contains **no website code**:

- `engine/form_watch.py` — daily end-to-end check of the live lead paths
- `engine/README-form-watch.md`
- `docs/` — strategy and runbooks

The website itself is **WordPress on shipousa.com**, with forms built in
**Forminator**. Form fields, notification templates and behaviour are rows in
the WP database. They cannot be changed by editing a file or pushing a commit
from anywhere — they are wp-admin changes. Do not offer to "fix the form" by
pushing code.

The Next.js app is a separate repo, `ophir-schultz/shipo-system` (contains
`src/app/api/chat/route.ts`, the chat lead-capture path). It is not attached to
cloud sessions by default and `add_repo` for it has been denied before.

## Known environment limits in cloud sessions

- **`shipousa.com` is blocked** by the environment network policy — the proxy
  answers 403 to CONNECT. Verify with a single curl before relying on it; the
  policy is per-environment and may have been changed since this was written.
- No credentials for wp-admin, and none should be requested into a session.
- Cloud sessions cannot reach Ophir's computer. Work needing his browser or
  network has to run there (Claude Desktop app, or `claude remote-control`).
- GitHub **is** reachable and pushes work. Reaching GitHub is not the same as
  reaching the website; do not conflate them.

## Monitoring gotcha

Changing any form's fields changes its signature (method + action + sorted
field names) and `form_watch.py` will report `!! <page> changed shape since
baseline` on the next run. That is correct behaviour and self-clears after one
run, because the baseline rewrites itself. Firing twice means something changed
that nobody intended.
