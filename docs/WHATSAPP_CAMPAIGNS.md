# WhatsApp Campaign Management

This module sends approved Meta WhatsApp templates from the CRM, records one durable recipient row per selected lead, and updates delivery/read/reply metrics from the existing WhatsApp bot webhook. It never exposes the access token to the frontend.

## Production upgrade

1. Back up the CRM database.
2. Select the production CRM schema in MySQL/MariaDB.
3. Run `backend/migrations/20260910_whatsapp_campaign_management.sql` once.
4. Deploy the backend and frontend from the same release.
5. Start the API, campaign worker, and existing WhatsApp bot.
6. Keep `CAMPAIGN_SEND_ENABLED=0` until template sync and a test send succeed; then change it to `1` and restart only the worker.

Do not use `db.drop_all()` or reset production data. `backend/schema.sql` contains the same definitions for new installations.

## Environment variables

CRM backend and campaign worker:

```env
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_GRAPH_API_VERSION=v23.0
WHATSAPP_APP_SECRET=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
CRM_INTEGRATION_SIGNING_SECRET=
CAMPAIGN_SEND_ENABLED=0
CAMPAIGN_REQUIRE_MARKETING_CONSENT=1
CAMPAIGN_BATCH_SIZE=25
CAMPAIGN_MAX_RETRIES=3
CAMPAIGN_DELAY_MS=500
CAMPAIGN_WORKER_INTERVAL_SECONDS=5
CAMPAIGN_TEST_RECIPIENT_LIMIT=5
CAMPAIGN_QUIET_HOURS_START=22:00
CAMPAIGN_QUIET_HOURS_END=08:00
CAMPAIGN_MEDIA_MAX_BYTES=5242880
CRM_AGENCY_ID=2
```

`WHATSAPP_TOKEN` remains a backward-compatible alias for `WHATSAPP_ACCESS_TOKEN`. `PHONE_NUMBER_ID` remains a backward-compatible alias for `WHATSAPP_PHONE_NUMBER_ID`. The WABA ID can be omitted when the configured token is permitted to derive it from the Phone Number ID.

Existing WhatsApp bot:

```env
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_APP_SECRET=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
CRM_CAMPAIGN_WEBHOOK_URL=https://crm.example.com/api/campaigns/webhook-events
CRM_INTEGRATION_SIGNING_SECRET=
CRM_API_URL=https://crm.example.com/api/integrations/leads
CRM_INTEGRATION_API_KEY=
```

Use the same `CRM_INTEGRATION_SIGNING_SECRET` in the bot and CRM. Do not put real values in Git, browser configuration, screenshots, or support logs.

## Meta configuration

The Meta app/system user needs access to the configured WABA and permissions appropriate to production Cloud API use, normally `whatsapp_business_management` for template synchronization and `whatsapp_business_messaging` for sending. The selected templates must have `APPROVED` status. Marketing sends should use approved MARKETING templates; the CRM preserves the exact approved component snapshot and does not expose an editable message body.

Keep the existing bot URL as the only public Meta callback:

```text
GET/POST https://bot.example.com/webhook
```

Configure the Meta webhook verify token and App Secret in the bot environment. The bot verifies `X-Hub-Signature-256`, retains its existing chatbot behavior, and forwards the verified raw event to the CRM using a separate HMAC signature. Do not configure `/api/campaigns/webhook-events` as a Meta callback; it is an internal bot-to-CRM endpoint.

Subscribe the Meta app to WhatsApp `messages` events. Those events include outbound delivery statuses and inbound replies.

## Worker

From the backend virtual environment:

```powershell
cd backend
.\venv\Scripts\python.exe run_campaigns.py
```

Linux:

```bash
cd backend
./venv/bin/python run_campaigns.py
```

PM2 example (adjust the interpreter path and working directory):

```bash
pm2 start run_campaigns.py --name digidara-campaign-worker --interpreter ./venv/bin/python --cwd /srv/digidara/backend
pm2 save
```

The worker holds a MySQL/MariaDB advisory lock so a second worker exits instead of sending concurrently. A recipient is committed as `sending` before the network call, and provider message IDs prevent a completed send from being retried.

## Safe launch procedure

1. Record explicit marketing/WhatsApp consent on eligible leads.
2. Open Campaigns and refresh approved templates.
3. Select the audience and review every exclusion reason.
4. Choose an approved template and map every variable.
5. For IMAGE headers, upload JPG, PNG, or WEBP; the backend validates it and uploads bytes to Meta. Local paths are never sent.
6. Save a draft and perform a test send.
7. Enable the worker only after the test is received.
8. Confirm eligibility and launch or schedule.
9. Use Pause, Resume, Cancel, or Retry Failed as needed.

Opted-out leads, invalid phones, duplicate normalized phones, missing consent, and missing variable values are not queued. Incoming `STOP`, `UNSUBSCRIBE`, `REMOVE`, `CANCEL`, `NO MORE`, and `STOP ALL` replies suppress future campaigns and stop AI follow-ups.

## API

All endpoints except the internal webhook forward require JWT and campaign permissions.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/campaigns` | List scoped campaigns and actual counters |
| POST | `/api/campaigns` | Create a draft |
| GET/PUT/DELETE | `/api/campaigns/<id>` | Read, edit, or safely delete a draft/final failed campaign |
| GET | `/api/campaigns/audience` | Preview count, eligibility and exclusion reasons |
| GET | `/api/campaigns/audience/export` | Stream the filtered audience CSV |
| GET | `/api/leads/export` | Backward-compatible scoped lead CSV export |
| GET | `/api/campaigns/templates` | Read approved cached templates |
| POST | `/api/campaigns/templates/refresh` | Synchronize approved templates from Meta |
| POST | `/api/campaigns/<id>/preview` | Preview campaign and audience |
| POST | `/api/campaigns/<id>/validate` | Validate template, media, variables and eligibility |
| POST | `/api/campaigns/<id>/media` | Validate and upload an IMAGE header to Meta |
| POST | `/api/campaigns/<id>/test` | Send and track one test message |
| POST | `/api/campaigns/<id>/launch` | Snapshot and queue a confirmed campaign |
| POST | `/api/campaigns/<id>/schedule` | Snapshot and schedule a confirmed campaign |
| POST | `/api/campaigns/<id>/pause` | Pause queue processing |
| POST | `/api/campaigns/<id>/resume` | Resume queue processing |
| POST | `/api/campaigns/<id>/cancel` | Cancel unsent recipients |
| POST | `/api/campaigns/<id>/retry` | Requeue failed recipients without provider IDs |
| GET | `/api/campaigns/<id>/stats` | Actual read/reply metrics |
| GET | `/api/campaigns/<id>/recipients` | Search/filter recipient results |
| GET | `/api/campaigns/<id>/replies` | List replies and linked leads |
| GET | `/api/campaigns/<id>/export` | Stream delivery/reply CSV |
| POST | `/api/campaigns/webhook-events` | HMAC-authenticated internal event forward |

Lifecycle launch/schedule bodies must include `{"confirmed": true}`. Sending is performed by the worker, not the browser request.

## Troubleshooting

- **No templates:** confirm the WABA, token permissions, Graph API version, and Meta approval status; then Refresh Templates.
- **Campaign remains queued:** confirm the worker is running and `CAMPAIGN_SEND_ENABLED=1`; check quiet hours.
- **Consent exclusions:** record `marketing_opt_in` or `whatsapp_opt_in` with evidence/source before retrying.
- **No delivery updates:** verify the public bot callback, App Secret signature, `CRM_CAMPAIGN_WEBHOOK_URL`, and shared HMAC secret.
- **Expired token / rate limit:** the API returns Meta's sanitized error message and code. Transient worker failures use bounded exponential backoff; permanent policy errors are not retried automatically.
- **Image failure:** use a matching JPG/JPEG, PNG, or WEBP MIME type and extension within the configured byte limit.

## Scope limitation

Campaigns, recipients, templates and events are agency-ready through `CRM_AGENCY_ID`. The legacy core `leads` table has no agency column, so this release preserves existing lead authorization: admins see the existing organization scope and staff are restricted to assigned leads (with optional assigned-owner branch filtering). Full cross-agency lead isolation requires a separate, coordinated migration of all legacy CRM modules and is intentionally not claimed here.
