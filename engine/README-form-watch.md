# form_watch.py — daily proof the lead paths still reach a human

Drop-in for `marketing-platform/engine/`. Stdlib-only Python 3, no packages,
so `/usr/bin/python3` runs it under cron on a bare Mac.

## Why it does not check HTTP status

Three things can be true on a site that looks perfectly healthy, and each one
loses leads silently:

- the form renders and POSTs 200, and the mail handler is dead
- the chat answers fluently and never emails the transcript
- a field is renamed, so submissions arrive with an empty `email`

The chat case is real, not hypothetical. `shipo-system/src/app/api/chat/route.ts`
captures the lead with `void sendEmail({...})` — fire and forget, on purpose, so
that "a mail failure must never turn into a broken-looking chat for the visitor."
Correct for the visitor, and it means the HTTP status carries no information
about the thing that matters. A 200-checker on that route is a check that cannot
fail.

So the only verdict this tool calls OK is: **a canary went in one end and came
out in the inbox.** Everything else is UNKNOWN, never OK.

## Exit codes

| code | meaning |
|---|---|
| 0 | every configured path proven end to end |
| 1 | findings — something is broken |
| 2 | could not check (no credentials, self-test refused) |

`UNKNOWN` never collapses into either OK or BROKEN. "I could not look" and
"there is nothing there" are different answers and nobody re-checks a no.

## Run

```sh
/usr/bin/python3 engine/form_watch.py --self-test        # 12 assertions
/usr/bin/python3 engine/form_watch.py \
    --site https://shipousa.com \
    --pages "/,/contact-us/,/partner-program/" \
    --chat-endpoint https://<shipo-system-host>/api/chat \
    --chat-origin https://shipousa.com \
    --baseline ~/shipo-sales-dashboard/form-baseline.json \
    --json ~/shipo-sales-dashboard/form-watch-$(date +%F).json
```

`--chat-origin` is load bearing. The route's `ALLOWED_ORIGINS` is an allow-list
of Shipo's own origins, so a probe sent without a matching `Origin` header is
refused and the chat reads as down every day for a reason unrelated to the chat.

## Inbox credentials

Delivery verification needs to read the lead inbox. Environment only, never argv:

```sh
export SHIPO_IMAP_HOST=imap.gmail.com
export SHIPO_IMAP_USER=support@shipousa.com
export SHIPO_IMAP_PASS=<google app password>   # app password, not the login
```

Absent these it reports `UNKNOWN`, not `OK`. Note cron does not read `~/.zshrc`,
so export these in the crontab or a sourced file — a token exported in a login
shell is simply absent at 08:00, which is how the YouTube job failed silently
for 28 days.

## Canaries

Each probe uses a unique plus-addressed canary — `Support+canary-<date>-<rand>@…`
— so every probe is filterable and self-identifying. A shared fixed address
would be indistinguishable from a real lead, and the inbox filter that
eventually kills it would take real leads with it.

`--purge-canaries` deletes the run's own canary mail after verifying it. Off by
default, and it only ever matches its own token.

## Cron

```cron
15 8 * * * SHIPO_IMAP_HOST=imap.gmail.com SHIPO_IMAP_USER=support@shipousa.com SHIPO_IMAP_PASS=xxxx /usr/bin/python3 /Users/ophirschultz/marketing-platform/engine/form_watch.py --site https://shipousa.com --chat-endpoint https://<host>/api/chat --baseline /Users/ophirschultz/shipo-sales-dashboard/form-baseline.json >> /Users/ophirschultz/marketing-platform/logs/form-watch.log 2>&1
```

Avoid paths under `~/Downloads`, `~/Documents`, `~/Desktop` — cron has no Full
Disk Access and the job fails silently there, forever.

## Baseline

`--baseline` stores each page's form signatures and reports a diff on the next
run. The signature is method + action + sorted field names; it deliberately
excludes field order and nonce VALUES, because a nonce rotates every render and
a checker that cries wolf daily gets ignored inside a week. A renamed field
still trips it.
