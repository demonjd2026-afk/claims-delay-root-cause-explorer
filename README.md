# Claims Delay Root-Cause Explorer

Shows claims operations leaders which delay themes drive pended claim volume, what the root causes inside each theme are, and where to intervene first.

Built for the capstone brief: *"Ops leaders can't see which delay themes drive claim volume or where to intervene first."* AI pattern: classification, root-cause clustering, insight dashboard. Data: claim records, status timestamps, pend/denial codes, adjuster notes.

All data is synthetic. No real member, provider or claim information is used.

**Contents:** [The problem](#the-problem-in-plain-terms) · [Run it](#run-it-on-a-mac) · [Data for another date range](#data-for-another-date-range) · [Language model](#connecting-a-language-model-optional) · [The tabs](#the-tabs) · [Demo path](#a-five-minute-demo-path) · [Architecture](#architecture) · [Assumptions](#what-is-measured-and-what-is-assumed) · [To production](#from-demo-to-production)

## The problem, in plain terms

A claim moves through four stages: **Intake → Pre-Adjudication → Adjudication → Post-Adjudication**. Most claims pass through automatically in a few days. A claim that the system cannot process on its own is *pended*: it stops and waits for a person. That wait is the delay.

Leaders cannot see what is causing the delays for three reasons:

1. **Pend codes are too coarse.** A large share of pends carry a generic "manual review" code. The real reason is in the free-text note the adjuster wrote, which nobody can read at scale.
2. **Claim counts mislead.** The most frequent cause is often quick to clear, while a rarer cause can hold claims for weeks. Ranking by count sends effort to the wrong place.
3. **Reports are aggregated.** Weekly or monthly totals hide the day a problem started and the platform or provider group it started in.

## Run it on a Mac

Requires Python 3.10 or newer (`python3 --version`). If it is missing: `brew install python`.

```bash
cd claims-delay-explorer
./run.sh
```

Then open **http://localhost:8000**. The first run creates a virtual environment, installs dependencies, builds the data (about 10 seconds) and starts the server. Later runs start immediately. Stop with `Ctrl+C`.

The same steps by hand:

```bash
cd claims-delay-explorer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.pipeline              # generate claims, train the classifier, cluster root causes
uvicorn app.main:app --port 8000    # start the app
```

Other commands:

```bash
pytest                              # run the tests (about 20 seconds)
PORT=8080 ./run.sh                  # use another port
```

No internet connection is needed once dependencies are installed. The chart library and both typefaces are bundled in `web/`.

## Data for another date range

There are three ways to answer "show me a different period", from fastest to most thorough.

| You want | Do this | Time |
|---|---|---|
| A shorter period inside the loaded data | Change **From** and **To** at the top of any tab | Instant |
| A different period, during the demo | **How it works** tab → **Data period** → pick dates → **Generate data** | About 10 seconds for a quarter, 30 for a year |
| A different period, before the demo | `python -m app.pipeline --start 2026-01-01 --end 2026-06-30`, then restart | Same |

Generating builds one set of claims for **every calendar day** in the range, then reruns classification and clustering. The range must be between 63 and 366 days, because rising-theme detection compares the latest 21 days with the 42 before.

```bash
python -m app.pipeline --start 2025-10-01 --end 2026-09-30    # a full year
python -m app.pipeline --seed 7                                # same dates, a different random draw
python -m app.pipeline                                         # back to the default quarter
```

The planted patterns move with the window. The provider / tax ID incident always covers the last 21 days of whatever range you generate, so the "rising theme" story works for any period.

## Connecting a language model (optional)

Without any configuration the analyst runs in **built-in mode**: it matches the question to a lookup and reports the result. It makes no outside calls.

To enable free-form conversation, copy `.env.example` to `.env`, fill in the three values and restart:

```
LLM_BASE_URL=https://api.anthropic.com/v1
LLM_API_KEY=your-key
LLM_MODEL=claude-sonnet-5-5
```

Any OpenAI-compatible chat completions endpoint with tool calling works: change the base URL and model name for another provider, or use `http://localhost:11434/v1` for a local Ollama model. If the model cannot be reached, the built-in analyst answers and says so.

Use only an endpoint your organisation has approved. With real data, claim notes can contain protected health information.

## The tabs

| Tab | Question it answers |
|---|---|
| Summary | How big is the problem, what causes it, what should we do first? |
| Claim journey | At which of the four stages do claims get stuck, and for how long? Includes intake time by submission channel. |
| Root causes | For one theme: why does it happen, what are the specific causes, who is affected? |
| Daily trends | What changed, on which day, and where? One bar per calendar day. |
| Where to act | Ranked interventions with owners, and an adjustable business case. |
| Claims | The individual delayed claims, with full timeline and adjuster note. |
| Ask the analyst | Plain-English questions and answers. |
| How it works | Data period control, method, measured model accuracy, and what is assumed. |

The date range, line of business and platform filters at the top apply to every tab.

## A five-minute demo path

1. **Summary.** Read the four findings left to right. Format errors are 14% of pended claims but 2% of days lost.
2. **Claim journey.** A straight-through claim takes about 3 days and a pended one about 11. 80% of lost days are in Adjudication. At Intake, paper claims wait over a day to be scanned and are stopped three times as often as electronic ones.
3. **Root causes → Prior authorization.** About four in ten of these claims have an authorization on file that the system could not match. That is a matching fix, not a provider behaviour problem.
4. **Daily trends.** The provider / tax ID theme more than doubled over the last three weeks, almost entirely on one platform. A weekly report would have shown this late and without the cause.
5. **Where to act.** Enter your own annual claim volume and cost per touch and tick the interventions to fund.
6. **Ask the analyst.** "Is anything getting worse recently?"
7. **If asked for another period:** How it works → Data period → Generate data.

---

## Architecture

### The whole system in one picture

```
                         BUILD TIME  (python -m app.pipeline, or "Generate data" in the UI)
 ┌────────────────┐   ┌────────────────┐   ┌────────────────┐   ┌──────────────────────────┐
 │ 1 GENERATE     │──▶│ 2 CLASSIFY     │──▶│ 3 CLUSTER      │──▶│ 4 SAVE                   │
 │ data/generator │   │ ml/classifier  │   │ ml/clustering  │   │ data/claims_enriched.csv │
 │ claims, stage  │   │ note + pend    │   │ group notes    │   │ data/model_report.json   │
 │ timestamps,    │   │ code → theme,  │   │ inside each    │   │ (themes, confidence,     │
 │ codes, notes   │   │ confidence     │   │ theme          │   │  clusters, accuracy)     │
 └────────────────┘   └────────────────┘   └────────────────┘   └────────────┬─────────────┘
                                                                             │ loaded once
                         RUN TIME  (uvicorn app.main:app)                    ▼
 ┌──────────────┐  HTTP  ┌──────────────┐      ┌───────────────────┐   ┌──────────────┐
 │ Browser      │◀──────▶│ api/routes   │─────▶│ services/analytics│──▶│ data/store   │
 │ web/ (8 tabs)│  JSON  │ parse, check │      │ every number is   │   │ claims in    │
 └──────────────┘        │ delegate     │      │ computed here     │   │ memory       │
                         └──────┬───────┘      └─────────▲─────────┘   └──────────────┘
                                │ POST /api/chat         │ same functions
                                ▼                        │
                         ┌──────────────┐      ┌─────────┴─────────┐   ┌──────────────┐
                         │ agent/analyst│─────▶│ agent/tools       │   │ Language     │
                         │ orchestrates │      │ 8 read-only tools │   │ model        │
                         │              │◀────────────────────────────▶│ (optional)   │
                         └──────────────┘                              └──────────────┘
```

Two things to remember: the heavy AI work happens **once, at build time**, so the dashboard is fast; and the dashboard and the analyst read from **the same analytics functions**, so they cannot disagree.

### Layers and what each one is allowed to do

| Layer | Folder | Responsibility | Rule it follows |
|---|---|---|---|
| Presentation | `web/` | Draws the eight tabs. Plain HTML, CSS and JavaScript modules, one module per tab. | Never calculates a business number. It only displays what the API returns. |
| API | `app/api/routes.py` | Receives requests, validates input, returns JSON. | No business logic. Each endpoint is a few lines that delegate. |
| Services | `app/services/analytics.py` | KPIs, theme ranking, daily series, rising themes, hotspots, intervention ranking, claim detail. | The only place numbers are computed. |
| Agent | `app/agent/` | Answers questions. `tools.py` wraps the services, `llm.py` talks to the model, `analyst.py` runs the conversation. | Can only read, and only through the tools. |
| Machine learning | `app/ml/` | Theme classifier and root-cause clustering. | Runs at build time only. |
| Data | `app/data/` | `generator.py` creates synthetic claims. `store.py` loads them once and adds derived measures. | The store is read-only at run time. |
| Domain | `app/domain.py` | The four stages, the 13 themes, and the playbook (why it happens, what to do, owner). | Single source for all business wording. |
| Configuration | `app/config.py` | Date window, turnaround target, confidence floor, model endpoint. | Everything adjustable comes from environment variables. |

### Build time, step by step

Run by `app/pipeline.py`. A quarter takes about 10 seconds.

**Step 1. Generate claims** (`data/generator.py`)
- Creates about 760 claims per weekday and 240 per weekend day for every calendar day in the window.
- Gives each claim a line of business, platform, submission channel, provider, specialty, network status and billed amount.
- Decides whether the claim pends and for which reason, using rates that vary by segment (for example radiology claims hit prior authorization three times as often).
- Writes the timestamps: received, intake complete, pre-adjudication complete, adjudicated, finalized, and for pended claims the moment it pended and the moment it was released.
- For pended claims, writes a pend code, an adjuster note and a count of manual touches. About 27% get only a generic pend code, and about 5% get a note with no useful detail.
- Keeps the true cause in two hidden columns, used only to measure accuracy.

**Step 2. Classify the delay theme** (`ml/classifier.py`)
- Input: the adjuster note plus the pend code, for each pended claim.
- Takes 1,200 pended claims as the labelled sample, the stand-in for claims tagged by subject matter experts.
- Turns the text into numbers with TF-IDF (single words and word pairs) and trains a logistic regression.
- Holds back a quarter of the labelled sample, never shows it to the model, and scores the model on it. That is the accuracy shown on the How it works tab.
- Predicts a theme and a confidence for every pended claim. Below 55% confidence the claim goes to **Needs human review** instead of being forced into a theme.

**Step 3. Cluster the root causes** (`ml/clustering.py`)
- Works inside one theme at a time, on the adjuster notes only.
- Groups notes with k-means. Tries 2 to 5 groups, scores each with the silhouette measure, and keeps the simplest split that is nearly as clean as the best.
- Describes each group by its most distinctive phrases and by the single note closest to the group's centre. Nothing is named by hand.

**Step 4. Save** (`pipeline.py`)
- `data/claims_enriched.csv.gz`: every claim, plus predicted theme, confidence and cluster.
- `data/model_report.json`: the date window, classifier accuracy per theme, cluster descriptions and cluster quality.

### Run time: what happens when a tab opens

1. The browser requests, for example, `GET /api/overview?date_from=…&lob=Medicaid`.
2. `api/routes.py` turns the query string into a `Filters` object and asks the store for the claims.
3. `data/store.py` returns the claims already held in memory. It loaded them once at start-up and added the derived measures: days pended, days in each stage, age, over-target flag.
4. `services/analytics.py` applies the filters and computes the result from claim rows.
5. The route returns JSON. The tab's JavaScript module draws it.

Every chart on the Daily trends tab is built from a series with one value for each calendar day, including days with zero.

### Run time: what happens when someone asks the analyst

**With a language model connected**

1. The browser sends the question, the last ten messages and the current filters to `POST /api/chat`.
2. `agent/tools.py` builds eight read-only tools bound to those filters.
3. `agent/analyst.py` sends the question and the tool descriptions to the model.
4. The model replies with the tools it wants to call, for example `find_emerging_themes`.
5. The analyst runs each tool against the analytics service and sends the results back to the model.
6. Steps 4 and 5 repeat, up to six rounds, until the model writes its answer.
7. The answer is returned with the list of tools used, shown under the answer as "Based on".

**Without a language model, or if it fails**

1. The built-in analyst matches the question to a tool by keyword.
2. It runs the same tool and writes the answer from a fixed sentence pattern.
3. If it stepped in because the model failed, the answer says so.

The eight tools: summary, rank delay themes, explain a theme, find rising themes, recommend interventions, compare segments, stage breakdown, look up a claim.

### Run time: what happens on "Generate data"

1. The browser sends the chosen dates to `POST /api/data/rebuild`.
2. The range is validated (63 to 366 days). A lock prevents two rebuilds at once.
3. The build-time pipeline runs for the new window and overwrites the two data files.
4. The in-memory store is cleared and reloaded.
5. The browser reloads its filters and every tab shows the new period. No restart is needed.

### How the key measures are defined

| Measure | Definition |
|---|---|
| Pended claim | A claim that fell out of automatic processing and waited for a person. |
| Days pended | Pend release time minus pend start time. For a claim still pended, the as-of date is used. |
| Days lost | Days pended, added up across claims. The main measure of impact. |
| First-pass rate | Share of claims that were never pended. |
| Over target | From receipt to finalization (or to the as-of date if open) is more than 30 days. |
| Rising theme | Daily pends in the latest 21 days are at least 1.4 times the 42 days before, and the rise is statistically clear. The tool then reports the first day it broke out and the segment contributing most. |
| Priority score | Days lost × assumed addressable share ÷ effort weight (low 1, medium 2, high 3.5). |

### The 13 delay themes, by stage

| Stage | Themes |
|---|---|
| Intake | Claim format or data errors · Misrouted or needs splitting at intake |
| Pre-Adjudication | Member could not be matched · Provider or tax ID could not be matched · Possible duplicate claim · Fraud, waste and abuse review |
| Adjudication | Coverage or eligibility discrepancy · Prior authorization missing or not matched · Clinical edit or bundling review · Medical records needed for clinical review · Other insurance information needed · Manual pricing or contract not loaded |
| Post-Adjudication | Payment could not be released |

Plus **Needs human review** for notes too vague to classify.

Intake delay is shown two ways: claims *stopped* at intake (the two themes above), and claims that are simply *slow* at intake without being stopped (paper claims waiting to be scanned and keyed, on the Claim journey tab).

### API

| Endpoint | Returns |
|---|---|
| `GET /api/meta` | Date range, filter options, themes, stages, analyst mode |
| `GET /api/overview` | KPIs, daily received and pended, theme table, key findings, top three interventions |
| `GET /api/journey` | Per-stage pends, time in stage, themes per stage, intake by channel |
| `GET /api/themes/{key}` | Playbook, measures, root-cause clusters, daily series, segments, examples |
| `GET /api/trends` | Daily series by stage and by theme, rising themes |
| `GET /api/hotspots?dimension=` | Pends per 1,000 claims for every theme and segment value |
| `GET /api/interventions` | Ranked interventions with removable days and touches |
| `GET /api/claims`, `GET /api/claims/{id}` | Paged claim list; one claim's timeline and note |
| `GET /api/model` | Classifier and clustering quality |
| `POST /api/chat` | Analyst answer and the tools it used |
| `POST /api/data/rebuild` | Regenerates data for a date range |

All `GET` endpoints accept `date_from`, `date_to`, `lob` and `platform`. Interactive documentation is at `http://localhost:8000/docs`.

### Design decisions and the reason for each

| Decision | Reason |
|---|---|
| Classify and cluster at build time, not per request | The dashboard stays fast, and results are the same every time a leader opens it. |
| A simple, explainable classifier (TF-IDF + logistic regression) | Trains in seconds on a small labelled sample, gives a confidence for every claim, and can be explained to an auditor. |
| A confidence floor with a "Needs human review" bucket | An unattributed claim is more honest than a wrong attribution. |
| Rank by days lost, not claim count | Count overstates quick, frequent causes. |
| One analytics service behind both the dashboard and the analyst | One definition of every number. |
| The analyst only has read-only tools | It cannot change data, and it can only quote figures the dashboard would show. |
| A built-in analyst as fallback | The demo works with no network and no key. |
| No front-end build step | Runs from a fresh laptop with Python only. |
| Assumptions kept in one file and labelled in the UI | Leaders can see which numbers are measured and which are judgement. |

### Steps followed to build it

1. **Understand the problem.** Read the brief and the claims process slides. Settled that "delay" means time spent pended, and that the question is which causes cost the most days.
2. **Define the measures.** Days pended, days lost, first-pass rate, over target. Chose days lost as the ranking measure.
3. **Define the themes.** Took the checks listed under each of the four stages in the process slides and turned each failure point into a theme, with an owner and an intervention.
4. **Build realistic synthetic data.** Daily volumes, stage timestamps, codes and notes, with known patterns planted so the tool's findings could be checked against the truth.
5. **Classify.** Trained on a small labelled sample, measured on held-back claims, added the confidence floor.
6. **Cluster.** Grouped notes inside each theme and described the groups automatically.
7. **Measure.** Built the analytics service: KPIs, daily series, rising themes with onset and driver, hotspots.
8. **Decide.** Ranked interventions and added a business case with adjustable assumptions.
9. **Present.** Built the eight tabs for a business reader: plain wording, one idea per card, one bar per day.
10. **Converse.** Added the analyst on top of the same analytics, with a language model optional.
11. **Verify.** Twelve automated tests: every day present, totals reconcile, the planted incident is found on the right day and platform, accuracy above 90%, the analyst cites its lookups, a rebuild for another period works.

### Project layout

```
claims-delay-explorer/
  run.sh                   One command to set up and start
  requirements.txt
  .env.example             Optional settings
  app/
    main.py                FastAPI app; serves the API and the dashboard
    config.py              Settings
    domain.py              Stages, themes, playbook
    pipeline.py            Build: generate → classify → cluster → save
    api/routes.py          HTTP endpoints
    services/analytics.py  All computed numbers
    agent/                 analyst.py, tools.py, llm.py
    ml/                    classifier.py, clustering.py
    data/                  generator.py, store.py
  web/
    index.html             Shell: sidebar, filters, view area
    css/app.css
    js/app.js              Navigation, filters, view lifecycle
    js/api.js              API client
    js/ui.js               Shared helpers: formatters, bars, charts
    js/views/              One file per tab
    fonts/, vendor/        Bundled typefaces and chart library
  tests/test_app.py
  data/                    Created by the pipeline (not in version control)
```

---

## The synthetic data

By default: 54,862 claims received on each of the 90 days from 1 July to 28 September 2026, with status as of 30 September. About 9% are pended.

Patterns planted on purpose, which the tool finds without being told:

- Prior-authorization pends concentrate in radiology, orthopedics and outpatient surgery.
- Provider / tax ID pends rise sharply on one platform for the last three weeks of the window.
- Format errors are frequent but short. Medical-record pends are rarer but long.
- Paper claims take over a day at intake and are stopped there more often.
- About 27% of pends carry only a generic pend code.

## What is measured and what is assumed

**Measured from the claim rows:** claim counts, days pended, days lost, manual touches, trends, rising themes, segment rates, classifier accuracy.

**Assumptions, shown as such in the UI:**

- *Addressability* and *effort* for each intervention, set in `app/domain.py`. Replace with operations' own estimates.
- *Cost of a manual touch* in the business case. The default is a placeholder. Use Finance's figure.
- *30-day turnaround target*, set by `CDE_SLA_DAYS`. Set it to the applicable contract or state rule.
- *Platform by line of business* in the generator (for example Medicare Advantage mostly on COSMOS). Confirm against the real platform mix.

**Codes.** Pend codes (`PND-…`) are invented for the demo. Denial codes are standard Claim Adjustment Reason Codes.

**Accuracy.** The classifier scores about 96% here. Real adjuster notes are messier, so expect a lower figure until it is retrained and re-measured on labelled real claims.

**Typefaces.** IBM Plex Sans and Source Serif 4, both under the SIL Open Font License. Licence text is in `web/fonts/LICENSES.txt`.

## From demo to production

1. Replace the generator with a feed from the claims platforms: claim header, status history, pend and denial codes, notes.
2. Have operations label about 1,000 to 2,000 real pended claims against the theme list, then retrain and re-measure.
3. De-identify notes before any text leaves the secure environment.
4. Move the store from in-memory to the enterprise data platform and schedule the pipeline daily.
5. Protect the rebuild endpoint, or remove it, once real data is in use.
6. Validate the playbook assumptions with the owning teams and track realised days removed after each intervention.
