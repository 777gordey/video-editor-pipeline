# Деплой на боевой n8n (194.154.29.60)

Этот пайплайн — НОВЫЙ, изолированный воркфлоу. Он не трогает существующие
боевые воркфлоу (`med agent boss`, «Алина» и т.д.), но требует одного
изменения на уровне контейнера n8n — добавления переменных окружения.

## Что нужно от владельца (не делается автоматически)

1. **GitHub PAT** с правами `repo` (классический токен, не fine-grained —
   проще). Создать: https://github.com/settings/tokens → Generate new token
   (classic) → scope `repo`. Не присылать в чат — вставить сразу в шаге 3.
2. **Тестовое видео** до 5 минут — положить на VPS в `/root/video-pipeline/test/source.mp4`.

## Шаг 1 — переменные окружения контейнера n8n

Контейнер `n8n` НЕ управляется активным `docker-compose.yml` (создан вручную,
см. память `project-n8n-vps`) — добавить переменные можно только пересозданием
контейнера (`docker update` их не поддерживает). Это ~15 секунд простоя n8n
(соответственно и бота Егора). Процедура (уже проверялась 31.08 при плановом
пересоздании):

```bash
# 1. Снять текущий конфиг для сверки
docker inspect n8n > /root/n8n_inspect_before_video_pipeline.json

# 2. Аккуратно остановить и удалить контейнер (данные в volume n8n_data, не теряются)
docker stop n8n && docker rm n8n

# 3. Пересоздать с ТЕМИ ЖЕ параметрами + новыми переменными
#    (image ID и сети — как в n8n_inspect_before_video_pipeline.json,
#     см. проверенную процедуру в памяти project-n8n-vps)
docker run -d --name n8n \
  --network ai_stack_default \
  --restart always \
  -v n8n_data:/home/node/.n8n \
  -e WEBHOOK_URL=https://gordey1-bot.duckdns.org \
  -e N8N_HOST=gordey1-bot.duckdns.org \
  -e N8N_SECURE_COOKIE=false \
  -e TELEGRAM_BOT_TOKEN='<токен нового видео-бота>' \
  -e GITHUB_OWNER='<ваш GitHub логин>' \
  -e GITHUB_REPO='video-editor-pipeline' \
  -e ALLOWED_USER_ID='<ваш Telegram user_id>' \
  <IMAGE_ID из n8n_inspect_before_video_pipeline.json>

docker network connect bridge n8n
docker update --memory=2048m n8n
```

**Это действие я НЕ выполняю сам без вашего явного подтверждения** — сервер
боевой, простой хоть и короткий, но затрагивает реальный медицинский бот.
Дайте отмашку — либо выполню сам по SSH, либо пришлю точные команды вам.

## Шаг 2 — credentials в n8n UI

При импорте `n8n/video-pipeline-workflow.json` (Import from File) n8n попросит
привязать credentials — создать:

- **Telegram API** (тип `telegramApi`) — токен нового бота.
- **GitHub API** (тип `githubApi` или generic `httpHeaderAuth` с заголовком
  `Authorization: Bearer <PAT>`) — тот же PAT из шага «Что нужно от владельца».

Узлы `Reject`, `Notify timeout`, `Notify failure`, `Send result`, `Telegram
Trigger` — привязать к Telegram-credential. Узлы `Trigger GitHub Action`,
`Find run`, `List artifacts`, `Download artifact zip` — к GitHub-credential.

## Шаг 3 — активация

Активировать воркфлоу через UI (не через API — см. известные грабли с PUT
`/api/v1/workflows/{id}` в памяти `project-n8n-vps`, они касаются
редактирования уже активных воркфлоу; для НОВОГО воркфлоу это не проблема,
но активация всё равно через UI — надёжнее и не требует создания API-ключа
с широкими правами ради разового действия).

## Шаг 4 — тест (ЭТАП 5)

1. Положить `test/source.mp4` на VPS (или его отдаст владелец боту напрямую в Telegram — тогда шаг не нужен).
2. Отправить видео новому боту от аккаунта с `ALLOWED_USER_ID`.
3. Смотреть: сработал ли триггер → создался ли GitHub Actions run → сколько
   заняла обработка → скачался ли артефакт → пришло ли видео обратно.
4. Результат зафиксировать в этом файле или в чате — что сработало, что нет.
