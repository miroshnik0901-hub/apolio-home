# APOLIO HOME — Intelligence Architecture v1.0
**Author:** Mikhail Miro
**Date:** 2026-04-01
**Status:** DESIGN — Phase 1 (bot foundation) complete. Intelligence layer pending.
**Context:** Personal finance AI for Mikhail Miro — Italy/Poland/Ukraine, multi-currency, Telegram-native.

---

## 0. DESIGN PRINCIPLE

The raw data — receipts, transactions, account balances — is not valuable by itself.
The value is in what it reveals about the gap between where you are and where you want to be.

**System direction: Goals → down. Not data → up.**

Not: "You spent 380 EUR on food this month."
But: "Your savings goal is 500 EUR/month. You're currently 120 EUR behind pace. Food is 18% over last month. Here are 3 adjustments."

This is the same principle as the CXO OS (APOLIO_CXO_ARCHITECTURE_v3.4): start from goals, move downward, find blind spots, generate 3 paths. Applied here to personal finance instead of corporate strategy.

**Two types of output the system produces:**
1. **Intelligence** — "Here's what's happening" (pattern, trend, anomaly)
2. **Advisory** — "Here's what to do about it" (decision options, tradeoff, recommendation)

The bot currently does neither. It records and retrieves. That's the raw material layer. Everything above that is what gets built next.

---

## 1. ARCHITECTURE OVERVIEW

### 1.1 Layers

```
LAYER 0: CONTEXT (goals, constraints — immutable foundation)
├── Financial goals: savings targets, budget caps, milestones
├── User profile: household composition, income, multi-currency rules
└── Nobody changes this randomly. Updated by explicit user command.

LAYER 1: DATA (what is happening)
├── Transactions: daily expense/income records
├── Receipts: photo-parsed itemized data
├── Conversation log: what user said, when, context
└── Multi-source: manual entry / voice / photo / Wise CSV

LAYER 2: INTELLIGENCE (patterns vs goals)
├── Budget status per envelope
├── Category trends (week/month/quarter)
├── Anomaly detection: unusual spend, category spikes
└── Goal progress: are we on track?

LAYER 3: ADVISORY (proactive recommendations)
├── Blind spots: what's being ignored
├── Decision prompts: "You should decide X"
├── 3-path options for each financial gap
└── Weekly financial brief

LAYER 4: DISPLAY (what you see)
├── Telegram bot: conversational interface
└── (Future) Google Sheets dashboard, web view
```

### 1.2 Data Flow

```
User input (voice / text / photo / CSV)
    ↓
LAYER 1: Transaction recorded in Google Sheets
    ↓
LAYER 2: Intelligence computed on-demand or scheduled
    ↓
LAYER 3: Advisory generated weekly or on trigger
    ↓
LAYER 4: Delivered via Telegram bot response
```

---

## 2. USER CONTEXT ENGINE

### 2.1 What User Context Is

The bot currently knows nothing about the user between sessions except `current_envelope_id` and `lang`. That's enough to record expenses. It's not enough to give advice.

User context is the persistent model of who the user is financially — their goals, patterns, anomalies, and decision history.

### 2.2 Context Structure (stored in Google Sheets — UserContext sheet)

```
USER PROFILE
├── user_id: 360466156
├── name: Mikhail
├── household: [Mikhail, Marina]  (who else contributes to budget)
├── primary_currency: EUR
├── secondary_currencies: [PLN, UAH]
├── countries: [IT, PL, UA]

FINANCIAL GOALS (explicitly set by user)
├── monthly_savings_target: 500 EUR  (e.g.)
├── emergency_fund_target: 5000 EUR
├── monthly_budget_cap: 2500 EUR  (from MM_BUDGET Config)
├── goals_set_at: 2026-01-01
└── goals_updated_at: ...

BEHAVIORAL PATTERNS (auto-derived from transactions)
├── avg_monthly_spend: computed from last 3 months
├── top_categories: [Food, Housing, Transport]
├── high_variance_categories: [Entertainment, Personal]
├── typical_weekly_spend: computed
├── payday_pattern: detected from income records
└── last_updated: ...

CONVERSATION MEMORY
├── last_10_intents: [{timestamp, user_text, detected_intent}, ...]
├── recurring_questions: ["status", "food spend"]
├── last_explicit_goals_discussion: date
└── pending_decisions: ["should we cut entertainment?"]
```

### 2.3 How Context Gets Built

Not by asking the user a questionnaire. Context accumulates automatically:

- **From transactions:** spending patterns, category behavior, anomalies
- **From conversation:** what the user asks about most, what triggers follow-up questions
- **From explicit commands:** "my savings goal is 500 EUR/month" → stored to UserContext
- **From gaps:** if user never mentions income → flag as blind spot

The bot checks for missing critical context and asks once, naturally:
> "По каким категориям считать лимиты? Или делаем по общей сумме?"

Not a form. One question at a time, triggered when relevant.

---

## 3. INTELLIGENCE LAYER

### 3.1 What Gets Computed

**Budget Status** (already exists, basic)
- Spent vs cap per envelope
- Days remaining in month
- Pace: "at this rate you'll hit cap on day 22"

**Category Intelligence** (needs to be built)
- vs last month
- vs average of last 3 months
- Anomaly detection: >2 standard deviations from average = flag

**Goal Progress** (needs to be built)
- Are we on track for monthly savings target?
- Is emergency fund growing?
- Trajectory: at current burn, when does reserve run out?

**Multi-currency Intelligence** (partially exists via Wise import)
- PLN/UAH spend converted to EUR baseline
- FX impact tracking: "food cost rose 8% due to PLN depreciation"
- (Future) FX opportunity alerts

### 3.2 Tiering System (adapted from CXO OS)

Every piece of financial intelligence is classified at compute time:

```
STRATEGIC — affects financial goals or major life milestones
  → "Monthly savings 60% below target — on current pace you won't hit emergency fund goal"
  → Shown prominently in weekly brief and on status request
  → Triggers advisory (blind spot + 3 paths)

OPERATIONAL — affects monthly budget execution, not life goals
  → "Food spend up 15% vs last month"
  → Shown in reports, available on demand
  → Triggers course correction suggestion only if sustained (2+ months)

NOISE — one-off events, FX fluctuations, minor variances
  → Small transactions, ATM fees, single anomalies
  → Recorded, not surfaced
  → Upgrade rule: if same pattern appears 3 months in a row → reclassify as OPERATIONAL
```

### 3.3 Anomaly Detection (v1.0 — rule-based)

Phase 1 uses simple threshold rules. Phase 2 adds statistical detection.

**v1.0 Rules:**
- Single transaction > 3× category average → flag for review
- Category total > 130% of previous month → flag
- No transactions recorded for 3+ days → reminder
- Income not recorded by day 5 of month → prompt

**v2.0 (future):** Z-score based; learned seasonal patterns; merchant-level anomalies.

---

## 4. ADVISORY LAYER

### 4.1 The Core Pattern (from CXO OS, adapted)

For each financial blind spot or gap, the advisory layer generates:

```
BLIND SPOT CARD:
├── What: "You have no savings activity this month"
├── Why it matters: "You're 3 months behind emergency fund target"
├── PATH A: Cut one category (which one, by how much, impact)
├── PATH B: Add income stream or sell asset
├── PATH C: Revise goal timeline (reduce target, extend deadline)
└── RECOMMENDATION: which path and why
```

This is the P4 ADVISOR pattern applied to personal finance.

### 4.2 Weekly Financial Brief (analogous to P4 ADVISOR output)

Generated every Monday 09:00 (Rome timezone) — already scheduled in bot.py.

Structure:

```
📊 APOLIO HOME — Неделя {N}, {date range}

━━━ ФИНАНСОВОЕ СОСТОЯНИЕ ━━━
Потрачено за месяц: {X} EUR из {cap} EUR ({pct}%)
Темп: {status — "в норме" / "превышаем" / "опережаем план"}
До зарплаты: {N} дней | Прогноз остатка: {EUR}

━━━ КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ ━━━
[только STRATEGIC и OPERATIONAL events]
↑ Еда +15% vs прошлый месяц (3-я неделя подряд)
↓ Транспорт -20% — хорошо

━━━ СЛЕПЫЕ ЗОНЫ ━━━
⚠ 1. Накопления: цель 500 EUR/мес → сейчас 0 EUR
   → Мы разобрали 3 варианта: [ссылка на решение]

━━━ РЕШЕНИЕ НЕДЕЛИ ━━━
"Сократить категорию Развлечения на 40 EUR?"
[Да, сократить] [Нет, оставить] [Показать анализ]
```

### 4.3 Triggered Advisory (event-based)

Not everything waits for Monday. Some events trigger immediate advisory:

| Trigger | Advisory |
|---------|----------|
| Spend > 80% of monthly cap | "Осталось {EUR} на {N} дней. Темп высокий." + 2 options |
| Large single transaction (>3× avg) | "Крупная трата: {amount}. Запланировано?" |
| 5 days without transactions | "Не вижу расходов 5 дней. Всё в порядке?" |
| Income recorded | "Доход получен. Распределяем по правилу?" |
| Month closes | "Итог месяца: [summary] vs цели" |

---

## 5. CONVERSATION HISTORY

### 5.1 Why It Matters

The current bot has no memory between sessions. Each conversation starts from scratch. This prevents:
- Understanding recurring questions ("user always asks about food spend → build a food summary dashboard")
- Tracking decision history ("user declined to cut entertainment 3 times → don't suggest it again")
- Continuity ("you were planning to cut Esselunga visits — did you?")

### 5.2 Storage Architecture

New Google Sheets tab: **ConversationLog** in the MM_BUDGET spreadsheet.

Columns:
```
A: timestamp (ISO 8601)
B: user_id
C: direction (user / bot)
D: message_type (text / voice / photo / command)
E: raw_text (user text or transcription)
F: detected_intent (add_transaction / query_status / query_report / greeting / unknown)
G: entities_json ({"amount": 5.0, "currency": "EUR", "category": "Food"})
H: tool_called (add_transaction / get_summary / etc.)
I: tool_result_summary (short: "Added coffee 3.50 EUR")
J: session_id (UUID, groups messages in one conversation session)
```

Retention: keep last 90 days. Auto-purge on each weekly run.

### 5.3 What Gets Stored

**Always stored:**
- Every user message (text, transcription of voice)
- Every bot response (condensed, not full text)
- Tool calls and results

**Not stored:**
- Photo binary data (too large)
- Full agent response text (store summary only)
- Internal agent tool chain steps

### 5.4 How Context Window Uses History

On each new conversation turn, load last 5 exchanges from ConversationLog for this user.
Inject as compressed context into agent system prompt:

```python
RECENT_CONTEXT = """
RECENT CONVERSATION (last 5 turns):
[2026-04-01 10:23] User: кофе 3.50
[2026-04-01 10:23] Bot: ✓ Добавлено — Кофе 3.50 EUR · Food

[2026-04-01 10:45] User: покажи статус
[2026-04-01 10:45] Bot: Потрачено 840 EUR из 2500 EUR (34%)
"""
```

This allows: "удали последнюю" (delete last), "то, что я добавил час назад", continuity between sessions.

---

## 6. RECEIPT INTELLIGENCE

### 6.1 What Should Happen With a Photo

Current behavior (after fix): bot sends photo + prompt to Claude Vision. Claude recognizes text and extracts transactions. Basic.

Target behavior:

1. **Extract** — OCR all line items from receipt, not just total
2. **Parse** — identify merchant, date, individual items with prices
3. **Categorize** — map items to categories (milk → Food:Groceries, beer → Food:Alcohol)
4. **Summarize** — store a structured receipt record with all line items
5. **Confirm** — show parsed items to user for quick confirm/edit before recording
6. **Learn** — if user changes a category, remember for next time at that merchant

### 6.2 Receipt Storage

New Google Sheets tab: **Receipts** in MM_BUDGET.

Columns:
```
A: receipt_id (UUID)
B: transaction_id (FK → Transactions.ID — the parent transaction)
C: date
D: merchant
E: total_amount
F: currency
G: items_json ([{"name": "Latte", "amount": 3.50, "category": "Food"}, ...])
H: ai_summary ("Esselunga grocery run — weekly food shop, 12 items")
I: raw_text (OCR output from Claude Vision)
J: source_photo_id (Telegram file ID for reference)
K: created_at
```

### 6.3 Receipt Confirmation Flow

After photo analysis, bot sends:

```
📄 Esselunga · 15.50 EUR · сегодня

Распознанные позиции:
• Молоко 2л — 1.89 EUR
• Хлеб — 2.20 EUR
• Помидоры — 3.40 EUR
...

Записать как единую трату?

[✅ Да, записать] [✏ Изменить категорию] [📋 Детализировать]
```

If "Детализировать": creates one transaction per line item.
If "Да": creates one parent transaction with items stored in Receipts tab.

---

## 7. IMPLEMENTATION ROADMAP

### Phase 1 — Foundation (complete)
- ✅ Bot core: text, voice, photo input
- ✅ Transaction recording in Google Sheets
- ✅ Basic budget status and reports
- ✅ Multi-language (ru/uk/en/it)
- ✅ Wise CSV import

### Phase 2 — Context & Memory (next 2-4 weeks)
- [ ] ConversationLog tab + storage
- [ ] UserContext tab + goals storage
- [ ] Last-5-turns context injection into agent
- [ ] "удали последнюю" and "что я добавил сегодня" work correctly
- [ ] Photo: confirmation flow with line items
- [ ] Receipts tab storage

### Phase 3 — Intelligence (4-8 weeks)
- [ ] Category trend computation (vs last month, vs 3-month avg)
- [ ] Budget pace alert ("at this rate...")
- [ ] Anomaly detection (threshold-based v1.0)
- [ ] Weekly brief with STRATEGIC/OPERATIONAL split
- [ ] Blind spot detection (no savings activity, missing income record)

### Phase 4 — Advisory (8-12 weeks)
- [ ] Goal-based advisory: 3-path options for each blind spot
- [ ] Decision tracking: log user decisions, don't repeat declined options
- [ ] Monthly close brief: "Month summary vs goals"
- [ ] Triggered advisory (80% cap, large transaction, etc.)
- [ ] Multi-currency intelligence: FX impact on budget

### Phase 5 — Expansion (12+ weeks)
- [ ] Multiple envelopes (Polina, Marina, business)
- [ ] Multi-user sharing (Marina gets her own access with read rights)
- [ ] Dashboard (Google Sheets or web)
- [ ] Statistical anomaly detection (z-score, seasonal)
- [ ] Savings automation suggestions

---

## 8. AGENT SYSTEM PROMPT ENRICHMENT

The current agent system prompt tells Claude what tools to use. The intelligence architecture adds context that makes Claude genuinely useful.

Target system prompt structure (pseudo):

```
## WHO YOU ARE
Apolio Home — personal finance AI for Mikhail. Household: Mikhail + Marina.
Primary currency: EUR. Secondary: PLN, UAH. Countries: Italy, Poland, Ukraine.

## CURRENT STATE
Active envelope: MM_BUDGET
Monthly budget: 2500 EUR
Spent this month: {X} EUR ({pct}%)
Days remaining: {N}

## USER GOALS
Monthly savings target: 500 EUR
Emergency fund target: 5000 EUR (current: {current})
Goals set: {date}

## RECENT PATTERNS
Top categories this month: Food 380 EUR, Housing 1200 EUR, Transport 180 EUR
Anomalies: Food up 15% vs avg (3rd month in a row)
Pending decision: reduce Entertainment?

## RECENT CONVERSATION (last 5 turns)
{conversation_history}

## BEHAVIORAL RULES
- Always respond. Never return empty.
- If unclear input: ask one clarifying question, then act.
- After recording a transaction: confirm with amount, category, and date.
- If spend > 80% of cap: proactively mention.
- If pattern matches known blind spot: surface it once per week max.
```

This transforms the agent from a transaction recorder into a financial thinking partner.

---

## 9. WHAT THIS IS NOT

The intelligence layer should NOT:
- Replace professional financial advice
- Predict market movements or investment returns
- Handle banking or payment execution
- Aggregate bank accounts (no plaid/open banking integration needed — user imports Wise CSV manually)
- Require the user to set up complex rule systems

The philosophy: **low friction, high signal.** The user types "кофе 3.50" and gets back more than just a confirmation — they get a picture of where they stand and what it means.

---

## 10. OPEN QUESTIONS (to decide before Phase 2)

1. **ConversationLog in same spreadsheet or separate?** Recommendation: same MM_BUDGET file, separate tab. Simpler to manage.

2. **UserContext: Sheets tab or JSON in Config?** Recommendation: Sheets tab for structured goals, JSON blob in Config for behavioral patterns (updated by bot).

3. **Receipt confirmation: always or optional?** Recommendation: always for receipts with >3 line items; direct-record for single-item receipts (coffee, fuel).

4. **Weekly brief: push always or only if something changed?** Recommendation: push always on Monday, but suppress if user hasn't been active for 2+ weeks (likely on vacation).

5. **Who manages goals?** Recommendation: user sets goals via natural language ("моя цель — откладывать 500 EUR в месяц"). Bot extracts and stores. Annual review prompt in December.
