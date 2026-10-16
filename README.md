# LAMal Navigator — compare, understand and switch Swiss basic health insurance with Apertus

Fill in a short form, and LAMal Navigator shows the cheapest Swiss basic health insurance (LAMal)
offers for **your** situation from the official 2027 FOPH premiums. An Apertus advisor then explains
them, shows how much you would save compared with your current insurer, answers your questions from
the **actual law texts**, prepares your application to the new insurer and your cancellation letter,
and tells you clearly what basic insurance does not pay. In French, German, Italian or English.

**Hack Apertus 2026 — Track 2B — team V-Boys** (Sacha Coemelck, Damian Kovar)
· Demo video: <https://youtu.be/bMkfqNypMic>
· Technical report: [`track_2b/V-Boys_Report.pdf`](track_2b/V-Boys_Report.pdf)
([Markdown version](track_2b/technical_report.md))

## The problem

Every autumn, people in Switzerland can switch their basic health insurance. The legal coverage
is identical everywhere, but premiums for the same person differ by several hundred francs a year.
Comparing them means knowing your premium region, age class, deductible, accident cover and
which insurance models you accept, reading tables of 220,000 rows, understanding the law, applying
to a new insurer and sending a correct cancellation letter before the end of November. Many people
never do it, and overpay.

## What it does

1. **Short form.** Year of birth, postcode, work situation (it decides accident cover), accepted
   insurance models; optionally your current insurer in your own words, and needs outside basic
   insurance (glasses, dentist, complementary medicine, private ward, treatment abroad).
2. **Official premiums.** Python filters the FOPH 2027 premium table (municipality-level availability
   included) and shows three neutral proposals, all offers, and what your model preferences cost.
   No offer is highlighted as “best”.
3. **An advisor that starts from your answers.** Apertus opens the conversation from the form (age
   class, accident cover, cheapest offer, deductible break-even computed by Python), then shows how
   much you would save by leaving your current insurer.
4. **Answers from the law.** Ask anything at any time ("Are my glasses covered?", "Kann mich eine
   Krankenkasse ablehnen?"). Apertus 70B answers from the paragraphs of the federal law texts
   (LAMal, OAMal, OPAS, LAA from fedlex.admin.ch) that a search finds for the question. Every answer
   cites its article with a link, and Python rejects any citation that was not provided.
5. **From choice to application, in real-life order.** *Choose this offer* opens the steps:
   (1) the application, written by Apertus and checked by Python, opens in your email, addressed to
   the insurer's official address (FOPH list), with a link to the insurer's own premium calculator;
   (2) wait for the insurer's written confirmation; (3) on request, the cancellation letter for your
   old insurer, with its official address, the deadline computed from today's date and a calendar
   reminder; (4) what basic insurance does not pay. Letters are written in an official language of
   your canton; every step says it concerns **basic insurance only**.
6. **What basic insurance does not pay.** A table for the needs you ticked, with the article, then a
   clear message: this needs supplementary insurance (private, health questions, no published
   premiums), and how to keep or change it safely.
7. **Subsidies.** If budget is tight, a link to the premium-subsidy office of your canton.

The app never sends anything itself and stores no personal data.

## How the work is split

| Task | Done by | Checked by Python |
|---|---|---|
| Understand free text (profile, current insurer and model) | Apertus 8B | every value against rules and official lists |
| Turn a question into legal search terms | Apertus 8B | — (search works without it) |
| Find the relevant law paragraphs | Python (BM25 search per paragraph, FR/DE/IT) | — |
| Premiums, savings, deductible break-even, deadlines, addresses | Python only | — |
| Opening, answers, savings paragraph, application, letter | Apertus 70B | numbers, citations, language, formal "vous/Sie/Lei", required elements |

Apertus never computes a premium: a language model can misread a table, and for a financial
decision one wrong figure is unacceptable. When a check fails, Apertus gets one retry with the
problem explained; otherwise a safe fixed text is shown. If Apertus cannot be reached, offers and
the application steps still work.

## Measured with the real Apertus

All tests were run against the hackathon Apertus endpoint and graded by the team, by hand; raw
outputs are in [`track_2b/docs/resultats_apertus/`](track_2b/docs/resultats_apertus/).

- **LAMal questions (60, 4 languages):** with the law texts, 47 correct / 6 wrong, versus
  26 correct / 20 wrong with a short fact sheet alone. On the control series (15 questions never
  used for tuning): 11 correct / 3 wrong versus 6 / 5. Median answer time 5 s.
- **Profile understanding:** 94.7% of 300 unseen sentences fully correct with Apertus 8B + Python
  rules, versus 32.3% for Apertus 8B alone.
- **Languages:** 24/24 German, Italian and English conversations answered in the user's language.
- **Cancellation letters:** 9/9 accepted by the checks on the first try (FR, DE, IT).

Details, corrections and limits: [technical report](track_2b/V-Boys_Report.pdf).

## How to run

1. Provide the Apertus endpoint, either as environment variables in your terminal:
   ```bash
   export LLM_NAME=apertus-v1.5-8b LLM_BASE_URL=<endpoint>/v1 LLM_API_KEY=<your key>
   export LLM_NAME_RESTITUTION=apertus-v1.5-70b   # optional: model that writes (otherwise LLM_NAME)
   ```
   or in a `track_2b/.env` file (`cp track_2b/.env.example track_2b/.env`, then add your key;
   never commit it).
2. From the root of the repository:
   ```bash
   make run      # builds and starts the Docker container, then open http://localhost:8501
   make test     # tests without Apertus (rules, law search, letters, two full journeys with a fake model)
   ```
3. Tests with the real Apertus are in `track_2b/tests/apertus/` (they write their results to
   `tests/apertus/resultats/`, or to `/dl` if you mount a folder there):
   ```bash
   cd track_2b && docker build -t lamal-navigator .
   docker run --rm --env-file .env lamal-navigator python tests/apertus/test_questions_lamal.py
   ```

## Data and licences

- LAMal premiums 2027, premium regions, catchment areas and list of approved insurers (with their
  official addresses): Federal Office of Public Health (FOPH), via opendata.swiss — open use, source
  must be provided.
- Law texts (LAMal, OAMal, OPAS, LAA): fedlex.admin.ch, downloaded by
  `track_2b/src/telecharger_lois.py` into `track_2b/data/lois.json`. Swiss federal legislation is
  not protected by copyright (art. 5 Copyright Act).
- Cantonal premium-subsidy offices: FOPH list (November 2025). Insurer calculator pages: official
  sites, checked on 15.10.2026.

No personal data is stored: the session lives only in the browser.

## Repository layout

- `track_2b/src/app.py`, `style.py` — Streamlit interface and flow
- `track_2b/src/chatbot.py`, `regles.py`, `soins.py`, `langues.py` — reading and checking the profile, 4 languages
- `track_2b/src/comparateur.py` — premium engine (FOPH data)
- `track_2b/src/conversation.py` — Apertus answers and their checks
- `track_2b/src/lois.py`, `telecharger_lois.py` — law-text search (RAG) and its data
- `track_2b/src/changement.py`, `subsides.py` — current insurer, savings, cancellation letter, subsidies
- `track_2b/src/affiliation.py`, `caisses.py` — application to the new insurer, official insurer contacts
- `track_2b/src/hors_lamal.py` — what basic insurance does not pay, with the articles
- `track_2b/tests/` — tests without Apertus (`make test`); `tests/apertus/` — tests with the real model
- `track_2b/V-Boys_Report.pdf`, `technical_report.md`, `docs/report/` — technical report and its LaTeX source

`complementaires.py` and `sante.py` are modules from a first version; their data was not verified to
the same standard, so they are switched off (`MODULES_COMPLEMENTAIRES = False` in `app.py`).
`finetuning/` holds an unfinished experiment that the app does not use.

## License

Code and test data: Apache 2.0 (see [LICENSE](LICENSE)); technical report: CC-BY-4.0. All Hack Apertus
projects are open source — see the [Hack Apertus Terms & Conditions](https://hackapertus.ch/terms-and-conditions).
