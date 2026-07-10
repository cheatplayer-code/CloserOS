# AI System Specification

## 1. Purpose

AI is used for context-dependent classification and recommendation. It is not the system of record.

Good AI tasks:
- objection classification;
- unanswered-question detection;
- handoff quality;
- discovery quality;
- next-step quality;
- grounded suggested reply;
- short conversation summary.

Non-AI tasks:
- timestamps;
- response time;
- delivery status;
- CRM outcome;
- message count;
- SLA;
- identity;
- permissions;
- revenue arithmetic.

## 2. Provider abstraction

Define an application port similar to:

```text
analyze_conversation(request) -> validated analysis
generate_suggestion(request) -> validated suggestion
health() -> provider health
estimate_cost(request) -> estimate
```

Initial adapter: DeepSeek.

The domain must not depend on provider model names or SDK types.

## 3. Input gate

External AI calls require:
- tenant policy permits the operation;
- message text is sanitized;
- sensitive-data detector allows it;
- conversation size is within policy;
- purpose is supported;
- input hash is calculated;
- provider budget is available.

Sanitized text remains potentially pseudonymized personal data until qualified legal counsel confirms otherwise. The gateway must continue to enforce approved location, purpose, vendor, retention, and access policies for sanitized input.

Fail closed when redaction confidence is insufficient.

## 4. Structured output

All outputs are validated against strict schemas.

A conversation finding includes:
- issue code from controlled taxonomy;
- severity;
- confidence;
- evidence message IDs;
- concise explanation;
- recommended action;
- optional grounded knowledge citations.

Reject:
- unknown codes;
- missing evidence;
- nonexistent evidence IDs;
- unsupported factual claims;
- malformed output;
- output containing apparent raw identifiers.

## 5. Prompt design

Stable prefix:
- task;
- rubric;
- issue taxonomy;
- output schema;
- safety constraints;
- examples.

Variable suffix:
- tenant-approved context;
- sanitized messages.

Store:
- prompt version;
- rubric version;
- model/provider;
- parameters;
- input hash;
- output hash;
- token usage;
- latency;
- validation status.

Never store chain-of-thought.

## 6. Confidence and review

Example policy:
- high-confidence, low-impact finding: visible with review available;
- medium-confidence finding: marked for review;
- low-confidence finding: hidden from aggregate score until reviewed;
- high-impact finding: always reviewed.

Thresholds must be calibrated from evaluation data, not invented permanently.

## 7. Evaluation

Build a versioned, lawfully obtained, sanitized evaluation set.

Measure per issue:
- precision;
- recall;
- false-positive rate;
- reviewer agreement;
- evidence accuracy;
- language breakdown;
- model cost and latency.

Include:
- Russian;
- Kazakh;
- mixed-language conversations;
- short and long chats;
- bot-manager handoff;
- ambiguous outcomes;
- adversarial text.

A model change cannot enter production without regression evaluation.

## 8. Feedback loop

Human feedback:
- accept;
- reject;
- correct code;
- correct evidence;
- correct explanation;
- correct suggested action.

Use feedback for:
- rubric improvement;
- prompt improvement;
- evaluation;
- future model selection.

Do not use tenant content for cross-tenant training without explicit legal and contractual approval.

## 9. Knowledge grounding

Recommendations involving business facts must use tenant-approved sources.

Requirements:
- tenant-isolated retrieval;
- source version;
- effective date;
- citation;
- rejection of expired/unapproved documents;
- no cross-tenant vector search.

## 10. Cost control

- deterministic code first;
- analysis only on new/changed content;
- content hashes;
- cached sanitized results;
- bounded output;
- batch work where provider supports it safely;
- per-tenant budget;
- model routing;
- circuit breaker;
- cost dashboards.

## 11. Provider outage

- ingestion continues;
- analysis state becomes pending;
- retry within policy;
- surface stale analysis;
- never drop source messages;
- provide manual review path.

## 12. Safety language

AI text must be labeled as generated or suggested.

The UI must not present:
- probability as certainty;
- revenue estimate as accounting fact;
- score as an employment verdict;
- invented business facts;
- unsupported policy claims.
