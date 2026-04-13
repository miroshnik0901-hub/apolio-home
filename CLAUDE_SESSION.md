# CLAUDE_SESSION.md — Живой рабочий журнал

> **Правила:**
> - Читать ПЕРВЫМ в начале каждой сессии — до кода, до задач, до всего.
> - Обновлять в конце каждой сессии — что сделано, что отложено, какие решения приняты.
> - Писать так, чтобы "следующий Claude" с нулевым контекстом мог продолжить без потерь.
> - НЕ заменяет CLAUDE_WORKING_GUIDE.md (архитектура) и DEV_CHECKLIST.md (QA). Дополняет их.

---

## Последнее обновление

**Дата:** 2026-04-13
**Сессия:** Очистка проекта, фиксы T-150, форматирование Sheets, структура документации

---

## Текущее состояние системы

- **Prod бот:** @ApolioHomeBot — работает, задеплоен
- **Staging бот:** @ApolioHomeTestBot — работает
- **Ветки:** `main` и `dev` синхронизированы (коммит `c4e3e7c`)
- **Активных задач в Task Log:** 0 (все CLOSED или DISCUSSION закрыты)
- **Prod Google Sheets:** структура приведена в соответствие с тестом

---

## Что было сделано в последней сессии

1. **T-150 (Topic validation)** — исправлена валидация: пустой topic теперь не проходит. Задеплоено в prod.
2. **Budget Config (prod)** — числовые значения были строками (`'2500'`). Исправлено: записаны как числа.
3. **Admin Config + DashboardConfig (prod)** — то же. `alert_threshold_pct`, `history_months` — числа.
4. **Dashboard формат** — prod Dashboard был в старом русскоязычном формате. Перезаписан новым `[SNAPSHOT]` форматом + исправлен сброс форматирования ячеек (старые date/% форматы портили новые значения).
5. **Topic config** — удалены `Bug Fix` и `Process` из config sheet и из fallback в коде.
6. **Очистка папки** — удалено 16 устаревших файлов.
7. **Документация** — реструктурирована: Project Instructions (lean pointer), CLAUDE.md (правила + workflow), создан этот файл.

---

## Активные задачи (Task Log)

*Нет активных задач на момент последнего обновления.*

При начале новой сессии — читать Task Log через:
```bash
export $(grep -v '^#' .env | xargs)
python3 -c "
from task_log import TaskLog
tl = TaskLog()
for t in tl.get_all_tasks():
    if t.get('Status') in ('OPEN', 'IN PROCESS', 'DISCUSSION', 'BLOCKED'):
        print(f\"[{t['ID']}] {t['Status']} | {t['Task'][:80]}\")
        print(f\"  {t.get('Apolio Comment','')[:200]}\")
"
```

---

## Отложенные вопросы (требуют решения Mikhail)

1. **Budget Config values** — `monthly_cap` и `split_rule` в проде были перезаписаны тестовыми значениями (3500, 50_50). Mikhail сказал что поправит сам. Проверить после правки что Dashboard пересчитался.
2. **Apps Script (task_log_automation.js)** — нужно вручную обновить в Google Sheets: Extensions → Apps Script → вставить содержимое `apps_script/task_log_automation.js` → Save → Run `setupTriggers()`. Формат `Resolved At` изменён на `yyyy-mm-dd hh:mm`.
3. **Файлы без решения по удалению:**
   - `APOLIO_CXO_ARCHITECTURE_v3.4.md` — другой продукт (CXO OS). Оставить или убрать из этой папки?
   - `SELF_LEARNING_ALGORITHM.md` — актуальна ли спека?
   - `TZ_Budget_Rules_v1.md` — актуальна ли?
   - `MENU_DASHBOARD_DESIGN.md` — T-112/T-113 выполнены?

---

## Ключевые технические решения этой сессии

- **`value_input_option='USER_ENTERED'`** при записи Config — иначе числа пишутся строками с `'` префиксом
- **Сброс форматирования Dashboard** — после `ws.clear()` нужно `repeatCell` с пустым `numberFormat` через batch_update, иначе старые форматы (дата, %) портят новые значения формул
- **Topic** — только 6 значений: Interface, Features, Data, Infrastructure, AI, Docs. Bug Fix и Process удалены везде.
- **CLAUDE.md** — единственный источник правды для операционных правил. Project Instructions — только pointer.

---

## Как использовать DEV_CHECKLIST.md

Не запускать всё подряд. Алгоритм:
1. Перед написанием кода — прочитать секцию "BEFORE making a change" (4 пункта)
2. Определить какие области затрагивает изменение (i18n / UI / transactions / agent / etc.)
3. Запустить только соответствующие секции DEV_CHECKLIST
4. L1 + L2 (`py_compile` + `test_regression.py`) — **всегда**, перед каждым push в dev
5. После push в dev — `tests/run_all.py` + Railway logs
6. L4/L5 (бот-тесты) — при изменениях в bot.py, agent.py, menu_config.py

---

## Как обновлять этот файл

В конце каждой рабочей сессии обновить:
- Дату и название сессии
- "Что было сделано" — конкретно, с именами файлов и задач
- "Активные задачи" — если что-то начато но не закончено, полный контекст
- "Отложенные вопросы" — всё что ждёт решения Mikhail
- "Ключевые решения" — нетривиальные технические выборы
