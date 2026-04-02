# MILA-AI Telegram Integration Runbook

## 1. Required env
Set these in `.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_BOT_USERNAME`
- `OPENCLAW_BASE_URL`
- `OPENCLAW_CHAT_PATH`
- `OPENCLAW_HEALTH_PATH`
- `OPENCLAW_GATEWAY_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_ANON_KEY`

Optional test fallback:

- `ENABLE_TEST_EMPLOYEE_FALLBACK=true`
- `TEST_COMPANY_ID=<uuid>`

## 2. Database migration
Run:

```sql
\i sql/migrations/2026-04-01_telegram_channel.sql
```

Or execute the file in Supabase SQL editor.

## 3. Start API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 4. Expose a public HTTPS URL
Telegram webhooks require public HTTPS. Example with ngrok:

```bash
ngrok http 8000
```

Assume this gives:

`https://example-public.ngrok-free.app`

## 5. Register Telegram webhook

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://example-public.ngrok-free.app/webhook/telegram\",\"secret_token\":\"<TELEGRAM_WEBHOOK_SECRET>\"}"
```

## 6. Verify webhook

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

You should see your webhook URL and no recent error.

## 7. Seed employee mapping (recommended)
Map `chat.id` to an employee:

```sql
update employees
set telegram_chat_id = '<chat_id>'
where id = '<employee_uuid>';
```

If missing and `ENABLE_TEST_EMPLOYEE_FALLBACK=true`, the gateway can auto-create a test employee when `TEST_COMPANY_ID` is set.

## 8. Start conversation
Open:

`https://t.me/beyondElevationbot`

Send:

- `/start`
- or `Hello`

Expected loop:

Telegram -> `/webhook/telegram` -> normalize -> gateway -> OpenClaw -> delivery_service -> Telegram reply.
# MILA-AI
