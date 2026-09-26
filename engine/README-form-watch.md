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
/usr/bin/python3 engine/form_watch.py --self-test        # 33 assertions
/usr/bin/python3 engine/form_watch.py \
    --site https://shipousa.com \
    --pages "/,/contact-us/,/partner-program/" \
    --submit-forms \
    --lead-pages "/contact-us/,/partner-program/" \
    --chat-endpoint https://<shipo-system-host>/api/chat \
    --chat-origin https://shipousa.com \
    --baseline ~/shipo-sales-dashboard/form-baseline.json \
    --json ~/shipo-sales-dashboard/form-watch-$(date +%F).json
```

`--chat-origin` is load bearing. The route's `ALLOWED_ORIGINS` is an allow-list
of Shipo's own origins, so a probe sent without a matching `Origin` header is
refused and the chat reads as down every day for a reason unrelated to the chat.

### The chat has TWO lead paths, and both are probed

They are different branches sending different emails, and the first can be
perfectly healthy while the second is dead:

| probe | what the visitor does | email it must produce |
|---|---|---|
| `chat lead` | leaves an address | *Website chat lead — &lt;address&gt;* |
| `chat agent request` | asks for a human, leaves nothing | *asked for a person — no contact details left* |

The agent-request probe deliberately carries **no** email address. An address
anywhere in the text routes the conversation down the lead path, and the branch
we meant to test never runs — a probe that quietly checks the wrong thing.

Its canary token travels in the message text rather than in an address, which
works because that email quotes the conversation back. The token is therefore
still in the body for the inbox search to find.

This branch matters most: the visitor has already asked to be contacted, so a
silent failure here loses someone who was ready to talk.

## Submitting the forms

`--submit-forms` is what makes a form OK-able. Without it the sweep only reads
each page's form structure, which catches a renamed field but not a dead mail
handler sitting behind an unchanged one — so forms report `UNKNOWN`, never `OK`.

It is **off by default**, and it is the only part of this tool that writes. Each
run posts a genuine submission: a real email to the lead inbox, and a real row
in whatever CRM sits behind the form. Turn it on deliberately, and expect one
canary per lead form per run.

What a probe submission does:

- fills **every** named field, required or not — server-side validation does not
  have to agree with the `required` attributes in the markup, and a field the
  server insists on but the page does not mark is the commonest reason a
  hand-built probe bounces
- echoes hidden fields **verbatim**, so the per-render nonce and the form id
  survive, and reuses the cookie jar from the page fetch — WordPress ties an
  anonymous nonce to the session cookie, and the right nonce on the wrong
  session is rejected before the mail handler ever runs
- ticks required consent boxes, picks a real `<select>` option rather than the
  empty placeholder, and collapses a radio group to a single value
- encodes the body the way the form declares it, multipart or urlencoded.
  Forminator's AJAX handler reads multipart; guessing wrong bounces the probe
  daily for a reason that has nothing to do with the form's health

Every probe is unmistakably a probe: the token appears in the name field and in
the message body, above the words *please ignore and do not reply*.

### Forms it refuses to submit

Three gates, each tested in both directions:

| refused | why |
|---|---|
| `method="get"` | a search box; submitting it proves nothing |
| no email field | nothing the inbox could recognise as the probe |
| login, signup, password, reset, checkout, cart, payment, delete, `wp-admin` | a monitor that POSTs to a login endpoint every morning is a slow brute-force against its own site, and repeated failures lock the account out |

### `--lead-pages`

Pages that **must** carry a lead form. A contact page serving no submittable
form is an outage, and on a first run there is no baseline to catch it against,
so absence there is a finding (`NO_LEAD_FORM`, exit 1). Everywhere else a page
without a form is just a page and stays silent — a checker that flags the
homepage every morning for having no contact form is ignored inside a week.

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

Every canary in a run is watched for under **one shared deadline**, not one
deadline each. They were all posted within a few seconds of each other, so the
waits overlap completely: three forms plus the chat at `--wait 180` is three
minutes, not twelve.

## Cron

```cron
15 8 * * * SHIPO_IMAP_HOST=imap.gmail.com SHIPO_IMAP_USER=support@shipousa.com SHIPO_IMAP_PASS=xxxx /usr/bin/python3 /Users/ophirschultz/marketing-platform/engine/form_watch.py --site https://shipousa.com --submit-forms --chat-endpoint https://<host>/api/chat --baseline /Users/ophirschultz/shipo-sales-dashboard/form-baseline.json >> /Users/ophirschultz/marketing-platform/logs/form-watch.log 2>&1
```

Avoid paths under `~/Downloads`, `~/Documents`, `~/Desktop` — cron has no Full
Disk Access and the job fails silently there, forever.

## Baseline

`--baseline` stores each page's form signatures and reports a diff on the next
run. The signature is method + action + sorted field names; it deliberately
excludes field order and nonce VALUES, because a nonce rotates every render and
a checker that cries wolf daily gets ignored inside a week. A renamed field
still trips it.
