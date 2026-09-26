# Contact form: remove two fields, cut the 5-second submit

Both changes are in WordPress, not in this repo. Forminator stores a form's
fields and settings in the WP database, so there is no file here to edit and
nothing to deploy — these are WP admin changes on shipousa.com.

Written 2026-09-26. The live site could not be loaded from the session that
wrote this (network policy denied the host), so the click paths below are
Forminator's standard layout and the diagnosis order is by likelihood, not a
reading of the actual form. Confirm each screen as you go.

## 1. Remove the two fields

Target: **Sales Channels** (checkbox group: Shopify / Amazon / Walmart /
B2B-Wholesale / Other) and **Are you currently using a 3PL?** (Yes/No radio).

WP Admin → **Forminator → Forms** → hover the contact form → **Edit** →
**Fields** tab. On each of the two fields use the field's **delete** control,
then **Update** the form.

**Check these two tabs before you hit Update.** Deleting a field does not clean
up the places that reference it, and a dangling reference is worse than the
field was:

- **Emails tab** — notification bodies interpolate fields by id
  (`{checkbox-1}`, `{radio-1}` or similar). A macro whose field no longer
  exists does not disappear; it renders literally in the lead email. Remove
  those lines from every notification, not just the first one.
- **Behaviour tab** — if any conditional logic, or the thank-you / redirect
  behaviour, is keyed on one of these fields, that condition silently stops
  matching once the field is gone.

Also check any **Integrations** tab mapping (Mailchimp, HubSpot, a CRM): a
mapping that points at a deleted field can make the whole integration call
fail, which costs you the lead rather than just the answer.

### Expect one monitoring alert

`engine/form_watch.py` fingerprints each form as method + action + sorted field
names and diffs it against `--baseline`. Removing two named fields changes that
signature, so the next run reports:

```
!! /contact-us/ changed shape since baseline
```

That is correct behaviour — it is the renamed-field detector doing its job. The
baseline rewrites itself on that same run, so the alert fires once and then
goes quiet. If it fires a second time, something changed that you did not
change.

## 2. The 5-second submit

First, find out whether the wait is server-side or in the browser — the fixes
are completely different and this takes thirty seconds:

Open the page → DevTools → **Network** → filter `admin-ajax.php` → submit the
form. Read the **TTFB / waiting** figure on that POST.

- **TTFB is ~5s** → the server is busy during submit. Work the list below.
- **TTFB is fast, total is 5s** → it is front-end: script load, a reCAPTCHA
  challenge resolving, or the success animation. Different problem.

**Prior finding — check this first.** The `Marketing expansion strategy`
session (2026-09-25) recorded **"NitroPack JS delay likely culprit"** for this
same complaint. NitroPack defers JavaScript execution until user interaction —
a FRONT-END cause, which shows up as fast TTFB with a slow total. That session
was itself blocked waiting on the DevTools check above, so this is a lead, not
a confirmation; but it came from a session working the site directly and it
outranks the server-side theory below. If the measurement says front-end, the
fix is in NitroPack's settings — disable "Delay JS execution", or exclude the
Forminator scripts from it — and Forminator is not involved at all.

Three sessions (2026-09-25, and two on 2026-09-26) have now stalled on this
same missing measurement. Take the number before theorising further.

Assuming it is server-side, these are the causes in order of how often they are
the answer:

1. **Email notification sent over SMTP during the request.** This is the most
   common cause by a wide margin. An authenticated SMTP handshake is several
   round trips before a byte of the message moves, and the visitor's browser
   waits through all of it. Switching the mailer from SMTP to the provider's
   **HTTP API** (SendGrid, Mailgun, Postmark all offer one; WP Mail SMTP
   exposes them as mailer options) typically takes this from seconds to a few
   hundred milliseconds, because there is no handshake.
2. **Third-party integrations firing synchronously.** Each connected service on
   the form's Integrations tab is a blocking outbound HTTP call inside the
   submit. Two slow ones are your five seconds on their own. Disconnect one at
   a time and re-time the submit to find the offender.
3. **Akismet / spam checks.** Forminator can call Akismet during validation —
   another outbound call in the request path. Toggle it off and re-time.
4. **reCAPTCHA verification.** The server-side `siteverify` call to Google is
   in the request path too.

The principle behind all four is the one the chat endpoint already applies
deliberately: the visitor should never wait on a system that is not the
visitor. `src/app/api/chat/route.ts` (in `shipo-system`) captures its lead with
`void sendEmail({...})` — fire and forget — precisely so a slow or dead mail
handler cannot turn into a slow or broken-looking experience for the person
filling out the form. The WordPress form should behave the same way: acknowledge
the submission immediately, deliver the notification on its own time.

### The thing to be careful about

Making mail asynchronous means the submit can succeed while the notification
quietly fails, and you would not find out from the form. That is exactly the
failure `form_watch.py` was built to catch, and it is worth re-reading
`engine/README-form-watch.md` before you make this change rather than after:
the tool only reports OK when a canary it sent actually lands in the inbox.
Make sure the daily run is green before you decouple the email, so that if it
goes red afterwards you know the change did it.
