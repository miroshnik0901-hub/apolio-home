# Staging & Deploy — регламент для AI-разработчика

> Читать перед любым изменением кода. Не для Mikhail — для AI.

---

## Среды

| Среда | Ветка | Бот | Sheets файл | Railway env ID |
|-------|-------|-----|-------------|----------------|
| Production | `main` | @ApolioHomeBot | MM_BUDGET (`1erXflbF2V7...`) | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |
| Staging | `dev` | @ApolioHomeTestBot | Apolio Home — Test (`1UNhBQqM5...`) | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` |

Railway деплоит автоматически при push в соответствующую ветку.

---

## Рабочий процесс при любом изменении

### 1. Написать/исправить код
```bash
cd /tmp/apolio-work2
git checkout dev
# ... правки ...
git add конкретные_файлы.py
git commit -m "тип: описание"
git push origin dev
# → Railway автоматически деплоит staging (~2 мин)
```

### 2. Проверить деплой staging
Дождаться `status: SUCCESS` через Railway GraphQL или UI:
```
https://railway.com/project/55240cdd-2cbc-4451-b6c9-ca97ce595c18
```

### 3. Самостоятельно протестировать на @ApolioHomeTestBot
- Написать в бот сообщение, релевантное изменению
- Проверить что данные попали в тестовый Sheets (не в реальный MM_BUDGET)
- Проверить логи Railway если что-то не так

### 4. Сообщить Mikhail
Коротко: что изменилось, можно ли проверить на @ApolioHomeTestBot.

### 5. После подтверждения — деплой в продакшн
```bash
git checkout main
git merge dev
git push origin main
# → Railway автоматически деплоит production (~2 мин)
```

---

## Когда НЕ деплоить в main без проверки

- изменения в логике транзакций
- изменения в calculate_obligation / contribution model
- изменения в ensure_envelope_config
- любые изменения схемы Sheets (новые колонки, вкладки)

Для таких изменений — обязательно staging + тест перед merge в main.

Хотфиксы (опечатки, тексты, i18n) — можно сразу в main если очевидно безопасно.

---

## Работа с git из sandbox

Репо находится в `/tmp/apolio-work2` (обычная ФС, не FUSE mount).
FUSE mount (`/sessions/.../mnt/apolio-home`) — только для чтения/редактирования файлов.
Коммитить и пушить — только из `/tmp/apolio-work2`.

После правок в mnt — скопировать файл в /tmp/apolio-work2:
```bash
cp /sessions/lucid-upbeat-pasteur/mnt/apolio-home/bot.py /tmp/apolio-work2/bot.py
```

---

## Переменные окружения Railway

Менять через GraphQL API с `credentials: 'include'` из открытой вкладки railway.com:
```js
fetch('https://backboard.railway.com/graphql/v2', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: `mutation { variableUpsert(input: {
    projectId: "55240cdd-2cbc-4451-b6c9-ca97ce595c18",
    serviceId: "8ec97839-6d49-4cdd-a012-1f6d54853454",
    environmentId: "<env_id>",
    name: "VARIABLE_NAME", value: "value"
  }) }` })
})
```

---

## Проверка статуса деплоев

```js
// В консоли railway.com:
fetch('https://backboard.railway.com/graphql/v2', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: `{ deployments(input: { serviceId: "8ec97839-6d49-4cdd-a012-1f6d54853454" }) { edges { node { status environmentId createdAt } } } }` })
}).then(r=>r.json()).then(d=>console.log(JSON.stringify(d.data.deployments.edges.slice(0,4).map(e=>({env:e.node.environmentId==='08e40bf3-cbe4-4a80-be54-1f291c21fe0d'?'prod':'staging',status:e.node.status})))))
```
