# Product Specification

## 1. Product

CloserOS AI is a connected sales-operations platform for businesses that sell through messaging channels.

It observes the full path between:
- customer;
- qualification bot;
- manager;
- CRM;
- follow-up;
- final outcome.

It converts fragmented conversations into evidence-backed tasks and coaching signals.

A `ConversationThread` is one provider-specific conversation on one authorized channel connection. An optional `SalesCase` may group multiple conversation threads, resolved identities, and CRM deals that belong to the same commercial journey. Grouping does not merge or rewrite the source histories.

## 2. Core problem

Businesses already use simple bots that ask basic questions and hand the lead to a manager. The main operational failures happen after or around that handoff:

- the customer waits too long;
- bot context is lost;
- the manager repeats questions;
- some questions remain unanswered;
- no next step is proposed;
- objections are mishandled;
- promised follow-up is missed;
- CRM status does not match the conversation;
- owners cannot inspect hundreds of chats.

## 3. Product promise

CloserOS helps sales teams identify and correct measurable process failures in messaging-based sales.

Do not promise a fixed percentage increase in sales until controlled evidence exists.

Approved positioning:

> Connect your sales chats, see where leads stall, and turn missed actions into a managed follow-up process.

## 4. Initial production release

### 4.1 Observer mode

CloserOS connects without replacing the existing bot, manager workflow, phone number, or CRM.

It:
- ingests new messages;
- imports approved history where supported;
- identifies bot/customer/manager/system messages;
- computes deterministic metrics;
- creates evidence-backed AI findings;
- creates follow-up tasks;
- produces owner and manager views;
- accepts human feedback.

It does not automatically send messages.

### 4.2 Owner dashboard

Required:
- total new leads;
- answered leads;
- unanswered leads;
- qualified leads from CRM;
- won/lost/unresolved outcomes from CRM;
- follow-up due and overdue;
- SLA breaches;
- top evidence-backed process issues;
- connection health and data freshness.

Every metric must drill down to the underlying conversations.

Before a CRM is connected, CRM-dependent metrics such as qualified, won, lost, amount, and outcome conversion display as unavailable. When CRM synchronization exceeds the configured freshness policy, those metrics display as stale with the last successful sync time. CloserOS must never use AI to infer factual qualified, won, or lost metrics.

### 4.3 Conversation review

Required:
- canonical chronological timeline for one ConversationThread;
- optional SalesCase context linking related threads and CRM deals;
- sender type: customer, bot, manager, system;
- response-time metrics;
- unanswered questions;
- detected objections;
- CTA/next-step findings;
- follow-up status;
- AI findings with evidence;
- human accept/reject/correct actions;
- authorized raw-data reveal.

### 4.4 Manager scorecards

Two separate concepts:

**Process score**
- response discipline;
- question coverage;
- discovery quality;
- next-step discipline;
- objection handling;
- follow-up discipline;
- factual accuracy.

**Outcome score**
- qualified leads;
- appointments;
- won deals;
- lost deals;
- cycle time;
- value or margin where available.

Never combine them into an unexplained single score.

### 4.5 Follow-up queue

Required:
- ConversationThread and optional SalesCase context;
- manager;
- reason;
- due time;
- priority;
- evidence;
- suggested message;
- status;
- human action.

No outbound message is sent automatically in the initial release.

### 4.6 Knowledge base

Tenant-scoped sources:
- prices;
- services;
- FAQ;
- scripts;
- promotions;
- policies;
- prohibited claims.

Requirements:
- document versions;
- effective dates;
- approval status;
- tenant isolation;
- citations in generated recommendations.

## 5. Revenue language

### Allowed

- opportunities at risk;
- estimated revenue at risk;
- recovery candidates;
- model assumptions;
- low/base/high scenario.

### Prohibited without proof

- “You lost exactly X.”
- “CloserOS will increase revenue by 30%.”
- “This manager cost the company X.”
- any result that treats every unresolved lead as a sale.

CRM is the source of truth for final outcomes. Revenue-at-risk is an estimate, not an accounting fact.

## 6. Initial users

### Owner
Needs a high-level operational view and evidence for intervention.

### Sales Head
Needs a risk queue, scorecards, review tools, and coaching actions.

### Manager
Needs assigned tasks, context, and suggested next actions.

### Analyst
Needs reporting without administrative access.

### Compliance Admin
Needs retention, export, deletion, access, and audit controls.

## 7. Initial vertical strategy

Do not hard-code medical, legal, migration, or children's-data workflows into the first release.

Choose the first vertical based on:
- paid design-partner demand;
- lawful access to data;
- non-sensitive conversation content;
- clear CRM outcomes;
- enough lead volume;
- available official integrations.

Likely lower-risk starting candidates:
- automotive sales;
- adult education with restricted data categories;
- ordinary B2B services;
- home and repair services;
- selected real-estate workflows after legal review.

## 8. Product success metrics

Pilot metrics must be agreed before connection.

Examples:
- percentage of leads receiving a first response within SLA;
- unanswered qualified leads;
- overdue follow-up rate;
- question-coverage rate;
- conversion from qualified lead to appointment;
- manager adoption of recommended tasks;
- percentage of AI findings accepted by reviewers;
- false-positive rate by issue type;
- time saved by the sales head.

Do not use vanity metrics such as number of AI analyses alone.

## 9. Out of scope for the first production release

- autonomous outbound messaging;
- replacing CRM;
- universal historical access to all messengers;
- live draft interception in native WhatsApp or Instagram apps;
- employee punishment automation;
- medical or legal advice;
- cross-tenant raw-data learning;
- custom model training;
- voice-call intelligence;
- mobile application;
- microservices.
