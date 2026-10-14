# LAMal Navigator — Swiss basic health insurance assistant built with Apertus

A chatbot that talks with you in French, German, Italian or English, finds the cheapest
Swiss basic health insurance (LAMal) offers for **your** situation from the official 2027
FOPH premiums, answers your questions from the **actual law texts**, tells you how much you
would save compared with your current insurer, and writes your cancellation letter.

Hack Apertus 2026 — Track 2B.

## The problem

Every autumn, people in Switzerland can switch their basic health insurance. The legal coverage
is identical everywhere, but premiums for the same person differ by several hundred francs a year.
Comparing them means knowing your canton, premium region, age class, deductible, accident cover and
which insurance models you accept, reading tables of 220,000 rows, understanding the law, and
sending a correct cancellation letter before the deadline. Many people never do it, and overpay.

## What it does

1. **Guided conversation.** Describe your situation in your own words ("I'm 35, I live in
   Lausanne, any model is fine"). Apertus reads it; Python checks every field and asks only for
   what is missing (location, age, accident cover, accepted models, budget, deductible).
   You can ask questions at any time; Apertus answers them before the next question.
2. **Official premiums.** Python filters the FOPH 2027 premium table (commune-level availability
   included) and shows three proposals, all offers, and what your model preferences cost.
3. **Answers from the law.** Questions about LAMal ("is an abortion covered?", "Werden bei einer
   Geburt Franchise und Selbstbehalt verrechnet?") are answered by Apertus 70B from the
   paragraphs of the federal law texts (LAMal, OAMal, OPAS, LAA from fedlex.admin.ch) that a search
   engine finds for the question. Every answer cites its article with a link, and Python rejects
   any citation that was not provided.
4. **Your savings.** Tell it your current insurer: Python computes your 2027 premium if you stay
   and the savings (same model, and cheapest overall); Apertus explains them in a few sentences.
5. **Cancellation letter.** Apertus writes the letter in French, German or Italian; Python checks
   every required element (insurer, end date 31.12.2026, basic insurance only, supplementary
   insurance kept, placeholders for personal data, no invented number) and shows the deadline.
6. **Subsidies.** If budget is tight, it links to the premium-subsidy office of your canton
   (official FOPH list).

## How the work is split

| Task | Done by | Checked by Python |
|---|---|---|
| Understand free text (profile, preferences, insurer) | Apertus 8B | every value against rules and official lists |
| Translate a question into legal search terms | Apertus 8B | — (search works without it) |
| Find the relevant law paragraphs | Python (BM25 search per paragraph, FR/DE/IT) | — |
| Premiums, savings, deductible break-even, dates | Python only | — |
| Reactions, answers, savings paragraph, letter | Apertus 70B | numbers, citations, language, formal "vous/Sie/Lei", required letter elements |

Apertus never computes a premium: a language model can misread a table, and for a financial
decision one wrong figure is unacceptable. When a check fails, Apertus gets one retry with the
problem explained; otherwise a safe fallback text is shown.

## Measured with the real Apertus

All tests were run against the hackathon Apertus endpoint; raw outputs are in
[`track_2b/docs/resultats_apertus/`](track_2b/docs/resultats_apertus/).

- **LAMal questions (60, 4 languages):** with the law texts, 47 correct / 6 wrong, versus
  26 correct / 20 wrong with the short fact sheet alone. On the clean control series (15 questions
  never used for tuning): 11 correct / 3 wrong versus 6 / 5. Median answer time 5 s.
- **Cancellation letters:** 9/9 accepted by the checks on the first try (FR, DE, IT).
- **Savings paragraphs:** 13/13 accepted.
- **Guided conversations:** 38/40 French conversations without problem; known weaknesses in
  Swiss German and Romansh.

Details, corrections and limits: [technical report](track_2b/technical_report.md).

## How to run

1. Create `track_2b/.env` from the template and add your API key (never commit it):
   ```bash
   cd track_2b && cp .env.example .env
   ```
   It defines `LLM_NAME` (Apertus 8B), `LLM_NAME_RESTITUTION` (Apertus 70B), `LLM_BASE_URL`
   and `LLM_API_KEY` (OpenAI-compatible endpoint).
2. From the root of the repository:
   ```bash
   make run      # then open http://localhost:8501
   make test     # tests without Apertus (rules, law search, letter checks, full journey with a fake model)
   ```
3. Tests with the real Apertus (they write their results to `tests/apertus/resultats/`, or to
   `/dl` if you mount a folder there):
   ```bash
   cd track_2b && docker build -t lamal-navigator .
   docker run --rm --env-file .env lamal-navigator python tests/apertus/test_questions_lamal.py
   ```

## Data and licences

- LAMal premiums 2027, premium regions, catchment areas and list of approved insurers: Federal Office
  of Public Health (FOPH), via opendata.swiss — open use, source must be provided.
- Law texts (LAMal, OAMal, OPAS, LAA): fedlex.admin.ch, downloaded by
  `track_2b/src/telecharger_lois.py` into `track_2b/data/lois.json`. Swiss federal legislation is
  not protected by copyright (art. 5 Copyright Act).
- Cantonal premium-subsidy offices: FOPH list (November 2025).

No personal data is stored: the conversation lives only in the browser session.

## Repository layout

- `track_2b/src/app.py` — Streamlit interface and conversation flow
- `track_2b/src/chatbot.py`, `regles.py`, `soins.py`, `langues.py` — reading and checking the profile, 4 languages
- `track_2b/src/comparateur.py` — premium engine (FOPH data)
- `track_2b/src/conversation.py` — Apertus answers and their checks
- `track_2b/src/lois.py`, `telecharger_lois.py` — law-text search (RAG) and its data
- `track_2b/src/changement.py`, `subsides.py` — current insurer, savings, cancellation letter, subsidies
- `track_2b/tests/` — tests without Apertus (`make test`); `tests/apertus/` — tests with the real model
- `track_2b/technical_report.md` — technical report

`complementaires.py` and `sante.py` are modules from a first version (supplementary insurance and
health information); their data was not verified to the same standard, so they are switched off
in the app (`MODULES_COMPLEMENTAIRES = False` in `app.py`).

## License

All Hack Apertus projects are open source — see [LICENSE](LICENSE) and the
[Hack Apertus Terms & Conditions](https://hackapertus.ch/terms-and-conditions).
