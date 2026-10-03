# LAMal Navigator
## Hack Apertus — Track 2B: Own Project

## 1. Project in one sentence

**LAMal Navigator is a sovereign conversational decision-support tool that turns a resident's everyday description of their situation into a verified comparison of Swiss compulsory health-insurance offers using Apertus, deterministic code, and official FOPH data.**

The core principle is:

> **Apertus understands the person. Code applies the rules and calculations. Official Swiss data provides the facts.**

---

## 2. The problem we are solving

Switzerland already provides official LAMal premium data and the federal Priminfo calculator.

The problem is therefore **not a lack of data**.

The real problem is that using this data correctly requires the user to understand several insurance concepts before they can compare offers:

- municipality and premium region;
- age category;
- accident coverage;
- deductible;
- standard vs restricted-choice models;
- the practical difference between PRAXIS, TEL_DIG, PHARM, FLEX and BASE;
- which cheaper offers are actually compatible with how the user wants to access healthcare.

Real users do not naturally think in those fields. They say things such as:

> “I live in Lausanne, work full-time, rarely go to the doctor, want a high deductible and I’m fine calling first if it saves money.”

LAMal Navigator bridges the gap between **human language** and **official structured insurance data**.

It does not replace Priminfo. It makes the same type of authoritative data easier to use correctly.

---

## 3. Product objective

The user should be able to explain their situation naturally in **French, German, Italian or English**.

The system should then:

1. understand the relevant facts and preferences with Apertus;
2. show the user what it understood;
3. detect missing, ambiguous or contradictory information;
4. ask only the clarification questions that are actually necessary;
5. convert the validated facts into official LAMal comparison parameters;
6. retrieve compatible offers from the official 2027 premium dataset;
7. perform every financial calculation deterministically in Python;
8. rank the lowest-cost offers compatible with the user's preferences;
9. explain the result in plain language with Apertus;
10. make every result traceable to official data and explicit rules.

The product must never claim:

> “This is the best insurer for you.”

The correct claim is:

> **“These are the lowest-cost official LAMal offers compatible with the parameters and preferences you provided.”**

---

## 4. Why Apertus is genuinely necessary

Apertus should not be added as decoration around a normal premium calculator.

Its essential job is to solve the part that traditional forms handle poorly: **understanding people**.

Apertus should be responsible for:

- extracting facts from free-form language;
- interpreting indirect preferences;
- understanding colloquial or multilingual phrasing;
- recognising missing or ambiguous information;
- maintaining a short multi-turn dialogue;
- asking contextual follow-up questions;
- explaining verified results clearly.

Examples:

> “I want to keep seeing any doctor I choose.”  
→ preference for unrestricted access.

> “Calling or using an app first is fine.”  
→ TEL_DIG may be acceptable.

> “I always go through my family doctor.”  
→ PRAXIS may be acceptable.

> “I work a few hours a week.”  
→ insufficient information; clarification required for accident coverage.

Without Apertus, the user must understand insurance terminology and fill a structured form.

With Apertus, the user can start from their real-life situation.

---

## 5. What Apertus must never do

The LLM is **not** the source of truth.

Apertus must never:

- invent or estimate a premium;
- calculate annual premiums or savings;
- infer a premium region by itself;
- invent an insurer or tariff;
- override an official dataset value;
- decide that an invalid input is “probably fine”;
- claim that one basic insurer offers better medical coverage than another;
- predict the user's future healthcare expenditure;
- provide personalised medical advice.

If a number is displayed to the user, it must come from:

1. the official dataset; or
2. a deterministic Python calculation based on official values.

Target:

> **0% LLM-generated financial figures.**

---

## 6. Product flow

```text
USER
  ↓
Natural-language description
  ↓
APERTUS
Extract facts + preferences
  ↓
STRUCTURED USER PROFILE
  ↓
PYTHON VALIDATION / RULE ENGINE
  ↓
Missing or ambiguous?
  ├── YES → Apertus asks a targeted clarification → update profile
  └── NO
       ↓
OFFICIAL PARAMETER RESOLUTION
       ↓
FOPH DATA FILTERING
       ↓
DETERMINISTIC RANKING + CALCULATIONS
       ↓
VERIFIED RESULTS
       ↓
APERTUS
Plain-language explanation only
       ↓
USER
```

This separation between **semantic understanding** and **deterministic decision logic** is the central technical design of the project.

---

## 7. User profile

Apertus should extract **raw facts and preferences**, not final insurance codes.

Example:

```json
{
  "birth_year": 1997,
  "location": {
    "postal_code": "1260",
    "municipality": "Nyon"
  },
  "employment": {
    "employed": true,
    "hours_per_week": 40
  },
  "deductible_preference": "high",
  "care_access_preferences": {
    "free_choice_required": false,
    "gp_first_ok": true,
    "telemedicine_ok": true,
    "pharmacy_first_ok": false,
    "flexible_model_ok": true
  },
  "current_insurer": null,
  "current_monthly_premium": null
}
```

Python then derives the official parameters:

```json
{
  "canton": "VD",
  "premium_region": "PR_REG_1",
  "age_class": "AKA_03_ERW",
  "accident": "OHN_UNF",
  "deductible": "FRA_06_E_2500",
  "accepted_tariff_types": ["PRAXIS", "TEL_DIG", "FLEX"]
}
```

**Apertus extracts meaning. Python derives insurance parameters.**

---

## 8. Uncertainty and validation

Every required field should be treated as one of:

- `KNOWN`
- `MISSING`
- `AMBIGUOUS`
- `INVALID`

The system must **fail closed**.

Examples:

- a postal code maps to multiple municipalities → ask for the municipality;
- employment information is insufficient to determine accident coverage → ask;
- an invalid deductible is requested → reject and explain valid options;
- two user statements conflict → clarify;
- a required field is absent → do not silently guess.

The product should never use an arbitrary LLM “confidence score” as a substitute for validation.

---

## 9. Official data sources

The application should work from local copies of official Swiss data.

### 2027 FOPH premium dataset

Source of truth for:

- insurer identifier;
- canton;
- premium region;
- age class;
- accident inclusion;
- deductible;
- tariff type;
- exact tariff/product name;
- monthly premium.

### 2027 premium-region dataset

Used for:

**municipality → canton → premium region**

Postal code can help identify the location, but the **municipality** determines the premium region.

### Official list of authorised insurers

Used for:

**insurer identifier → official insurer name**

The final system must not rely on manually hardcoded insurer names.

---

## 10. Insurance models

The comparison should support the official 2027 tariff categories:

- `BASE` — standard / unrestricted model;
- `PRAXIS` — first contact through a designated practice, GP or medical centre;
- `TEL_DIG` — first contact by telephone or digital channel;
- `PHARM` — first contact through a participating pharmacy;
- `FLEX` — flexible/hybrid restricted-choice model.

The user should not need to know these labels.

Apertus interprets the user's real-world preference; Python maps that preference to compatible official categories.

The application must also preserve the **exact tariff name**, because one insurer may offer multiple products with different prices and access rules.

Therefore:

> **The unit of comparison is an offer/tariff, not simply an insurer.**

The system must not select the cheapest tariff from each insurer before checking whether that tariff matches the user's preferences.

---

## 11. Comparison logic

The ranking must remain transparent and auditable.

Default logic:

1. resolve the validated user profile;
2. filter official data by canton and premium region;
3. filter by age class;
4. filter by accident coverage;
5. filter by deductible;
6. filter by accepted insurance-model categories;
7. preserve distinct tariff/product offers;
8. sort compatible offers by official monthly premium;
9. return a small number of lowest-cost compatible offers.

No subjective insurer score is used.

LAMal Navigator does **not** rank customer service, brand reputation or claims handling unless a future version obtains authoritative comparable data for those dimensions.

---

## 12. High-value decision support

The product should do more than return a cheap-premium list.

### A. Cheapest compatible offers

The core result.

It answers:

> “Given what you told me, which official offers satisfy those constraints at the lowest premium?”

### B. “What if I accept a different model?”

This is a strong differentiator.

Example:

> “If you require unrestricted doctor choice, the lowest compatible premium is CHF X/month.  
> If you accept TEL_DIG, offers start at CHF Y/month.”

X and Y are calculated by Python.

Apertus explains the trade-off.

This lets the user understand **what they are paying for**, not only which row is cheapest.

### C. Deductible scenario explorer

Rather than telling the user which deductible is “best,” the application can compare deterministic scenarios.

Python may calculate:

- annual premium by deductible;
- premium differences;
- total-cost scenarios at different annual healthcare-spending levels;
- break-even points where mathematically meaningful.

The system does not predict future health expenditure.

This remains a neutral decision-support feature rather than medical advice.

### D. Current-plan comparison

If the user provides their current premium, Python may show:

- monthly difference;
- annual difference.

Apertus only explains those precomputed values.

---

## 13. Output

The final experience should be structured rather than a wall of chatbot text.

### 1. What I understood

```text
Residence        Nyon (VD)
Premium region   Region 1
Age category     Adult
Accident          Excluded
Deductible       CHF 2,500
Accepted models  TEL_DIG / PRAXIS / FLEX
Premium year     2027
```

The user can immediately detect a misunderstanding.

### 2. Compatible offers

For each result:

- insurer;
- exact product;
- model category;
- monthly premium;
- annual premium;
- deductible;
- accident status.

### 3. Why this result?

Show the exact parameters used by the engine and identify the official source dataset.

### 4. Apertus explanation

A short explanation of:

- why the offer matches;
- what the model means;
- the relevant trade-off;
- what should still be verified in the insurer's detailed conditions.

No new numerical claim is introduced here.

---

## 14. Privacy and sovereignty

The target design must be able to run entirely on controlled infrastructure.

```text
Browser
   ↓
Application
   ├── Apertus
   ├── deterministic Python engine
   └── local FOPH datasets
```

The LLM remains configurable through:

```text
LLM_NAME
LLM_BASE_URL
LLM_API_KEY
```

The hackathon deployment can use the provided Apertus endpoint.

A sovereign deployment can point the same application to a locally or Swiss-hosted Apertus instance.

The product should not require any proprietary external LLM to function.

No user conversation needs to be stored for the core use case.

No medical history is required.

Secrets remain outside Git and are loaded through environment variables.

---

## 15. Scope and limitations

### In scope

- Swiss compulsory/basic health insurance;
- official 2027 premiums;
- conversational profile extraction;
- multi-turn clarification;
- municipality/premium-region resolution;
- age-class logic;
- accident-cover logic;
- deductible handling;
- official insurance-model categories;
- compatible-offer comparison;
- deterministic cost calculations;
- multilingual interaction;
- traceability and explanation.

### Explicitly out of scope

- supplementary insurance;
- medical advice;
- prediction of future healthcare use;
- subjective insurer-quality ratings;
- automatic policy purchase or cancellation;
- health-risk profiling;
- claims analysis;
- unsupported doctor/network guarantees;
- personalised legal advice.

The application should clearly state that it is a prototype decision-support tool and not an official FOPH service.

---

## 16. Evaluation

Evaluation should be a visible strength of the project.

Create a labelled multilingual test set containing realistic and difficult user statements.

It should cover:

- complete profiles;
- missing information;
- ambiguous postal codes;
- employment ambiguity;
- age-category boundaries;
- invalid deductibles;
- indirect insurance-model preferences;
- contradictory statements;
- irrelevant information;
- colloquial language;
- French;
- German;
- Italian;
- English;
- attempts to make Apertus ignore application rules.

Measure at least:

- field-level extraction accuracy;
- exact-profile accuracy;
- missing-field detection;
- ambiguity detection;
- invalid-input rejection;
- correct follow-up-question rate;
- premium lookup correctness;
- arithmetic correctness;
- financial hallucination rate.

### Apertus 8B vs 70B

Run the same evaluation on both models.

Compare:

- extraction quality;
- dialogue quality;
- latency;
- deployment cost/resource requirements.

The chosen model should be justified by measured results, not assumption.

If Apertus 8B reaches sufficient quality, that becomes a particularly strong argument for scalability and sovereign deployment.

---

## 17. Differentiation from Priminfo

Priminfo should be treated as the authoritative reference, not as a competitor to criticise.

### Priminfo

```text
User understands insurance parameters
→ enters structured values
→ receives official comparison
```

### LAMal Navigator

```text
User describes a real-life situation
→ Apertus understands the intent
→ the system resolves and validates official parameters
→ official data produces the comparison
→ Apertus explains the verified result
```

Positioning:

> **Priminfo exposes authoritative premium data. LAMal Navigator makes that data conversational, explainable and easier to use correctly.**

---

## 18. Competition strategy

The project should deliberately maximise the five Track 2B judging dimensions.

### Purposeful use of AI

Apertus solves a genuine language problem:

**natural human situation → structured insurance intent → contextual clarification.**

It is essential to the experience but deliberately prevented from performing tasks where deterministic code is safer.

### Technical rigour

The strongest technical story is:

- structured outputs;
- explicit validation;
- deterministic business rules;
- fail-closed behaviour;
- numerical provenance;
- automated tests;
- multilingual evaluation;
- 8B vs 70B benchmark.

### Value, cost and scalability

The system is based on official national data and one reusable architecture.

It can scale across Switzerland without building a separate product for every insurer.

Annual data refreshes can largely be handled by updating official datasets and validating schema changes.

### Sovereign deployability

The complete inference and decision pipeline can run without sending user data to a proprietary foreign LLM.

Apertus, the rules engine and the datasets can all remain on controlled infrastructure.

### Implementation feasibility

The project intentionally avoids dependencies that would make the prototype fragile:

- no insurer-website scraping;
- no complex medical prediction;
- no proprietary data requirement;
- no automatic policy switching;
- no subjective ranking model.

The goal is one reliable end-to-end product rather than many partially implemented features.

---

## 19. Collaboration model

Both contributors should treat this document as the shared product contract.

The work naturally separates into two layers.

### Deterministic layer

- official data loading;
- municipality and region resolution;
- insurer resolution;
- age and accident rules;
- model compatibility;
- comparison;
- financial calculations;
- validation;
- tests.

### Apertus / product layer

- structured extraction;
- conversation state;
- clarification;
- multilingual behaviour;
- grounded explanation;
- interface.

The two layers communicate only through clear structured objects.

Conceptually:

```python
raw_profile = extract_with_apertus(message, conversation_state)

validated_profile = validate_and_resolve(raw_profile)

if validated_profile.needs_clarification:
    return ask_with_apertus(validated_profile)

offers = compare_official_offers(validated_profile)

return explain_with_apertus(validated_profile, offers)
```

This prevents both contributors — and their coding assistants — from independently inventing different product logic.

---

## 20. Product principles

Every new feature should satisfy these principles.

### Correctness before cleverness
A smaller verified system is better than a sophisticated unreliable one.

### Deterministic whenever possible
If a rule can be encoded and tested, use code.

### AI where language matters
Use Apertus for semantic understanding, clarification and explanation.

### Official data first
Official FOPH/Priminfo data is the source of truth.

### Ask rather than guess
Uncertainty must be visible.

### Explain every result
The user should understand why an offer appeared.

### Preserve sovereign portability
Changing the Apertus endpoint should not require rewriting product logic.

### Measure rather than claim
Accuracy and model choice should be demonstrated through evaluation.

### Avoid feature inflation
A trustworthy complete product is stronger than a collection of demos.

---

## 21. What a strong final project should demonstrate

A resident describes their situation naturally.

Apertus understands it in their language.

The system identifies uncertainty and asks only what is missing.

Deterministic Swiss rules convert the conversation into a valid comparison profile.

Official FOPH data provides the offers and premiums.

Python calculates every number.

The user receives only offers compatible with their preferences.

Every result can be inspected and verified.

Apertus explains the decision without being allowed to alter the financial facts.

The same architecture can point to a locally hosted Apertus model.

Its behaviour is measured with a reproducible multilingual evaluation set.

That combination is the project's competitive advantage:

> **useful AI + deterministic correctness + official Swiss data + multilingual accessibility + transparency + sovereign deployment**

---

## North star

> **Build the most trustworthy conversational interface to official Swiss basic-health-insurance data: Apertus understands the user, code enforces the rules, and every result can be verified.**
