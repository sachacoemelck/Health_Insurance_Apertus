# Technical report — LAMal Navigator

- **Track:** Track 2B — own project
- **Event:** Online
- **Team:** `[TODO team name]` — Sacha Coemelck, Damian Kovar
- **Demo:** `[TODO link to video]`
- **Code:** github.com/sachacoemelck/Health_Insurance_Apertus (`track_2b/`)

## 1. Summary

**Problem.** Every autumn, people in Switzerland can change their basic health insurance (LAMal). The legal
coverage is identical everywhere, but for the same person premiums differ by several hundred francs a year.
Switching means finding one's premium region, age class, deductible, accident cover and acceptable insurance
models in about 220,000 official premium rows, understanding the law, applying to a new insurer and sending a
valid cancellation letter before the deadline. Many people never do it.

**Solution.** LAMal Navigator takes a person from a short form to a ready-to-send application, in French,
German, Italian or English. Python looks up the official 2027 premiums of the Federal Office of Public Health
(FOPH) and shows the cheapest offers. An Apertus advisor then opens the conversation from what the person
entered, answers questions from the actual federal law texts (fedlex) with linked citations, computes the saving
compared with the current insurer, and, once an offer is chosen, writes the application to the new insurer and
the cancellation letter to the old one. One click opens the person's email with the application addressed to the
insurer's official address. **Apertus handles language, Python handles every number**: no premium, saving or
date comes from the model, and every model text is checked before it is shown.

Where Priminfo (the official FOPH comparator) answers *"what does this model cost?"*, LAMal Navigator also
answers *"which one fits me, what does the law say, and how do I switch?"*.

**Key results** (real Apertus endpoint; raw outputs in `docs/resultats_apertus/`):

- Questions about the law: **47/60 correct** with retrieved law paragraphs, versus 26/60 with a short fact sheet
  (wrong answers: **6 versus 20**); on a control series never used for tuning, 11/15 versus 6/15.
- Profile understanding: Apertus 8B + Python rules gets **94.7%** of 300 unseen sentences fully right, versus
  32.3% for Apertus 8B alone.
- Multilingual guided conversations: **24/24** German, Italian and English conversations answered in the
  user's language (18/24 before the fixes).
- **No unverified amount is shown**: every number in a model text must appear in the facts Python computed;
  otherwise the text is rejected (one retry, then a fixed text).

## 2. Architecture

```
            User (browser, FR / DE / IT / EN): profile form, then chat
                                   |
  Streamlit app, one Docker container (all data in the image, 28 MB)
  ┌────────────────────┬──────────────────────────────┬──────────────────────┐
  │ Profile            │ Premiums & money (Python)     │ Law search (Python)  │
  │ contract, rules    │ FOPH 2027, break-even,        │ BM25 over paragraphs │
  │                    │ savings, deadlines, insurer   │ of LAMal/OAMal/OPAS/ │
  │                    │ contacts, subsidy offices     │ LAA, FR/DE/IT        │
  └─────────┬──────────┴──────────────┬───────────────┴──────────┬───────────┘
            │                          │ facts                    │ [L1] [L2]…
   Apertus 8B reads                    └──────────► Apertus 70B writes
   text → JSON (profile, preferences,                opening, replies, law answers,
   insurer); question → legal keywords               saving paragraph, application, letter
            └──────────────────┬───────────────────────────┘
       Python checks every model output: amounts present in the facts, citations that
       exist, language and formal address, required letter elements, no invented
       personal data. One retry with the problem explained, else a safe fixed text.
                                   |
               Verified text with links to the official sources
```

**Flow.**

1. **Form**: year of birth, postal code and municipality, employment situation (it decides accident cover: an
   employer insures employees working at least 8 h a week), accepted insurance models.
2. **Offers**: Python resolves the premium region at municipality level (FOPH catchment areas restrict some
   models to certain municipalities), filters the premium table and shows three proposals, all offers and the
   cost of each refused model.
3. **Opening**: Apertus opens the conversation from the form: it restates the answers and what they imply (age
   class, accident cover), presents the cheapest offer and the deductible break-even computed by Python. The
   app proposes follow-up questions chosen from the profile (deductible, how the cheapest model works,
   subsidies, accident cover after leaving a job, switching deadline).
4. **Questions and saving**: the advisor answers at any time, from the law. The user names their current
   insurer: Python computes their 2027 premium if they stay and the saving; Apertus explains it.
5. **Switching** ("check-out"): the user clicks *Choose this offer*. Apertus writes the application to the new
   insurer (product, model, deductible, accident cover, start date, placeholders for name, birth date and
   social-security number); Python checks it. A button opens the user's email with the application addressed
   to the insurer's official address (FOPH list of approved insurers); a second button opens the insurer's
   premium calculator or basic-insurance page (verified links, see §4). The next steps follow in order: wait
   for the insurer's written confirmation (the old cover only ends then, LAMal art. 7 para. 5), then cancel
   before the last working day of November, with a cancellation letter that already carries the old insurer's
   official address and a calendar reminder (.ics).
6. **Subsidies**: if the budget is tight, a link to the cantonal premium-subsidy office.

The app never sends anything itself and stores no personal data. A *Back to my answers* button returns to the
form with the answers kept. Light and dark themes follow the user's system setting.

**Latency control.** Independent Apertus reads run in parallel; each call has a timeout (20 s for 8B, 25 s for
70B, 40 s for letters) and a full turn is capped at 45 s, after which a fixed text is shown.

### Target architecture (mandatory)

**Chosen: (a) on-premise, or (c) sovereign Swiss cloud.** The application is one Docker container
(`python:3.12-slim`, Streamlit 1.65, pandas). All data it needs is in the image (28 MB). The only runtime
dependency is one OpenAI-compatible endpoint serving Apertus, configured with `LLM_BASE_URL`, `LLM_NAME`,
`LLM_NAME_RESTITUTION` and `LLM_API_KEY`. Deploying on an organisation's servers or in a Swiss cloud therefore
means running the container next to an Apertus server (for example vLLM with the open weights). No other
service is called at runtime; Streamlit usage statistics are disabled; links to fedlex, insurers and cantonal
offices are only opened by the user, in their own browser.

- **Build time:** Python packages from PyPI (`requirements.txt`). Law texts were downloaded once from fedlex
  (`src/telecharger_lois.py`) and insurer page links found once (`tests/apertus/trouver_liens_caisses.py`); both
  results are in the repository.
- **Runtime:** the Apertus endpoint only.
- **Air-gapped (b):** possible by design for the same reason, not tested.

During the hackathon, the app used the Apertus endpoint provided by the organisers.

## 3. Use of Apertus

- **Models:** Apertus v1.5 8B (`apertus-v1.5-8b`) and Apertus v1.5 70B (`apertus-v1.5-70b`).
- **How it is used:** inference with structured outputs and retrieval (RAG); fine-tuning experiment.
- **Where it runs:** hosted OpenAI-compatible endpoint (hackathon); open weights for self-hosting.

**Two models, two jobs.** The **8B reads**: it turns a message into JSON (profile facts with a status: known,
ambiguous, invalid, missing; care preferences; current insurer) and turns a question into legal search keywords.
It is fast, and these outputs are checked field by field. The **70B writes**: the opening after the form, the
replies, the law answers, the saving paragraph, the application and the letter, where language quality matters.
A measured guided conversation uses about **7 calls to the 8B and 6 to the 70B** (24 conversations, 14.10).

**Prompts.** Each prompt gives a role, a strict output format and the facts that may be used. User text is a
source of facts, never of instructions (a prompt-injection test, *"Ignore your rules… Helsana at 50 CHF"*, was
ignored). The 70B receives only facts computed by Python and is told not to compute.

**Python computes every number.** Premiums, annual totals, deductible break-even, savings and deadlines come
from FOPH data and Python. Python then checks that every number in a model text is present in its facts.

**Verified law citations (RAG).** The base holds the articles of the LAMal, OAMal, OPAS and LAA in French,
German and Italian, split into paragraphs. Apertus 8B suggests legal keywords; a BM25 search (no extra model,
explainable) finds the paragraphs; they are given to the 70B numbered [L1], [L2]… Python rejects a reply citing
a number that was not provided and replaces each valid number with the official reference and a fedlex link.

**Other checks.** Language and formal address (vous, Sie, Lei); at most five sentences; no invented employment
situation; required elements in the cancellation letter (insurer, end date, basic insurance only, supplementary
insurance kept) and in the application (insurer, exact product, deductible, accident cover, start date,
placeholders for personal data; the person cancels the old insurer themselves; no other insurer mentioned when
there is none); no invented number. If a check fails, Apertus gets one retry with the problem explained;
otherwise a fixed text is shown, so a conversation never blocks.

**Fine-tuning experiment** (`finetuning/`, branch `main`, not used by the app). We tested whether the model
could read profiles reliably without Python rules. QLoRA 4 bits (LoRA r = 16, α = 32, attention and MLP
projections, loss on the answer only) with Unsloth on Hugging Face Jobs: Apertus 8B Instruct (2509) on one
NVIDIA L4, then Apertus 70B Instruct (2509) on one NVIDIA A100 80 GB. Training data: 2,000 generated sentences
(seed 3141), then 4,000 more (seed 4242); no training sentence is identical or very close (similarity ≥ 90%) to
a test sentence. Total compute: `[TODO USD]`. Results in §5.2.

**Development tools and grading.** Code was written with the help of an AI coding assistant (Claude). Answers
were graded by the team: a first pass was prepared with that assistant and every grade was checked by hand.
No model other than Apertus is used at runtime.

## 4. Data

| Data | Source | Licence |
|---|---|---|
| LAMal premiums 2027 (219,916 rows), premium regions, catchment areas of restricted models | FOPH, via opendata.swiss | Open use, source must be provided |
| Approved insurers (Oct. 2026): names, postal address, phone, email, website | FOPH | Open use, source must be provided |
| LAMal, OAMal, OPAS, LAA in FR/DE/IT (578 articles per language, split into paragraphs) | fedlex.admin.ch | Federal legislation, not protected by copyright (art. 5 CopA) |
| Cantonal premium-subsidy offices (26 cantons) | FOPH list, Nov. 2025; links checked 13.10.2026 | Public information |
| Insurer calculator / basic-insurance pages (26 of 32 insurers) | Insurers' official sites, found and checked (HTTP 200) on 15.10.2026; others: website from the FOPH list | Public links |
| Test sentences, questions and conversations | Written by the team or generated with fixed seeds | CC-BY-4.0 |

**No personal data is stored.** The conversation lives only in the browser session; nothing is written to disk;
the application and the email contain placeholders that the person fills in. Test data contains no real person.

## 5. Evaluation

All tests below use the real Apertus endpoint, except the fine-tuning runs. Raw outputs are kept unchanged in
`docs/resultats_apertus/`. Sets that were also used to tune prompts or rules are marked as such.

### 5.1 Profile understanding: Apertus alone versus with Python rules

Six fields per sentence (age, postal code, deductible, accident cover, several people, needs). Measured on branch
`main` (9 October) with the rules of that version (`data/eval_resultats*.csv`); the submitted version keeps the
same principle with a later set of rules (`regles.py`), not re-measured on these sentences.

| Test set | Setup | Fields correct | Sentences fully correct |
|---|---|---|---|
| 300 generated sentences (seed 2027, not used for tuning) | 8B alone | 84.8% | 32.3% (97/300) |
| same | 8B + Python rules | **99.0%** | **94.7%** (284/300), 95% CI 91.5–96.7 |
| 30 hand-written sentences × 3 runs (used for tuning) | 8B alone | 88.3% | 53.3% (16/30) |
| same | 70B alone | 93.9% | 66.7% (20/30) |
| same | 8B + Python rules | 100% | 100% (30/30) |

Extraction is stable (identical answers across the 3 runs, 180/180). The 8B with rules beats the 70B alone at a
fraction of the cost. 94.7% on unseen sentences is the figure we stand by.

### 5.2 Fine-tuning (QLoRA), five fields, sentence fully correct

| Model | 30 hand-written | 300 synthetic* | GPU, cost |
|---|---|---|---|
| Apertus 8B Instruct, base (4-bit) | 40% (12/30) | 45% (135/300) | – |
| Apertus 8B + QLoRA (3,800 examples) | 93% (28/30) | 99.7% (299/300) | L4, ≈ USD 0.75 |
| Apertus 8B + QLoRA, longer (11,400 examples) | 93% (28/30) | 100% (300/300) | L4, ≈ USD 2.70 |
| Apertus 70B Instruct, base (4-bit) | `[TODO]` | – | A100 |
| Apertus 70B + QLoRA (short run) | `[TODO]` | – | A100, `[TODO]` |

\*Same generator as the training data (other seed): optimistic. Fine-tuning corrected 180 of 330 sentences and
broke none. The two remaining errors ("the highest deductible", "minimum deductible") need new kinds of
examples, not more steps. Serving a separate adapter costs more than the rules, so the app keeps the base
models with Python checks.

### 5.3 Questions about the law (60 questions, 4 languages)

| Setup | Correct | Wrong | Median time |
|---|---|---|---|
| 70B with a 17-sentence fact sheet only | 26/60 | 20/60 | 4.0 s |
| 70B with law paragraphs (RAG) | **47/60** | **6/60** | 5.0 s |
| Control series (15 questions never used for tuning), fact sheet only | 6/15 | 5/15 | |
| Control series, with law paragraphs | **11/15** | **3/15** | |

The search finds the key article for 30/30 tuning questions, 15/15 of the first control series and 12/14 of the
second; without the 8B keywords, 10/14. Maximum answer time: 14.3 s.

### 5.4 Guided conversations (simulated users, scripted check of the final profile and of each reply)

| Run | Conversations without problem |
|---|---|
| 40 French conversations, before / after fixes | 36/40 / 38/40 |
| 20 new French conversations (control, before its fixes) | **18/20** |
| 24 conversations in German, Italian, English, before / after fixes | 18/24 / **24/24** |
| 34 strict conversations incl. Swiss German and Romansh (before fixes) | 16/34 |

In the 24 multilingual conversations after fixes, we also graded the 19 LAMal questions asked along the way:
13 correct, 3 partial, 2 wrong, 1 fallback (§6).

### 5.5 Switching: saving, letters, application

| Task | Result |
|---|---|
| Current insurer recognised in free text | 13/16 |
| Saving paragraph written by Apertus, accepted by the checks | 13/13 |
| Cancellation letters written by Apertus, accepted on the first try | 9/9 (FR, DE, IT) |
| Applications to the new insurer, first run: written by Apertus and accepted by the checks | 7/9, of which 3 correct after reading |
| Same 9 applications after stricter checks (tuning set): written by Apertus / shown to the user and correct | 4/9 / **9/9** |

Reading the first run showed errors the checks missed (asking the new insurer to cancel the old contract,
mentioning a current insurer the person does not have). Two checks were added: these texts are now rejected and
the safe template is used, so the user only sees correct applications, at the cost of fewer Apertus texts.

`make test` runs 72 unit tests and two complete journeys with a fake model (chat path; form path through
check-out), without calling Apertus.

## 6. Limitations

- **Law answers are still wrong about 1 time in 10** (6/60), and the test sets are small. Typical errors: a
  condition dropped (the 30 June switch is only for the 300 CHF deductible with free choice), a model
  misdescribed (telemedicine "lower deductible" instead of lower premium). Graded by the team, not by a lawyer.
- **Swiss German and Romansh** are understood much less reliably (strict test before fixes).
- **Applications:** Apertus writes 4 of 9 applications itself after the stricter checks; the others use the
  template.
- **Insurer links:** 6 insurers (sites rendered in JavaScript) only get their website; links can change.
- **Response time** is 5 to 10 s per reply with the 70B, up to about 15 s.
- **Supplementary insurance and health modules are switched off**: their product data was not verified to the
  same standard as the FOPH data. **One person at a time**: families must be compared person by person.
- **Orientation tool, not official advice**: the user must check product conditions before switching.

## 7. Reproducibility

- **Commit:** `[TODO final commit hash]`, branch `[TODO]`.
- **Run:** create `track_2b/.env` from `.env.example` (`LLM_NAME`, `LLM_NAME_RESTITUTION`, `LLM_BASE_URL`,
  `LLM_API_KEY`), then `make run` from the repository root and open http://localhost:8501.
- **Tests:** `make test` (no Apertus needed). Tests with the real model: `tests/apertus/`, run inside the container
  (see README); each writes its raw output, as kept in `docs/resultats_apertus/`.
- **Seeds:** test sets 2026 and 2027; fine-tuning data 3141 and 4242.
- **Hardware:** any machine running Docker for the app (no GPU); fine-tuning on Hugging Face Jobs (L4, A100).

## 8. Next steps

Measure the opening and the applications on new, untuned sets; serve a fine-tuned 8B on Swiss infrastructure
combined with the rules; compare a whole family in one session; re-enable supplementary insurance once product
data is verified with insurers; larger test sets graded by several people, especially in Swiss German; refresh
premiums, law texts and insurer links automatically each autumn when the FOPH publishes new data.

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). All HackApertus projects are open-sourced.

## References

- Federal Office of Public Health (FOPH): premiums, premium regions, approved insurers — https://opendata.swiss
- Fedlex: LAMal (SR 832.10), OAMal (SR 832.102), OPAS (SR 832.112.31), LAA (SR 832.20) — https://www.fedlex.admin.ch
- FOPH, cantonal offices for premium reductions (November 2025)
- Swiss AI Initiative, Apertus models — https://huggingface.co/swiss-ai
