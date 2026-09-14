# video-editor-pipeline

Автоматизированный монтаж видео: Telegram → n8n → GitHub Actions (тяжёлая обработка, бесплатный раннер) → Telegram.

## Как это работает

1. Владелец бота присылает видео в Telegram (лимит: 5 минут).
2. n8n получает `file_id`, строит временную ссылку через Telegram File API (`https://api.telegram.org/file/bot<TOKEN>/<file_path>`, живёт, пока жив файл на серверах Telegram).
3. n8n дёргает `POST /repos/{owner}/{repo}/dispatches` (`event_type: process-video`) с этой ссылкой в `client_payload.video_url`.
4. GitHub Actions скачивает видео, делает транскрипцию (faster-whisper), режет паузы >0.4с и слова-паразиты, кадрирует в 9:16 по лицу, накладывает субтитры, лёгкую цветокоррекцию — и кладёт результат в `actions/upload-artifact` (retention 1 день).
5. n8n поллит статус run, затем скачивает артефакт через Artifacts API и отправляет видео обратно в Telegram.

## Ограничения

- Видео длиннее 5 минут отклоняются на этапе n8n (до диспатча).
- Раннер GitHub Actions даёт ~6 часов и стандартные ресурсы (2 CPU, 7 GB RAM) — для видео длиннее нескольких минут whisper+ffmpeg могут не уложиться в разумное время. Не предназначено для коммерческого/постоянного объёма — CI не является видеосервисом по ToS GitHub.
- Артефакт хранится 1 день — если n8n не успел скачать (сеть легла), результат теряется безвозвратно.
- Публичный репозиторий: `client_payload.video_url` виден в логах Actions run (если run сделать публичным) — ссылка на Telegram File API содержит токен бота в пути. **Runs должны быть недоступны публично либо ссылка не должна течь в логи** — см. `edit-video.yml`, где `video_url` не печатается в `run:`-шагах напрямую.

## Переменные окружения (на VPS, в n8n)

- `GITHUB_TOKEN` — Personal Access Token с правами `repo` (для dispatch + чтения runs/artifacts). НЕ `workflow` — этот scope нужен только для пуша самого yml-файла, не для рантайм-вызовов.
- `TELEGRAM_BOT_TOKEN` — токен бота.
- `ALLOWED_USER_ID` — Telegram user_id владельца; все прочие отправители игнорируются.
