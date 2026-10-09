# Implementation prompt

This is the brief used to build the Claims Delay Root-Cause Explorer with an AI coding assistant. It is kept in the repository so the project can be reproduced or extended from the same starting point.

Attach the capstone brief and the claims process slides when using it.

---

Build a working demo called "Claims Delay Root-Cause Explorer" for a healthcare payer capstone. It will be presented to the CIO and CTO to win funding, so the audience is business leaders in claims operations, not engineers.

## The problem

The brief says: *"Ops leaders can't see which delay themes drive claim volume or where to intervene first."* AI pattern: classification, root-cause clustering, insight dashboard. Sample data: claim records, status timestamps, pend/denial codes, adjuster notes.

A claim moves through four stages: Intake → Pre-Adjudication → Adjudication → Post-Adjudication. A claim the system cannot process automatically is "pended" for a person to work; that wait is the delay.

Before writing code, explain back to me why leaders cannot see the causes today: generic pend codes, the real reason sitting in free-text adjuster notes, claim counts overstating quick causes, and aggregated reports hiding the day a problem began.

I have attached the process slides. Use the checks listed under each stage to define the delay themes, and do not invent process steps that are not on them.

## What to build

1. **Synthetic data generator.** One row per claim for every calendar day in a configurable date window (default 90 days), never weekly or bi-weekly buckets.
   - Include line of business, platform, submission channel, provider, specialty, network status, billed amount, timestamps for all four stages, and for pended claims a pend code, adjuster note and manual touch count.
   - Plant known patterns so findings can be checked: a theme concentrated in certain specialties, a theme that spikes on one platform in the last three weeks of the window, a frequent-but-quick theme versus a rare-but-slow one, a share of pends with only a generic code, and paper claims that are slow at intake.
   - Keep the true cause in hidden columns for evaluation only.
   - The window must be changeable three ways: a CLI flag, environment variables, and a control in the UI that regenerates data without a restart.

2. **Classifier.** Read the adjuster note plus pend code and assign one delay theme. Train on a small labelled sample, score on held-out claims, and send low-confidence predictions to "Needs human review" instead of guessing.

3. **Root-cause clustering.** Inside each theme, group notes that say the same thing and describe each group by its distinctive phrases and one typical note. Do not hand-name clusters.

4. **Analytics service.** Days lost (the main impact measure), first-pass rate, time in each stage, daily series, rising themes with onset date and the segment driving the rise, segment hotspots, and interventions ranked by removable delay per unit of effort.

5. **Dashboard** with separate tabs rather than one long page: Summary, Claim journey, Root causes, Daily trends, Where to act (with an adjustable business case), Claims (with a per-claim timeline), Ask the analyst, and How it works.
   - Global filters for date range, line of business and platform.
   - Cover Intake delay explicitly: both claims stopped at intake and claims that are slow there without being stopped.

6. **AI analyst.** A tool-calling agent over read-only tools that wrap the same analytics the dashboard uses, so the two cannot disagree.
   - Use any OpenAI-compatible chat endpoint configured through `.env`.
   - If no model is configured or the call fails, fall back to a built-in analyst that routes the question to the same tools, and say so in the UI.
   - Show which lookups each answer used.

## Standards

- **Do not hallucinate.** Every number on screen or in an analyst answer must be computed from claim rows. Anything that is a judgement (how much delay an intervention removes, effort, cost per manual touch, turnaround target) must live in one place and be labelled as an assumption in the UI.
- **Be honest about the data.** Say plainly in the UI and README that the data is synthetic and that model accuracy will be lower on real notes.
- **Layered architecture.** API routes only parse and delegate; one analytics service computes all numbers; machine learning runs at build time, not per request; domain wording (stages, themes, why it happens, what to do, owner) lives in one module; settings come from environment variables. No boilerplate, no dead code.
- **UI quality.** Enterprise standard, written for a business reader in plain language.
  - No overlapping or clipped elements at laptop, projector and phone widths. Check this by rendering each tab and looking at it.
  - Charts show one bar per day. Colour encodes the four stages consistently.
  - Bundle the chart library and typefaces locally so the demo works offline. Use a distinctive, professional typeface pairing rather than system defaults.
  - Do not use the company's logo or branding.
- **Tests** that prove the important things: every calendar day is present, totals reconcile across endpoints, the planted incident is found on the right day and segment, classifier accuracy clears a floor, the analyst cites its lookups, and regenerating for another period works.

## Deliverables

- The project, runnable on a MacBook with one command, plus the manual commands.
- `README.md` covering:
  - the problem in plain terms
  - how to run it
  - how to get data for another date range
  - how to connect a language model
  - what each tab answers
  - a five-minute demo path
  - a thorough architecture section: system diagram, layers and their rules, build-time steps, run-time request flow, analyst flow, measure definitions, themes by stage, API table, design decisions with reasons, and the steps followed to build it
  - what is measured versus assumed
  - what it would take to go to production
- Run the tests and a clean install before handing over, and tell me anything you could not verify.
