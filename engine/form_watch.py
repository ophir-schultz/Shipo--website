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

That applies to the FORMS as much as to the chat, which is why --submit-forms
exists: reading a page's form markup catches a renamed field, but never a dead
mail handler behind markup that did not change. Only a submission does. It is
off by default because it is the one thing here that writes -- a real message
in the lead inbox and a real row in whatever CRM sits behind the form.

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
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar

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


def new_jar():
    """A cookie jar shared by a page fetch and the submission that follows it.

    WordPress ties an anonymous form nonce to the session cookie handed out with
    the page. Submitting on a fresh connection sends the right nonce with the
    wrong session, the form is rejected before the mail handler ever runs, and
    the probe then reports the form broken every morning for a reason that is
    entirely the probe's own fault.
    """
    return CookieJar()


def fetch(url, data=None, headers=None, method=None, jar=None):
    h = {"User-Agent": UA}
    h.update(headers or {})
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else data.encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    opener = (urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
              if jar is not None else urllib.request.build_opener())
    try:
        with opener.open(req, timeout=TIMEOUT) as r:
            return Resp(r.status, r.read().decode("utf-8", "replace"), None, dict(r.headers))
    except urllib.error.HTTPError as e:
        return Resp(e.code, e.read().decode("utf-8", "replace"), None, dict(e.headers or {}))
    except Exception as e:
        return Resp(None, "", "%s: %s" % (type(e).__name__, e))


# ---------------------------------------------------------------- form discovery

_FORM = re.compile(r"<form\b(?P<attrs>[^>]*)>(?P<inner>.*?)</form>", re.I | re.S)
_FIELD = re.compile(r"<(input|select|textarea)\b([^>]*)>", re.I)
_ATTR = re.compile(r"""(\w[\w:-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
_SELECT = re.compile(r"<select\b([^>]*)>(?P<opts>.*?)</select>", re.I | re.S)
_OPTION = re.compile(r"<option\b([^>]*)>", re.I)


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
        inner = m.group("inner")
        # <select> options live BETWEEN the tags, where the opening-tag scan
        # below cannot see them. Without a real option value a required dropdown
        # is submitted empty and the whole form bounces on validation.
        options = {}
        for sm in _SELECT.finditer(inner):
            nm = attrs_of(sm.group(1)).get("name")
            if nm:
                options[nm] = [attrs_of(om.group(1)).get("value", "")
                               for om in _OPTION.finditer(sm.group("opts"))]
        fields = []
        for fm in _FIELD.finditer(inner):
            tag, raw = fm.group(1).lower(), fm.group(2)
            fa = attrs_of(raw)
            name = fa.get("name")
            if name:
                kind = (fa.get("type") or "text").lower() if tag == "input" else tag
                fields.append({"name": name, "type": kind, "required": _is_required(raw),
                               "value": fa.get("value", ""), "options": options.get(name, [])})
        found.append({
            "id": a.get("id") or "", "action": a.get("action") or "",
            "method": (a.get("method") or "get").lower(),
            "enctype": (a.get("enctype") or "application/x-www-form-urlencoded").lower(),
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


# ---------------------------------------------------------------- form probe

# Forms this tool must never submit. A monitor that POSTs to a login or a
# checkout endpoint every morning is not a monitor, it is a slow brute-force
# attempt against its own site, and repeated failures lock the account out.
_FORM_DENY = re.compile(
    r"(log[-_]?in|sign[-_]?in|sign[-_]?up|regist|password|passwd|reset|"
    r"checkout|cart|payment|billing|delete|logout|wp-admin|wp-login)", re.I)

PROBE_MESSAGE = (
    "Automated monitoring probe %s - please ignore and do not reply. "
    "This submission checks that the website's lead forms still reach the inbox."
)


def _is_email_field(f):
    return f["type"] == "email" or "email" in f["name"].lower()


def is_probeable_lead_form(f):
    """Whether a form is one we may safely put a canary through.

    Three gates, each of which has to be here: a GET form is a search box and
    submitting it proves nothing about the lead path; a form with no email
    field cannot produce a lead we would recognise in the inbox; and anything
    on the deny-list must never be POSTed to on a schedule.
    """
    if f.get("method") != "post":
        return False
    if _FORM_DENY.search(f.get("action") or "") or _FORM_DENY.search(f.get("id") or ""):
        return False
    return any(_is_email_field(x) for x in f.get("fields", []))


def _probe_value(f, canary_email, token):
    """A plausible value for one field, chosen by type and then by name.

    Every named field is filled, required or not. Server-side validation does
    not have to agree with the `required` attributes in the markup, and a field
    the server insists on but the page does not mark is the commonest reason a
    hand-built probe bounces.
    """
    name, typ = f["name"], f["type"]
    low = name.lower()
    if typ == "hidden":
        return f.get("value", "")        # nonce, form id, referer - echo verbatim
    if typ in ("checkbox", "radio"):
        return f.get("value") or "1"     # an unticked consent box bounces the form
    if typ == "select":
        real = [o for o in f.get("options", []) if o.strip()]
        return real[0] if real else ""   # never the empty "Choose..." placeholder
    if _is_email_field(f):
        return canary_email
    if typ == "tel" or any(k in low for k in ("phone", "tel", "mobile")):
        return "+1-555-0100"
    if typ == "url" or "website" in low:
        return "https://shipousa.com"
    if typ == "number":
        return "1"
    if typ == "textarea" or any(k in low for k in ("message", "comment", "enquiry", "inquiry")):
        return PROBE_MESSAGE % token
    if "name" in low:
        return "Form Watch Canary %s" % token
    return "form-watch %s" % token


def fill_form(f, canary_email, token):
    """Name/value pairs for a probe submission, deduplicated by field name.

    Radio and checkbox groups repeat one name across several inputs. Sending
    every one of them leaves the server keeping whichever it happened to read
    last, so the first is picked here, where the choice is visible and testable.
    """
    pairs, seen = [], set()
    for field in f.get("fields", []):
        if field["name"] in seen:
            continue
        seen.add(field["name"])
        pairs.append((field["name"], _probe_value(field, canary_email, token)))
    return pairs


def encode_body(pairs, enctype):
    """Encode the body the way the form itself declares it.

    Forminator's AJAX handler reads multipart; most plain WordPress handlers
    read urlencoded. Guessing wrong bounces the submission for a reason that
    has nothing to do with the form's health, and a monitor that cries wolf
    every morning is ignored inside a week.
    """
    if "multipart" in (enctype or ""):
        boundary = "----formwatch%s" % "".join(
            random.choice(string.ascii_lowercase + string.digits) for _ in range(16))
        out = []
        for k, v in pairs:
            out.append("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                       % (boundary, k, v))
        out.append("--%s--\r\n" % boundary)
        return ("".join(out).encode("utf-8"),
                "multipart/form-data; boundary=%s" % boundary)
    return (urllib.parse.urlencode(pairs).encode("utf-8"),
            "application/x-www-form-urlencoded")


def probe_form(page_url, form, canary_email, token, origin, jar=None):
    """POST one canary through one form.

    The best verdict available here is POSTED, never OK. A 200 from a form
    handler says the request was accepted, not that mail left the building -
    the same reason the chat probe stops at RESPONDED. Only the inbox settles it.
    """
    action = urllib.parse.urljoin(page_url, form.get("action") or page_url)
    body, ctype = encode_body(fill_form(form, canary_email, token), form.get("enctype"))
    r = fetch(action, data=body, method="POST", jar=jar, headers={
        "Content-Type": ctype, "Origin": origin, "Referer": page_url,
        "Accept": "application/json, text/html;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    })
    stage = "form %s" % (form.get("id") or action)
    if r.error:
        return {"stage": stage, "state": "UNREACHABLE", "detail": r.error}
    if not r.ok:
        return {"stage": stage, "state": "HTTP_%d" % r.status, "detail": r.body[:200]}
    try:
        j = json.loads(r.body)
    except ValueError:
        j = None
    if isinstance(j, dict) and j.get("success") is False:
        return {"stage": stage, "state": "REJECTED",
                "detail": str(j.get("message") or j.get("data") or j)[:200]}
    return {"stage": stage, "state": "POSTED", "detail": "accepted; delivery not yet proven"}


# ---------------------------------------------------------------- chat probe

_HASHY = re.compile(r"^(?=.*[0-9])(?=.*[a-z])[a-z0-9]{8,12}$")


def is_ephemeral_deploy_url(endpoint):
    """True for a per-DEPLOYMENT Vercel URL rather than a stable alias.

    Vercel gives every deployment its own <name>-<hash>-<scope>.vercel.app
    address, and that address dies the next time anything ships. Point the
    monitor at one and it passes today, then reports the chat unreachable
    every morning after the next deploy — an outage that exists only in the
    monitor's config. The site itself calls a stable alias, so that is what
    this must watch.

    The hash sits BETWEEN the project name and the team scope, never first or
    last, and always mixes letters with digits. A plain project name like
    shipo-chat.vercel.app, a scoped alias, or a custom domain are all fine.
    """
    try:
        host = urllib.parse.urlparse(endpoint).hostname or ""
    except ValueError:
        return False
    if not host.endswith(".vercel.app"):
        return False
    parts = host[:-len(".vercel.app")].split("-")
    return any(_HASHY.match(seg) for seg in parts[1:-1])


def chat_lead_message(token, canary_email):
    """A visitor who leaves contact details. Triggers the 'chat lead' email."""
    return ("Automated monitoring probe %s — please ignore. "
            "Reach me at %s" % (token, canary_email))


def chat_agent_message(token):
    """A visitor who asks for a human and leaves NOTHING behind.

    This is a different trigger from the lead path and it sends a different
    email ('asked for a person, no contact details'), so it has to be probed
    separately: the lead path can be perfectly healthy while this one is dead,
    and this is the one where the visitor is already asking to be called back.

    It deliberately carries no email address. An address in the text would put
    the conversation down the lead path instead and this branch would never run
    — a probe that quietly tests the wrong thing.
    """
    return ("Automated monitoring probe %s — please ignore, no reply needed. "
            "I would like to speak to a human agent please." % token)


def probe_chat(endpoint, origin, token, message, kind="lead"):
    """Send one message through the chat API and classify the response.

    The Origin header is mandatory and load bearing: the route's ALLOWED_ORIGINS
    is an allow-list of the site's own origins, so a probe sent without it is
    refused and the chat would be reported down every day for a reason that has
    nothing to do with the chat.
    """
    stage = "chat %s" % kind
    payload = json.dumps({
        "messages": [{"role": "user", "content": message}],
        "page": "form-watch probe",
    })
    r = fetch(endpoint, data=payload, method="POST", headers={
        "Content-Type": "application/json", "Origin": origin, "Referer": origin + "/",
    })
    if r.error:
        return {"stage": stage, "state": "UNREACHABLE", "detail": r.error}
    if r.status == 403:
        return {"stage": stage, "state": "CORS_REFUSED",
                "detail": "origin %s is not on the endpoint's allow-list" % origin}
    if not r.ok:
        return {"stage": stage, "state": "HTTP_%d" % r.status, "detail": r.body[:200]}
    try:
        reply = (json.loads(r.body) or {}).get("reply") or ""
    except ValueError:
        return {"stage": stage, "state": "BAD_JSON", "detail": r.body[:200]}
    if not reply.strip():
        return {"stage": stage, "state": "EMPTY_REPLY", "detail": r.body[:200]}
    # Responded is NOT delivered. Lead capture on this route is fire-and-forget.
    return {"stage": stage, "state": "RESPONDED", "detail": reply[:160]}


# ---------------------------------------------------------------- inbox

def imap_find_many(tokens, host, user, password, mailbox="INBOX", wait_s=180,
                   poll_s=15, purge=False):
    """Watch the inbox for several canaries under ONE shared deadline.

    Not one deadline per probe: three forms plus the chat, polled serially at
    180s each, is twelve minutes of cron spent on waits that overlap completely
    — every canary was posted within a few seconds of the others.

    ABSENT and UNKNOWN are different answers, per canary. UNKNOWN means the
    inbox could not be consulted and says nothing about whether the mail
    arrived. Reporting that as ABSENT would manufacture an outage; reporting it
    as OK would hide a real one. Both are worse than saying so.
    """
    waiting = list(dict.fromkeys(tokens))
    if not (host and user and password):
        return {t: {"stage": "inbox", "state": "UNKNOWN",
                    "detail": "no inbox credentials in environment; delivery not verified"}
                for t in waiting}
    out, last_err = {}, None
    deadline = time.time() + wait_s
    while waiting and time.time() < deadline:
        try:
            ctx = ssl.create_default_context()
            with imaplib.IMAP4_SSL(host, ssl_context=ctx) as M:
                M.login(user, password)
                M.select(mailbox)
                for t in list(waiting):
                    typ, data = M.search(None, 'TEXT', '"%s"' % t)
                    if typ == "OK" and data and data[0].split():
                        ids = data[0].split()
                        if purge:
                            for i in ids:
                                M.store(i, "+FLAGS", "\\Deleted")
                            M.expunge()
                        out[t] = {"stage": "inbox", "state": "DELIVERED",
                                  "detail": "%d message(s) carrying the canary%s"
                                            % (len(ids), " (purged)" if purge else "")}
                        waiting.remove(t)
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, e)
        if waiting and time.time() < deadline:
            time.sleep(poll_s)
    for t in waiting:
        out[t] = ({"stage": "inbox", "state": "UNKNOWN",
                   "detail": "inbox unreadable — %s" % last_err} if last_err else
                  {"stage": "inbox", "state": "ABSENT",
                   "detail": "no message carrying the canary within %ds" % wait_s})
    return out


def imap_find(token, host, user, password, mailbox="INBOX", wait_s=180, poll_s=15, purge=False):
    """Single-canary form of imap_find_many."""
    return imap_find_many([token], host, user, password, mailbox, wait_s, poll_s, purge)[token]


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

FIXTURE_LEAD_PAGE = """
<html><body>
<form id="contact-1" action="/wp-json/forminator/v1/form" method="POST"
      enctype="multipart/form-data">
  <input type="hidden" name="form_id" value="42">
  <input type="hidden" name="_wpnonce" value="abc123">
  <input type="text" name="name-1" required>
  <input type="email" name="email-1" required>
  <input type="tel" name="phone-1">
  <select name="service-1" required>
    <option value="">Choose a service</option>
    <option value="ocean">Ocean freight</option>
  </select>
  <input type="radio" name="mode-1" value="air">
  <input type="radio" name="mode-1" value="sea">
  <input type="checkbox" name="consent-1" value="1" required>
  <textarea name="message-1"></textarea>
</form>
<form id="search" action="/" method="get"><input type="search" name="s"></form>
</body></html>
"""
FIXTURE_LOGIN = """
<form id="loginform" action="/wp-login.php" method="POST">
  <input type="email" name="log" required><input type="password" name="pwd" required>
</form>
"""
FIXTURE_SUBSCRIBE_GET = """<form action="/subscribe" method="get">
<input type="email" name="em"></form>"""
FIXTURE_NO_EMAIL = """<form id="quote" action="/quote" method="POST">
<input type="text" name="zip"></form>"""


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

    # Which forms may be submitted at all. Each gate is proven to refuse AND,
    # via the lead form itself, to let the real thing through.
    page = find_forms(FIXTURE_LEAD_PAGE)
    leads = [f for f in page if is_probeable_lead_form(f)]
    check("picks exactly the lead form", [f["id"] for f in leads], ["contact-1"])
    check("refuses a GET search form",
          is_probeable_lead_form(find_forms(FIXTURE_SUBSCRIBE_GET)[0]), False)
    check("refuses a login form", is_probeable_lead_form(find_forms(FIXTURE_LOGIN)[0]), False)
    check("refuses a form with no email",
          is_probeable_lead_form(find_forms(FIXTURE_NO_EMAIL)[0]), False)
    check("reads the declared enctype", leads[0]["enctype"], "multipart/form-data")

    tok2 = "canary-selftest-1"
    addr2 = "Support+%s@shipousa.com" % tok2
    filled = dict(fill_form(leads[0], addr2, tok2))
    check("fills every named field", sorted(filled),
          ["_wpnonce", "consent-1", "email-1", "form_id", "message-1", "mode-1",
           "name-1", "phone-1", "service-1"])
    check("echoes the nonce verbatim", filled["_wpnonce"], "abc123")
    check("echoes the form id verbatim", filled["form_id"], "42")
    check("puts the canary in the email field", filled["email-1"], addr2)
    check("ticks a required consent box", filled["consent-1"], "1")
    check("skips the empty select placeholder", filled["service-1"], "ocean")
    check("collapses a radio group to one value", filled["mode-1"], "air")
    check("puts the token in the message", tok2 in filled["message-1"], True)

    # A monitor pointed at a per-deployment URL passes today and lies later.
    check("flags a per-deployment Vercel URL", is_ephemeral_deploy_url(
        "https://shipo-chat-8lqtfd5we-shipo-llc-s-projects.vercel.app/api/chat"), True)
    check("allows a bare project alias",
          is_ephemeral_deploy_url("https://shipo-chat.vercel.app/api/chat"), False)
    check("allows a scoped project alias", is_ephemeral_deploy_url(
        "https://shipo-chat-shipo-llc-s-projects.vercel.app/api/chat"), False)
    check("allows a custom domain",
          is_ephemeral_deploy_url("https://chat.shipousa.com/api/chat"), False)
    check("allows a project name ending in a digit",
          is_ephemeral_deploy_url("https://shipo-system1.vercel.app/api/chat"), False)

    # The two chat branches. The agent request must carry NO address, or it
    # goes down the lead path and this branch is never exercised.
    lead_msg = chat_lead_message("tok-A", "Support+tok-A@shipousa.com")
    agent_msg = chat_agent_message("tok-B")
    check("chat lead message carries the canary",
          "Support+tok-A@shipousa.com" in lead_msg, True)
    check("chat agent message carries its token", "tok-B" in agent_msg, True)
    check("chat agent message asks for a human", "human" in agent_msg.lower(), True)
    check("chat agent message leaves no address", "@" in agent_msg, False)

    body, ctype = encode_body([("email-1", "a+b@c.d")], "application/x-www-form-urlencoded")
    check("urlencodes the body", b"email-1=a%2Bb%40c.d" in body, True)
    mbody, mctype = encode_body([("email-1", "a@b.c")], "multipart/form-data")
    check("multipart declares its boundary",
          mctype.split("boundary=")[1] in mbody.decode(), True)
    check("multipart carries the value", b"a@b.c" in mbody, True)

    # The distinction the whole tool turns on.
    many = imap_find_many(["t1", "t2"], None, None, None)
    check("every canary reports UNKNOWN uncredentialed",
          [many["t1"]["state"], many["t2"]["state"]], ["UNKNOWN", "UNKNOWN"])
    miss = imap_find("tok", None, None, None)
    check("no credentials reports UNKNOWN", miss["state"], "UNKNOWN")
    check("UNKNOWN is never DELIVERED", miss["state"] == "DELIVERED", False)

    print("\nSELF-TEST %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 2


# ---------------------------------------------------------------- report

def verdict(results):
    """A path is OK only when a canary was seen in the inbox."""
    bad = [r for r in results if r["state"] in
           ("UNREACHABLE", "CORS_REFUSED", "BAD_JSON", "EMPTY_REPLY", "ABSENT",
            "REJECTED", "NO_LEAD_FORM", "EPHEMERAL_ENDPOINT")
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
    p.add_argument("--submit-forms", action="store_true",
                   help="put a canary THROUGH each lead form (off by default: this writes "
                        "a real submission to production and to whatever CRM sits behind it)")
    p.add_argument("--lead-pages", default="/contact-us/,/partner-program/",
                   help="pages that MUST carry a lead form; absence there is a finding")
    p.add_argument("--purge-canaries", action="store_true",
                   help="delete this run's own canary mail after verifying it (off by default)")
    p.add_argument("--json", default="")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()

    if a.self_test:
        return self_test()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("FORM WATCH — %s — %s\n" % (a.site, stamp))

    results, forms_seen, page_forms, page_jars = [], {}, {}, {}

    # 1. Structure. A changed signature is not itself an outage, but it is the
    #    single best predictor of one, and it is invisible to a status check.
    for path in [x.strip() for x in a.pages.split(",") if x.strip()]:
        url = a.site.rstrip("/") + path
        jar = new_jar()
        r = fetch(url, jar=jar)
        if not r.ok:
            results.append({"stage": "page " + path, "state": "UNREACHABLE",
                            "detail": r.error or "HTTP %s" % r.status})
            print("  %-28s UNREACHABLE  %s" % (path, r.error or r.status))
            continue
        fs = find_forms(r.body)
        forms_seen[path] = [form_signature(f) for f in fs]
        page_forms[path], page_jars[path] = fs, jar
        print("  %-28s %d form(s)" % (path, len(fs)))
        for f in fs:
            print("      %s%s" % (form_signature(f),
                                  "   <- lead" if is_probeable_lead_form(f) else ""))

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

    # 2. The forms, end to end. Off by default, because unlike every other check
    #    here this one WRITES: a real submission, in the real inbox, and in
    #    whatever CRM sits behind the form.
    pending = {}                       # canary token -> human label
    origin = a.site.rstrip("/")
    lead_pages = [x.strip() for x in a.lead_pages.split(",") if x.strip()]
    if a.submit_forms:
        print("")
        for path in [x for x in forms_seen if x in page_forms]:
            leads = [f for f in page_forms[path] if is_probeable_lead_form(f)]
            if not leads:
                # Only a page declared to carry a lead form can be BROKEN for
                # lacking one. Elsewhere a page without a form is just a page.
                if path in lead_pages:
                    results.append({"stage": "page " + path, "state": "NO_LEAD_FORM",
                                    "detail": "no submittable lead form where one must be"})
                    print("  %-28s NO_LEAD_FORM" % path)
                continue
            for f in leads:
                tok = canary_token()
                addr = canary_address(a.lead_inbox, tok)
                label = "form %s%s" % (path, (" #" + f["id"]) if f["id"] else "")
                sub = probe_form(origin + path, f, addr, tok, origin, jar=page_jars.get(path))
                results.append(sub)
                print("  %-34s %s  %s" % (label, sub["state"], sub["detail"][:60]))
                if sub["state"] == "POSTED":
                    pending[tok] = label
    else:
        results.append({"stage": "forms", "state": "UNKNOWN",
                        "detail": "--submit-forms not set; form delivery not verified"})
        print("\n  forms                        UNKNOWN  --submit-forms not set")

    # 3. The chat, end to end — BOTH of its lead paths.
    #    Leaving an address and asking for a human are different branches
    #    sending different emails. Probing only the first would leave the
    #    callback request, where the visitor has already asked to be phoned,
    #    completely unwatched.
    if a.chat_endpoint and is_ephemeral_deploy_url(a.chat_endpoint):
        results.append({"stage": "chat endpoint", "state": "EPHEMERAL_ENDPOINT",
                        "detail": "%s is a per-deployment URL; it dies on the next "
                                  "deploy. Point --chat-endpoint at the stable alias "
                                  "the website itself calls." % a.chat_endpoint})
        print("\n  %-34s %s  %s" % ("chat endpoint", "EPHEMERAL_ENDPOINT",
                                     "per-deployment URL, use the stable alias"))

    if a.chat_endpoint:
        tok = canary_token()
        addr = canary_address(a.lead_inbox, tok)
        print("\n  chat probe %s -> %s" % (tok, addr))
        c = probe_chat(a.chat_endpoint, a.chat_origin, tok,
                       chat_lead_message(tok, addr), kind="lead")
        results.append(c)
        print("  %-28s %s  %s" % ("chat lead response", c["state"], c["detail"][:80]))
        if c["state"] == "RESPONDED":
            pending[tok] = "chat lead"

        atok = canary_token()
        print("  chat agent-request probe %s" % atok)
        ac = probe_chat(a.chat_endpoint, a.chat_origin, atok,
                        chat_agent_message(atok), kind="agent request")
        results.append(ac)
        print("  %-28s %s  %s" % ("chat agent response", ac["state"], ac["detail"][:80]))
        if ac["state"] == "RESPONDED":
            pending[atok] = "chat agent request"
    else:
        results.append({"stage": "chat", "state": "UNKNOWN",
                        "detail": "no --chat-endpoint configured; chat not checked"})
        print("\n  chat                         UNKNOWN  no endpoint configured")

    # 4. One inbox watch covering every canary sent above.
    if pending:
        print("\n  watching the inbox for %d canary/ies, up to %ds" % (len(pending), a.wait))
        found = imap_find_many(list(pending),
                               os.environ.get("SHIPO_IMAP_HOST", "imap.gmail.com"),
                               os.environ.get("SHIPO_IMAP_USER"),
                               os.environ.get("SHIPO_IMAP_PASS"),
                               wait_s=a.wait, purge=a.purge_canaries)
        for tok, label in pending.items():
            d = dict(found[tok])
            d["stage"] = "%s delivery" % label
            results.append(d)
            print("  %-34s %s  %s" % (d["stage"], d["state"], d["detail"]))

    code = verdict(results)
    print("\nVERDICT %s" % {0: "ALL PROVEN", 1: "FINDINGS", 2: "COULD NOT FULLY CHECK"}[code])
    if a.json:
        with open(a.json, "w") as fh:
            json.dump({"site": a.site, "at": stamp, "forms": forms_seen,
                       "results": results, "exit": code}, fh, indent=1)
    return code


if __name__ == "__main__":
    sys.exit(main())
