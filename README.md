# Health Insurance Apertus — LAMal premium assistant

A chatbot that understands your situation in plain language and finds the cheapest
Swiss basic health insurance (LAMal) premiums from official FOPH data, explained by Apertus.

**Status: work-in-progress prototype** (Hack Apertus, Track 2B).

## The problem

Every autumn, people in Switzerland can switch their basic health insurance. Premiums for
the exact same legal coverage vary a lot between insurers, but comparing them means knowing
your canton, premium region, age class, deductible and accident coverage — and reading
tables with hundreds of thousands of rows. Many people never compare, and overpay.

## How it works

1. **Describe** — the user describes their situation in free text (age, place, work, deductible).
2. **Extract** — Apertus turns that text into a structured JSON profile
   (`canton`, `region`, `age`, `franchise`, `travaille_8h`). Python validates every field
   against the dataset and asks again for anything missing or invalid.
3. **Compute** — `comparateur.py` filters the official FOPH premium table with pandas and
   returns the cheapest offers. Accident coverage is excluded when the person works at
   least 8 hours/week for the same employer (covered by their employer's insurance).
4. **Explain** — Apertus explains the results in French, using only the numbers it was given.

## Why the LLM does not compute premiums

Premiums are looked up, not generated. A language model can misread a table, round
numbers or invent an insurer, and for a financial decision a single wrong figure is
unacceptable. So the work is split: Apertus handles language (understanding the user,
explaining the result), and deterministic code handles numbers. Every premium shown
comes straight from the FOPH dataset and can be traced back to a row in the CSV.

## How to run

1. Create your `.env` from the template and add your API key:
   ```bash
   cd track_2b
   cp .env.example .env
   ```
   It defines `LLM_NAME`, `LLM_BASE_URL` and `LLM_API_KEY` (OpenAI-compatible endpoint).
   Never commit `.env`.
2. From the root of the repository:
   ```bash
   make run
   ```
   > The Docker setup behind `make run` is still in progress. Meanwhile, run locally:
   > `pip install -r track_2b/requirements.txt && python track_2b/src/chatbot.py`

## Data

LAMal premiums 2027 published by the Federal Office of Public Health (FOPH / OFSP),
via [opendata.swiss](https://opendata.swiss).
Licence: **Open use, must provide the source.** — Source: Federal Office of Public Health FOPH.
The file is `track_2b/data/primes_CH.csv`.

## Repository layout

- `track_2b/src/` — `comparateur.py` (premium engine), `chatbot.py` (Apertus dialogue)
- `track_2b/data/` — FOPH premium data
- `track_2b/technical_report.md` — **[full technical report](track_2b/technical_report.md)**

## License

All Hack Apertus projects are open source — see [LICENSE](LICENSE) and the
[Hack Apertus Terms & Conditions](https://hackapertus.ch/terms-and-conditions).
