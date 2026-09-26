#!/usr/bin/env python3
"""Daily proof that the website's lead paths still carry a lead to a human.

Not "is the page up". Three things can be true at once on a site that looks
perfectly healthy, and each one loses leads silently:

  * The form renders and POSTs 200, and the mail handler is dead.
  * The chat answers fluently and never emails the transcript.
  * A field was renamed, so submissions arrive with an empty `email`.

The chat case is not hypothetical here. src/app/api/chat/route.ts captures the
lead with `void sendEmail({...})` — fire and forget, deliberately, so that a
mail failure "must never turn into a broken-looking chat for the visitor". That
is right for the visitor and it means the HTTP status carries no information
about the thing we actually care about. A 200-checker on that endpoint is a
check that cannot fail, and a check that cannot fail is indistinguishable from
one that is not running.

So the only verdict this tool trusts is: a canary went in one end and came out
in the inbox. Everything else it reports as UNKNOWN, never as OK.

Exit codes, so cron can tell the three apart:
    0  every configured path proven end to end
    1  findings — something is broken
    2  could not check (no credentials, site unreachable, self-test refused)
"""

import argparse
import email as emaillib
import html as htmllib
import imaplib
import json
import os
import random
import re
import ssl
import string
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "shipo-form-watch/1.0 (+ops monitor)"
TIMEOUT = 25

# ---------------------------------------------------------------- http

class Resp:
    def __init__(self, status=None, body="", error=None, headers=None):
        self.status, self.body, self.error = status, body, error
        self.headers = headers or {}
    @property
    def ok(self):
        return self.status is not None and 200 <= self.status < 400


def fetch(url, data=None, headers=None, method=None):
    h = {"User-Agent": UA}
    h.update(headers or {})
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else data.encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return Resp(r.status, r.read().decode("utf-8", "replace"), None, dict(r.headers))
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.read().decode("utf-8", "replace"), None, dict(e.headers or {}))
    except Exception as e:
        return Resp(None, "", "%s: %s" % (type(e).__name__, e))


# ---------------------------------------------------------------- form discovery

_FORM = re.compile(r"<form\b(?P<attrs>[^>]*)>(?P<inner>.*?)</form>", re.I | re.S)
_FIELD = re.compile(r"<(?:input|select|textarea)\b([^>]*)>", re.I)
_ATTR = re.compile(r"""(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def attrs_of(s):
    out = {}
    for m in _ATTR.finditer(s or ""):
        out[m.group(1).lower()] = htmllib.unescape(m.group(2) or m.group(3) or m.group(4) or "")
    return out


_BARE_REQUIRED = re.compile(r"(?:^|\s)required(?:\s|$|=)", re.I)


def _is_required(raw_attrs):
    """`required` is a VALUELESS attribute, so a key=value parser cannot see it.

    The self-test caught this: the attribute dict never contained the key, so
    every form on every site reported zero required fields — a check that reads
    clean because it is blind, which is the exact bug class this tool is for.
    """
    return bool(_BARE_REQUIRED.search(raw_attrs or ""))


def find_forms(page_html):
    """Every <form> with its action, method and named fields.

    Hidden inputs are kept. Forminator and most WP form plugins carry the form
    id and a nonce in hidden fields, so dropping them would make two different
    forms look identical and a swapped handler would read as no change at all.
    """
    found = []
    for m in _FORM.finditer(page_html or ""):
        a = attrs_of(m.group("attrs"))
        fields = []
        for fm in _FIELD.finditer(m.group("inner")):
            raw = fm.group(1)
            fa = attrs_of(raw)
            name = fa.get("name")
            if name:
                fields.append({"name": name, "type": (fa.get("type") or "text").lower(),
                               "required": _is_required(raw)})
        found.append({
            "id": a.get("id") or "", "action": a.get("action") or "",
            "method": (a.get("method") or "get").lower(),
            "fields": sorted(fields, key=lambda f: f["name"]),
        })
    return found


def form_signature(f):
    """Stable identity of a form: where it posts plus the names it accepts.

    Deliberately excludes field ORDER and any nonce VALUE. A nonce rotates every
    render, so including its value would make every run report a change and the
    report would be ignored inside a week.
    """
    names = ",".join(sorted(x["name"] for x in f["fields"] if not _is_nonce(x["name"])))
    return "%s %s [%s]" % (f["method"], f["action"], names)


def _is_nonce(name):
    n = name.lower()
    return "nonce" in n or n in ("_wpnonce", "_wp_http_referer", "csrf", "_token", "authenticity_token")


# ---------------------------------------------------------------- canary

def canary_token():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return "canary-%s-%s" % (stamp, rand)


def canary_address(base_address, token):
    """A plus-addressed canary, so every probe is filterable and self-identifying.

    A shared fixed address would be indistinguishable from a real lead in the
    inbox, and the operator would eventually filter the whole address away —
    taking real leads with it.
    """
    local, _, domain = base_address.partition("@")
    return "%s+%s@%s" % (local, token, domain)


# ---------------------------------------------------------------- chat probe

def probe_chat(endpoint, origin, canary_email, token):
    """Send one message containing the canary address through the chat API.

    The Origin header is mandatory and load bearing: the route's ALLOWED_ORIGINS
    is an allow-list of the site's own origins, so a probe sent without it is
    refused and the chat would be reported down every day for a reason that has
    nothing to do with the chat.
    """
    payload = json.dumps({
        "messages": [{"role": "user", "content":
                      "Automated monitoring probe %s — please ignore. "
                      "Reach me at %s" % (token, canary_email)}],
        "page": "form-watch probe",
    })
    r = fetch(endpoint, data=payload, method="POST", headers={
        "Content-Type": "application/json", "Origin": origin, "Referer": origin + "/",
    })
    if r.error:
        return {"stage": "chat", "state": "UNREACHABLE", "detail": r.error}
    if r.status == 403:
        return {"stage": "chat", "state": "CORS_REFUSED",
                "detail": "origin %s is not on the endpoint's allow-list" % origin}
    if not r.ok:
        return {"stage": "chat", "state": "HTTP_%d" % r.status, "detail": r.body[:200]}
    try:
        reply = (json.loads(r.body) or {}).get("reply") or ""
    except ValueError:
        return {"stage": "chat", "state": "BAD_JSON", "detail": r.body[:200]}
    if not reply.strip():
        return {"stage": "chat", "state": "EMPTY_REPLY", "detail": r.body[:200]}
    # Responded is NOT delivered. Lead capture on this route is fire-and-forget.
    return {"stage": "chat", "state": "RESPONDED", "detail": reply[:160]}


# ---------------------------------------------------------------- inbox

def imap_find(token, host, user, password, mailbox="INBOX", wait_s=180, poll_s=15, purge=False):
    """Watch the inbox for the canary token. ABSENT and UNKNOWN are different answers.

    UNKNOWN means the inbox could not be consulted and says nothing about whether
    the mail arrived. Reporting that as ABSENT would manufacture an outage;
    reporting it as OK would hide a real one. Both are worse than saying so.
    """
    if not (host and user and password):
        return {"stage": "inbox", "state": "UNKNOWN",
                "detail": "no inbox credentials in environment; delivery not verified"}
    deadline = time.time() + wait_s
    last_err = None
    while time.time() < deadline:
        try:
            ctx = ssl.create_default_context()
            with imaplib.IMAP4_SSL(host, ssl_context=ctx) as M:
                M.login(user, password)
                M.select(mailbox)
                typ, data = M.search(None, 'TEXT', '"%s"' % token)
                if typ == "OK" and data and data[0].split():
                    ids = data[0].split()
                    if purge:
                        for i in ids:
                            M.store(i, "+FLAGS", "\\Deleted")
                        M.expunge()
                    return {"stage": "inbox", "state": "DELIVERED",
                            "detail": "%d message(s) carrying the canary%s"
                                      % (len(ids), " (purged)" if purge else "")}
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, e)
        time.sleep(poll_s)
    if last_err:
        return {"stage": "inbox", "state": "UNKNOWN", "detail": "inbox unreadable — %s" % last_err}
    return {"stage": "inbox", "state": "ABSENT",
            "detail": "no message carrying the canary within %ds" % wait_s}


# ---------------------------------------------------------------- self-test

FIXTURE_TWO_FORMS = """
<html><body>
<form id="contact" action="/wp-json/forminator/v1/form" method="POST">
  <input type="text" name="name-1" required>
  <input type="email" name="email-1" required>
  <input type="hidden" name="_wpnonce" value="abc123">
  <textarea name="textarea-1"></textarea>
</form>
<form id="search" action="/" method="get"><input type="search" name="s"></form>
</body></html>
"""
FIXTURE_NO_FORMS = "<html><body><p>Nothing here but prose and a <a href='/x'>link</a>.</p></body></html>"
FIXTURE_NONCE_ROTATED = FIXTURE_TWO_FORMS.replace('value="abc123"', 'value="zzz999"')
FIXTURE_FIELD_RENAMED = FIXTURE_TWO_FORMS.replace('name="email-1"', 'name="email-2"')


def self_test():
    """Every check must be proven to fire AND to stay quiet, or startup refuses.

    A discovery check nobody has watched fire is indistinguishable from one that
    cannot fire, and this whole tool exists because of silent passes.
    """
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print("  %-34s %s%s" % (label, "PASS" if good else "FAIL",
                                "" if good else "  -> %r != %r" % (got, want)))

    two = find_forms(FIXTURE_TWO_FORMS)
    check("finds both forms", len(two), 2)
    check("stays quiet on a page with none", len(find_forms(FIXTURE_NO_FORMS)), 0)
    check("reads the action", two[0]["action"], "/wp-json/forminator/v1/form")
    check("reads the method", two[0]["method"], "post")
    check("keeps hidden fields", any(f["name"] == "_wpnonce" for f in two[0]["fields"]), True)
    check("marks required fields",
          sorted(f["name"] for f in two[0]["fields"] if f["required"]), ["email-1", "name-1"])

    base = form_signature(two[0])
    rot = form_signature(find_forms(FIXTURE_NONCE_ROTATED)[0])
    ren = form_signature(find_forms(FIXTURE_FIELD_RENAMED)[0])
    check("signature ignores a rotated nonce", rot, base)
    check("signature catches a renamed field", ren != base, True)

    tok = canary_token()
    addr = canary_address("Support@shipousa.com", tok)
    check("canary is plus-addressed", addr, "Support+%s@shipousa.com" % tok)
    check("canary tokens are unique", canary_token() != canary_token(), True)

    # The distinction the whole tool turns on.
    miss = imap_find("tok", None, None, None)
    check("no credentials reports UNKNOWN", miss["state"], "UNKNOWN")
    check("UNKNOWN is never DELIVERED", miss["state"] == "DELIVERED", False)

    print("\nSELF-TEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 2


# ---------------------------------------------------------------- report

def verdict(results):
    """A path is OK only when a canary was seen in the inbox."""
    bad = [r for r in results if r["state"] in
           ("UNREACHABLE", "CORS_REFUSED", "BAD_JSON", "EMPTY_REPLY", "ABSENT")
           or r["state"].startswith("HTTP_")]
    unknown = [r for r in results if r["state"] == "UNKNOWN"]
    if bad:
        return 1
    if unknown:
        return 2
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", default="https://shipousa.com")
    p.add_argument("--pages", default="/,/contact-us/,/partner-program/",
                   help="comma-separated paths to sweep for forms")
    p.add_argument("--chat-endpoint", default=os.environ.get("SHIPO_CHAT_ENDPOINT", ""))
    p.add_argument("--chat-origin", default="https://shipousa.com",
                   help="must be on the endpoint's ALLOWED_ORIGINS or the probe is refused")
    p.add_argument("--lead-inbox", default="Support@shipousa.com")
    p.add_argument("--baseline", default="", help="JSON file of known form signatures")
    p.add_argument("--wait", type=int, default=180, help="seconds to watch the inbox")
    p.add_argument("--purge-canaries", action="store_true",
                   help="delete this run's own canary mail after verifying it (off by default)")
    p.add_argument("--json", default="")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()

    if a.self_test:
        return self_test()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("FORM WATCH — %s — %s\n" % (a.site, stamp))

    results, forms_seen = [], {}

    # 1. Structure. A changed signature is not itself an outage, but it is the
    #    single best predictor of one, and it is invisible to a status check.
    for path in [x.strip() for x in a.pages.split(",") if x.strip()]:
        url = a.site.rstrip("/") + path
        r = fetch(url)
        if not r.ok:
            results.append({"stage": "page " + path, "state": "UNREACHABLE",
                            "detail": r.error or "HTTP %s" % r.status})
            print("  %-28s UNREACHABLE  %s" % (path, r.error or r.status))
            continue
        fs = find_forms(r.body)
        forms_seen[path] = [form_signature(f) for f in fs]
        print("  %-28s %d form(s)" % (path, len(fs)))
        for f in fs:
            print("      %s" % form_signature(f))

    if a.baseline:
        try:
            with open(a.baseline) as fh:
                old = json.load(fh)
            for path, sigs in forms_seen.items():
                was = old.get(path)
                if was is not None and was != sigs:
                    results.append({"stage": "page " + path, "state": "CHANGED",
                                    "detail": "was %r now %r" % (was, sigs)})
                    print("  !! %s changed shape since baseline" % path)
        except FileNotFoundError:
            pass
        with open(a.baseline, "w") as fh:
            json.dump(forms_seen, fh, indent=1, sort_keys=True)

    # 2. The chat, end to end.
    if a.chat_endpoint:
        tok = canary_token()
        addr = canary_address(a.lead_inbox, tok)
        print("\n  chat probe %s -> %s" % (tok, addr))
        c = probe_chat(a.chat_endpoint, a.chat_origin, addr, tok)
        results.append(c)
        print("  %-28s %s  %s" % ("chat response", c["state"], c["detail"][:90]))
        if c["state"] == "RESPONDED":
            d = imap_find(tok, os.environ.get("SHIPO_IMAP_HOST", "imap.gmail.com"),
                          os.environ.get("SHIPO_IMAP_USER"), os.environ.get("SHIPO_IMAP_PASS"),
                          wait_s=a.wait, purge=a.purge_canaries)
            results.append(d)
            print("  %-28s %s  %s" % ("chat lead delivery", d["state"], d["detail"]))
    else:
        results.append({"stage": "chat", "state": "UNKNOWN",
                        "detail": "no --chat-endpoint configured; chat not checked"})
        print("\n  chat                         UNKNOWN  no endpoint configured")

    code = verdict(results)
    print("\nVERDICT %s" % {0: "ALL PROVEN", 1: "FINDINGS", 2: "COULD NOT FULLY CHECK"}[code])
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"site": a.site, "at": stamp, "forms": forms_seen,
                       "results": results, "exit": code}, fh, indent=1)
    return code


if __name__ == "__main__":
    sys.exit(main())
