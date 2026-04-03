"""
One-time script: batch-update task log for completed dev-session fixes.
Run once from the repo root after setting GOOGLE_SERVICE_ACCOUNT env var.
"""
from task_log import TaskLog

tl = TaskLog()

updates = [
    # T-030: duplicate detection — code done
    ("T-030", "IN PROCESS", "Реализована проверка дублей в tool_add_transaction: "
     "если в тот же день уже есть запись с тем же amount+category+who — возвращает confirm_required/duplicate. "
     "Агент может обойти с force_add=true. Схема инструмента в agent.py обновлена.", "READY", ""),

    # T-034: Marina/Maslo — code done
    ("T-034", "IN PROCESS", "Добавлена функция _normalize_who() в tools/transactions.py: "
     "при вводе 'Marina Maslo' → автоматически корректируется до 'Marina' (known user). "
     "Работает тихо, без запроса подтверждения. Phantom-пользователи в отчётах исчезнут.", "READY", ""),

    # T-039: envelope filter — code done
    ("T-039", "IN PROCESS", "Добавлена фильтрация конвертов по правам доступа в cb_envelopes, "
     "cmd_envelopes и menu command 'envelopes'. Не-admin пользователи видят только свои конверты.", "READY", ""),

    # T-038: база знаний недоступна — explanation, no code needed
    ("T-038", "CLOSED", "Не баг в коде. PostgreSQL (DATABASE_URL) не настроен в Railway staging environment. "
     "База знаний недоступна именно в тест-боте из-за отсутствия подключения к БД. "
     "Fix: добавить DATABASE_URL в Railway Staging environment variables.", "N/A", ""),

    # T-040: TEST режим — explanation
    ("T-040", "CLOSED", "Фича работает корректно. Надпись '🧪 Переключено в TEST режим' появляется "
     "при переключении режима через /settings → DashboardConfig mode=test. "
     "TEST mode: использует MM_TEST_FILE_ID вместо prod sheet.", "N/A", ""),

    # T-042: test bot shows prod data — explanation
    ("T-042", "DISCUSSION", "Причина: Railway Staging env использует те же ADMIN_SHEETS_ID и MM_BUDGET_FILE_ID "
     "что и production. Fix (без кода): в Railway Dashboard → Staging environment → "
     "ADMIN_SHEETS_ID=1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM "
     "и MM_BUDGET_FILE_ID=196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788", "N/A", ""),

    # T-043: test bot shows real envelope — same root cause as T-042
    ("T-043", "CLOSED", "Та же причина что T-042 — Staging environment variables совпадают с prod. "
     "После фикса T-042 (смены env vars в Railway Staging) решится автоматически.", "N/A", ""),

    # T-032: budget_MM_BUDGET_monthly hardcoded — explanation
    ("T-032", "CLOSED", "Переменная budget_MM_BUDGET_monthly есть только в setup_sheets_v2.py (одноразовый скрипт). "
     "В runtime cap читается из Monthly_Cap в Config-вкладке конверта через read_envelope_config(). "
     "Не является production-проблемой.", "N/A", ""),
]

for task_id, status, comment, deploy, confirm in updates:
    ok = tl.update_task(
        task_id,
        status=status,
        comment=comment,
        deploy=deploy if deploy else None,
        confirm=confirm if confirm else None,
    )
    print(f"{'✓' if ok else '✗'} {task_id} → {status} / {deploy}")

print("\nDone.")
