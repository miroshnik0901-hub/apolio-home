# Apolio Home — Research & Analysis Prompt Template

Use this template when asking Claude to analyze any aspect of Apolio Home: architecture decisions, feature design, competitive positioning, or intelligence layer planning.

The template ensures you get structured, actionable output — not vague recommendations.

---

## HOW TO USE

Copy the template below, fill in the [BRACKETED] sections, paste into a new Claude conversation.
You don't need to paste the full codebase — describe the relevant pieces.

---

## TEMPLATE

```
# Apolio Home Research Brief

## Context
Apolio Home is an AI-powered personal finance assistant for Mikhail Miro — a businessman
in Pino Torinese, Italy, operating across Italy, Poland, and Ukraine.

Bot: @ApolioHomeBot (Telegram, Python/PTB 20.7)
Stack: Python, Anthropic Claude API, Google Sheets, Telegram
Intelligence architecture: APOLIO_HOME_INTELLIGENCE_v1.0.md
CXO OS reference: APOLIO_CXO_ARCHITECTURE_v3.4.md

Primary user: Mikhail Miro, admin
Languages: Russian (default), Ukrainian, English, Italian — often mixed
Active envelope: MM_BUDGET (monthly cap 2500 EUR)

## What I'm Researching
[DESCRIBE THE QUESTION IN ONE SENTENCE]
Example: "How should I design the conversation history storage to enable
coherent multi-turn sessions without hitting API context limits?"

## Current State
[DESCRIBE WHAT EXISTS NOW — briefly]
Example: "The bot currently has no conversation persistence. Each message
is independent. SessionContext is in-memory only."

## The Problem or Gap
[WHAT IS NOT WORKING / WHAT IS MISSING]
Example: "When user says 'delete the last one', the bot has no memory
of what was added. When user returns next day, context is gone."

## Constraints
[HARD LIMITS]
- Budget: [e.g., free tier / Railway $5/month]
- Complexity: [e.g., no new infrastructure, Google Sheets only]
- Timeline: [e.g., want to implement in 1-2 days]
- Compatibility: [e.g., must work with existing gspread setup]

## What I Want
Analyze this and give me:

1. **OPTION A / B / C** — 3 distinct approaches with tradeoffs
2. **RECOMMENDATION** — which one and why, given my specific constraints
3. **BLIND SPOTS** — what am I not thinking about that will bite me
4. **IMPLEMENTATION SKETCH** — just enough code/structure to start

Design principle: start from what the user needs to feel, then design backward.
Not "what's technically easy to store" but "what enables Mikhail to say
'покажи что я добавил вчера' and get the right answer."
```

---

## EXAMPLE FILLED PROMPT

```
# Apolio Home Research Brief

## What I'm Researching
How to design receipt photo analysis so the confirmation flow doesn't
feel like a form — it should feel like the bot understood the receipt and
is just confirming with me.

## Current State
Bot receives photo, passes to Claude Vision with prompt "это фото чека,
распознай транзакции". Claude returns text. Bot sends that text as response.
No structured parsing, no confirmation flow, no line-item storage.

## The Problem or Gap
The response is a wall of text. User has to read it, can't quickly approve
or correct individual items. No itemized storage for future analysis.
Also: if receipt is from Esselunga (regular merchant), bot doesn't recognize
it as known — asks same clarifying questions every time.

## Constraints
- No new infrastructure: must use Google Sheets for storage
- Must work with existing photo handler in bot.py
- Must feel conversational, not like a web form
- Receipt confirmation must complete in max 2 messages from user

## What I Want
Analyze this and give me 3 approaches with tradeoffs + recommendation
+ blind spots + implementation sketch.

Design principle: start from the user experience — Mikhail is standing
at the checkout, just took a photo of the receipt, phone in one hand.
The flow must be one-tap for known merchants, two steps max for new ones.
```

---

## ARCHITECTURE DECISION TEMPLATE

For larger architectural decisions (not just feature design):

```
# Architecture Decision — [TITLE]

## Decision Required
[ONE SENTENCE: what needs to be decided]

## Options on the Table
A) [OPTION A — brief]
B) [OPTION B — brief]
C) [OPTION C — brief]

## Evaluation Criteria (in priority order)
1. Reliability: must work without maintenance
2. Simplicity: Mikhail maintains this himself
3. Extensibility: adding Polina envelope in 6 months must not require rewrite
4. Cost: stays on Railway free/hobby tier

## Reference Architecture
Read: APOLIO_HOME_INTELLIGENCE_v1.0.md (sections [X, Y])
Philosophy: system starts from goals, moves downward. Data is raw material.
Intelligence is what gets built on top.

## What I Want
Evaluate the 3 options against the criteria above.
For the recommended option: describe the implementation in enough
detail that a developer can start tomorrow without asking questions.
Surface any assumptions I'm making that may be wrong.
```

---

## WHEN TO USE WHICH

| Situation | Template |
|-----------|----------|
| Feature design question | Main template |
| "Should I use X or Y?" | Architecture Decision template |
| "How does X work in production?" | Main template, fill Current State with "nothing yet" |
| Competitive research | Ask directly: "Compare [feature] across Cleo, Monarch, YNAB, Apolio Home" |
| Code review of specific file | Paste the file + "What's missing? What will break?" |
| System prompt improvement | "Read ApolioHome_Prompt.md. What's making the bot silent/wrong?" |
