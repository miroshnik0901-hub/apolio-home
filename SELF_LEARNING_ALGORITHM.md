# Apolio Agent — Self-Learning Algorithm
# Version: 1.0 | Author: Apolio Architect
# This file defines HOW the agent learns from every interaction.
# It is the authoritative spec. Code in db.py, agent.py must match it.

---

## PHILOSOPHY

The agent improves with every conversation. It does NOT retrain a model.
Instead, it builds a **personal knowledge base per user** stored in PostgreSQL,
and uses it to make smarter decisions on every new message.

There are three layers of learning:
1. **Vocabulary** — which words the user uses for which categories/people/accounts
2. **Corrections** — what the agent got wrong, and the right answer
3. **Patterns** — recurring transactions the agent should recognize and suggest automatically

---

## LEARNING EVENTS

Every learning event has a type. The agent calls `save_learning` tool after each one.

### Type 1: `vocabulary`
**Trigger:** User says a word/phrase and it maps to a transaction field.
The agent infers: "when this user says X → they mean category=Y, subcategory=Z"

**Examples:**
- "шаурма" → category=Food, subcategory=Fast Food
- "заправка" → category=Transport, subcategory=Fuel
- "садик" → category=Education, note=kindergarten, who=Polina
- "comunali" → category=Home, subcategory=Utilities (Italian word)
- "марина отдала" → who=Marina, type=income (contribution)

**Storage:**
```json
{
  "event_type": "vocabulary",
  "trigger": "шаурма",
  "mapped_to": {"category": "Food", "subcategory": "Fast Food"},
  "confidence": 0.9,
  "times_confirmed": 1
}
```

**Usage:** Before interpreting a message, check vocabulary table.
If trigger word found with confidence >= 0.75 → use mapped values directly.

---

### Type 2: `correction`
**Trigger:** User says "не так", "исправь", "не 45 а 54", "это была Marina", etc.
Agent extracts what field was wrong and what the right value is.

**Examples:**
- "не 45 а 54" → field=amount, wrong=45, correct=54
- "это была Марина" → field=who, wrong=Mikhail, correct=Marina
- "категория не еда а транспорт" → field=category, wrong=Food, correct=Transport
- "вчера было, не сегодня" → field=date, wrong=today, correct=yesterday

**Storage:**
```json
{
  "event_type": "correction",
  "field": "category",
  "original_value": "Food",
  "corrected_value": "Transport",
  "original_input": "заправка 50 EUR",
  "confidence_penalty": -0.3
}
```

**Usage:** If vocabulary entry exists for a trigger and got corrected → lower its confidence.
If confidence < 0.4 → remove it. Correct the transaction immediately.

---

### Type 3: `confirmation`
**Trigger:** User says "да", "верно", "правильно", "точно", "ок" after an agent interpretation.

**Storage:**
```json
{
  "event_type": "confirmation",
  "confirmed_interpretation": {"category": "Food", "subcategory": "Coffee", "amount": 3.50},
  "original_input": "кофе 3.50",
  "confidence_boost": 0.1
}
```

**Usage:** Boost confidence of vocabulary/pattern entries that produced this interpretation.
Entry confirmed 3+ times → confidence capped at 0.98, skip confirmation in future.

---

### Type 4: `pattern`
**Trigger:** Agent detects that similar transactions appear repeatedly (same category/amount/who/day-of-month).
Detected after 3+ similar transactions in 60-day window.

**Examples:**
- Rent 1200 EUR every 1st of month → "Affitto" pattern, who=Joint
- Kindergarten fee 250 EUR every 5th → "Sadik" pattern, who=Polina
- Weekly grocery run 60-90 EUR every Saturday → Food/Groceries pattern

**Storage:**
```json
{
  "event_type": "pattern",
  "description": "Monthly rent payment around 1st of month",
  "match_rule": {"category": "Home", "subcategory": "Rent", "amount_range": [1150, 1250], "day_of_month": [1, 2, 3]},
  "who": "Joint",
  "times_seen": 4,
  "last_seen": "2026-03-01",
  "suggest_template": true
}
```

**Usage:** When new transaction matches pattern → say:
"Похоже на регулярный платёж: Аренда 1200 EUR (видел 4 раза). Записать как обычно?"

---

### Type 5: `new_value`
**Trigger:** User approves adding a new category, subcategory, account, or user via `force_new=true`.

**Storage:**
```json
{
  "event_type": "new_value",
  "field": "category",
  "value": "Автомобиль",
  "subcategory": "Страховка",
  "approved_by_user": true
}
```

**Usage:** Add to reference data. Next time → no validation block, no question.

---

### Type 6: `ambiguity_resolved`
**Trigger:** Agent was unsure, showed hypothesis, user confirmed or corrected.
Stores: what was ambiguous, what the correct interpretation was.

**Storage:**
```json
{
  "event_type": "ambiguity_resolved",
  "input": "вот чек",
  "was_ambiguous": true,
  "resolution": "record_transactions",
  "outcome": {"transactions_recorded": 3, "total_eur": 527.2}
}
```

**Usage:** Build understanding of what "ambiguous" phrases actually mean to this user.

---

## CONFIDENCE SCORING

Every vocabulary and pattern entry has a `confidence` score (0.0 → 1.0):

| Confidence | Meaning | Agent behavior |
|-----------|---------|----------------|
| < 0.4 | Unreliable | Ignore, ask user |
| 0.4 – 0.74 | Plausible | Use as suggestion, show in hypothesis |
| 0.75 – 0.94 | High | Use directly, brief confirmation |
| >= 0.95 | Certain | Use directly, no confirmation needed |

Initial confidence on first observation: **0.7**
Each confirmation: **+0.1** (capped at 0.98)
Each correction: **−0.3** (removed if < 0.2)

---

## AMBIGUITY DETECTION RULES

Before executing ANY action, the agent evaluates confidence:

**EXECUTE IMMEDIATELY (no confirmation) if ALL are true:**
- Amount is explicit (number in message or image)
- Intent is clear (expense/income/contribution)
- Vocabulary match confidence >= 0.75 OR category is obvious from text
- No conflicting signals

**ASK FOR CONFIRMATION if ANY is true:**
- Amount missing and can't be read from image
- Intent unclear (could be expense or income)
- Multiple transactions found in image (always confirm list)
- New vocabulary/category not in reference data
- Vocabulary match confidence < 0.75
- Image with vague caption ("вот", "смотри", "это")
- Message ambiguous between "record" and "question about data"

**NEVER ASK if:**
- User previously confirmed this interpretation 3+ times (confidence >= 0.95)
- Explicit instruction given ("запиши", "добавь", "record this")
- Correction of previous entry ("не 45 а 54" → edit immediately)
- Simple question (не запись, а вопрос: "сколько потратили?")

---

## LEARNING PIPELINE

```
User message
     ↓
[Ambiguity check] → ambiguous? → show hypothesis → user responds
     ↓                                                    ↓
[Execute]                                    [confirmation/correction]
     ↓                                                    ↓
[Pattern detection]                           [save_learning(type)]
     ↓                                                    ↓
[Vocabulary extraction]                      [update confidence scores]
     ↓
[save_learning if new vocab/pattern]
```

---

## STORAGE

### PostgreSQL table: `agent_learning`
Primary storage. Fast, reliable, survives restarts.

```sql
CREATE TABLE IF NOT EXISTS agent_learning (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id       BIGINT NOT NULL,
    envelope_id   VARCHAR(64) DEFAULT '',
    event_type    VARCHAR(50) NOT NULL,
    trigger_text  TEXT DEFAULT '',
    context_json  JSONB DEFAULT '{}',
    learned_json  JSONB DEFAULT '{}',
    confidence    FLOAT DEFAULT 0.7,
    times_seen    INT DEFAULT 1,
    last_seen_ts  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_learning_user_type ON agent_learning (user_id, event_type);
CREATE INDEX IF NOT EXISTS idx_learning_trigger ON agent_learning (user_id, trigger_text);
```

### Google Sheets Admin file: `Learning` tab
Human-readable summary, auto-updated weekly by `refresh_learning_summary` tool.
Columns: User | Type | Trigger | Learned | Confidence | Times Seen | Last Seen

Admins can manually edit/delete learning entries from the sheet.
Bot reads the sheet on startup and syncs to PostgreSQL.

---

## TOOLS

### `save_learning` (agent.py TOOLS)
Called by agent after every interaction that produced learning.

Input:
```json
{
  "event_type": "vocabulary|correction|confirmation|pattern|new_value|ambiguity_resolved",
  "trigger": "optional — the input word/phrase",
  "learned": {"field": "category", "value": "Food", ...},
  "confidence_delta": 0.1,
  "original_input": "кофе 3.50"
}
```

### `get_learning_context` (agent.py TOOLS)
Called at start of each message processing.
Returns: vocabulary matches for current input + active patterns.
Used by agent to decide: execute immediately vs. confirm.

### `refresh_learning_summary` (admin tool)
Aggregates agent_learning table and writes summary to Google Sheets `Learning` tab.
Callable manually or on schedule.

---

## PRIVACY & SAFETY

- Learning is per-user (user_id scoped). Never shared between users.
- Corrections always override — wrong entries are demoted immediately.
- Admin can view and delete any learning entry via Google Sheets.
- No sensitive data (amounts, personal notes) stored in learning events — only patterns and vocabulary mappings.
- Learning events for `correction` and `ambiguity_resolved` store anonymized signals (field names, categories) — not raw amounts.

---

## WHAT THE AGENT DOES NOT LEARN

- Preferences that change frequently (active envelope) → UserContext, not Learning
- Language preference → UserContext
- Financial goals → UserContext
- Actual transaction data → Transactions sheet
- Conversation history → PostgreSQL conversation_log

Learning is ONLY about: vocabulary, patterns, and interpretation correctness.
