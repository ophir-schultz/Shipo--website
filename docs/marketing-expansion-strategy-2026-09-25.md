# Marketing Expansion Strategy — read date 2026-09-25

**Picks up from:** `shipo-system/docs/project-log-2026-08-10.md` (the last full recap)
**Engine of record:** `ophir-schultz/marketing-platform` (last push 2026-09-25 09:23 UTC; `clients.json` updated 2026-09-19, one active tenant: `shipo`)

## How this document was produced, and what that limits

Every finding below came from **live web search on 2026-09-25**. Nothing here was
carried over from memory or assumed.

What could **not** be done, and why it matters for how much you trust this:

- **shipousa.com was never crawled.** This container's network policy denies the
  host, so `cold_audit.py` returned `could not audit` rather than a clean report.
  An empty audit is not a passing audit — that distinction is the whole point of
  the tool's exit codes, so no claim about the current state of the site's own
  pages is made here.
- **Every competitor figure below is a third-party search snippet, not a verified
  number.** They are written as *reported*, with the source named. Under
  `docs/fact-gate.md` none of them may enter published copy or a rate card
  comparison until someone reads them off the competitor's own page and dates
  them. They are good enough to *prioritise* with and not good enough to *publish*.

Only search results are available from here; direct page fetches are blocked too.
To let the engine actually audit the site from a session like this, the
environment's **Network access** setting needs `shipousa.com` allowed (or a
broader access level) — the cloud environment menu in the title bar, then Edit.

## 1. What changed since the 2026-08-10 log

The single biggest open item in that log has closed, and it closed well.

**Amazon SPN is live.** Task #21 was "submitted → Pending Review". Shipo LLC is
now listed in Amazon's Service Provider Network under **FBA Prep & Packaging**,
and it has been announced:

| outlet | what it is |
|---|---|
| openpr.com | "Shipo LLC Listed in Amazon's Service Provider Network for FBA Prep & Packaging as Q4 2026 Inbound Deadlines Approach" |
| prunderground.com | same release, "Opens Q4 FBA Prep Capacity in Delaware" |
| lifestyle.middletownlifemagazine.com | regional pickup of the same release |

Two other assets now show up in search that the August log did not mention:

- The Wilmington facility is described as **FDA-registered as a food facility**,
  which opens food, beverage and dietary supplement inventory — a category most
  prep centers must decline.
- **55,000 sq ft** is now the figure carried consistently across the site,
  Racklify and Fulfill.com (the log's reconciliation work held).

**This is the asset the next 90 days should be spent on.** An SPN listing plus an
FDA food registration is a qualification story almost no Delaware prep center can
match, and right now it is sitting in three press releases and nowhere else.

## 2. The scoreboard: where Shipo is actually cited

This is the finding that should drive everything else.

### Present ✅

| surface | status on 2026-09-25 |
|---|---|
| Amazon SPN | listed, FBA Prep & Packaging |
| Fulfill.com | full 3PL profile live |
| Racklify | listed, 55,000 sq ft correct |
| openpr / PR Underground / Middletown Life | SPN release carried |
| shipousa.com | ranks for the branded query |

### Absent ❌ — and this is the gap

Shipo appears in **none** of the pages that answer a non-branded buyer question.
Searched on 2026-09-25:

- `best Amazon FBA prep center East Coast 2026` → **Shipo absent.**
  Cited instead: amzprep.com, redstagfulfillment.com, prepvia.com,
  fbaprepfinder.com, litefulfillment.com, exceptionalsellers.com,
  wholesaleseeker.com, ainfluencer.com.
- `FBA prep center Delaware no sales tax Wilmington` → **Shipo absent.**
  Cited instead: Smart Prep Center, Lite Fulfillment, East Coast Prep and Ship,
  Dollan Prep Center, prepcenterdelaware.com, hopstack.io directory,
  prepcentersearch.com, smartprepcenter.com.

Shipo surfaces only when its **name** is in the query. That is the signature of a
brand with good directory hygiene and no presence in the comparison layer — and
the comparison layer is precisely what LLMs and AI Overviews quote when a seller
asks "who should prep my FBA inventory in Delaware?"

The 0% sales tax angle is the sharpest illustration. It is Shipo's headline
positioning, and on the query that states it almost verbatim, five competitors
answer and Shipo does not.

## 3. The Delaware competitive set

Everyone below is inside an hour of 310 Cornell Dr and competes for the same
seller. All figures are **as reported in search snippets on 2026-09-25 — unverified.**

| competitor | city | reported detail |
|---|---|---|
| Smart Prep Center | Wilmington, DE | **1,000 sq ft** warehouse; FBA from **$0.70/item** wholesale; StartUp pricing, additional unit in same order $0.50 |
| East Coast Prep and Ship | Wilmington, DE | **$0.80–$1.50/unit** by tier; bin storage **$0.50/cu ft/mo**; pallet **$40/mo**; FBA + WFS + SFP + DTC |
| Lite Fulfillment | Wilmington, DE | **500+ brands**; same-day; no long-term contracts; supplement fulfillment |
| Dollan Prep Center | Newark, DE | 210 Executive Dr; wholesale, private-label, online-arbitrage |
| Delaware Prep & Fulfillment Center | DE | Fulfill.com profile with pricing/reviews |
| prepcenterdelaware.com | DE | FBA prep + order fulfillment |
| Regional NJ centers | Pennsauken NJ | **$0.45–$0.85/unit** tiers, 24–48h to Amazon, no minimums |

**Read the first row again.** Smart Prep Center is reported at **1,000 sq ft** and
out-ranks Shipo on Delaware prep queries. Shipo is reported at **55,000 sq ft**
— roughly 55× the footprint — with SPN status and an FDA registration, and loses
the search. Nothing about that gap is a capability problem. It is entirely a
distribution problem, which is the good kind: it can be fixed by publishing.

**Pricing reality check.** The NJ tier starts at $0.45/unit and Smart Prep at
$0.70/item against Shipo's **$500 monthly minimum**. Shipo cannot win the
cheapest-per-unit comparison and should stop being entered in it. The $500
minimum was set deliberately so small accounts cannot lose money — that is a
qualification filter, and it should be marketed as one. SPN + FDA + 55,000 sq ft
+ 0% sales tax is a *serious-inventory* pitch, not a bargain pitch.

## 4. The expansion plan, in priority order

Ordered by leverage per `docs/playbook-earned.md`, which is explicit that the
highest-value earned work is rarely "find another directory".

### P0 — Get into the comparison layer (the actual gap)

The listicles in §2 are the pages that get quoted. Each needs a different route
and they should not be treated as one task:

1. **fbaprepfinder.com** — publishes "Amazon FBA prep centers in Delaware: **4
   verified** (2026)" and a verified-center list. A *verified* directory with a
   named count is the single best target on this list: it is small, it is
   Delaware-specific, and inclusion is a real signal rather than a link. Find its
   submission route and apply.
2. **prepcentersearch.com/states/delaware** and
   **hopstack.io/fba-prep-center-directory/** — directory submissions, same
   pattern as the Racklify and Fulfill.com listings that already worked.
3. **Editorial listicles** (amzprep, prepvia, wholesaleseeker,
   exceptionalsellers, ainfluencer, logos3pl "Top 3PLs in Wilmington DE 2026",
   stone-mgt "Best 3PL Warehouses in Delaware") — these are pitches, not
   submissions. The SPN listing is the news hook and it is time-sensitive: "an
   Amazon-SPN-listed, FDA-registered 55,000 sq ft Delaware prep center with Q4
   capacity" is a reason for a Q4 roundup to add a row. Reuse the
   `docs/backlink-connectively-pitch-kit.md` structure.
4. Note that **litefulfillment.com and redstagfulfillment.com rank for these
   queries with their own listicles.** A competitor publishing the comparison page
   is how this layer gets owned. Shipo has no equivalent page.

### P1 — Publish the pages that answer the questions Shipo loses

Own-site work, no external dependency, per `docs/playbook-owned.md`:

- **A Delaware prep-center comparison page.** Shipo is the only one of these
  companies that can honestly publish a table including SPN status, FDA food
  registration and square footage. Build it from verified figures only; where a
  competitor's number is unverified, say so on the page — the fact gate's own note
  is right that visible self-disclosure reads as more credible than most sourced
  statistics.
- **An FDA / food-and-supplement fulfillment page.** This is a category most of
  the competitive set must turn away, and there is currently no query for which
  Shipo is the obvious answer. This could be it.
- **A "why the $500 minimum exists" page.** Turn the objection into the
  qualification filter it actually is, and stop competing on $/unit.

### P2 — Carry the open items forward

From the August log, restated with what today's findings change:

| # | item | status / what changed |
|---|---|---|
| #20 | Apollo FBA outreach | in progress. The SPN listing is a materially stronger opener than anything in the August sequences — the messaging should be rewritten around it before more sends. |
| #25 | Referral + P&L dashboard | in progress in `shipo-system` (`/marketing`, `/pnl`, `campaigns_pnl.sql`). |
| #27 | Referral agreement | **still blocked on Delaware attorney review.** Unchanged, and still must not be used before it. |
| #28 | Deliverability warmup | getshipo.com warmup was ~4 weeks from early August and should now be complete or nearly so. **Verify before unfreezing cold sends** — do not assume the calendar did the work. |
| #29 | A/B tests | pending. Worth sequencing *after* the SPN-led rewrite, so the test compares the new opener against the old one. |

### P3 — Unblock the engine

`content_gen.py` and `publisher.py --post` both refuse a profile whose
`profile_status` starts with `DRAFT`, and `daily.py` declines content generation
for one. Until the `shipo` profile's `differentiators`, `verified_numbers` and
`banned_claims` are filled in by hand, the engine can verify and score but **will
never publish**. That gate is correct and should not be bypassed; it just means
verifying the profile is a prerequisite for any automated publishing, not a
tidy-up task.

Two claims to resolve while doing it, both of which the platform's own docs
already flag as trap patterns:

- **"nine years" in Wilmington** — a hand-written duration is the
  `STALE_DATED_CLAIM` case and goes silently wrong every January. Replace with a
  founding year and let the reader subtract.
- **"6.43 million orders picked and packed"** — a magnitude figure, so the fact
  gate treats it as a statistic needing a source and a date, not an offer.

## 5. What is genuinely true right now

- Shipo's *qualifications* are ahead of its Delaware competitive set: SPN listing,
  FDA food facility, 55,000 sq ft, 0% sales tax, nine years operating.
- Shipo's *discoverability* is behind a reported 1,000 sq ft competitor on the
  exact query describing its own headline positioning.
- The gap is distribution, not capability, and the SPN listing is a fresh,
  dated, verifiable news hook that expires with the Q4 inbound deadlines.

The expansion is therefore not "more channels". It is getting a company that has
already earned the credentials into the layer where buyers and LLMs compare
credentials, before Q4 closes.
