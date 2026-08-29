# External Lead Integration

Use this when a separate app, such as the WhatsApp bot on `digidaratechnologies.com`, needs to push enquiries into the CRM lead dashboard on another domain.

For production API-push deployment examples, see [API_PUSH_DEPLOYMENT.md](API_PUSH_DEPLOYMENT.md).

## Architecture

- CRM owns the main `leads` table and dashboard.
- WhatsApp bot, chatbot, and website forms remain separate apps/databases.
- Each external app sends a signed HTTPS request to the CRM.
- CRM creates or updates a normal lead with `source=whatsapp`, `source=chatbot`, or `source=website`.
- `source_system + external_id` prevents duplicate imports from the same external database.
- CRM classifies every new or meaningfully changed lead as `hot`, `warm`, or `cold`. Notes and the latest customer message are the primary intent signal; the score, reason, factors, next action, and scoring timestamp are stored on the lead.
- External apps must not assign the lead `tag`; CRM owns that field. If the configured LLM is unavailable, deterministic scoring stores a safe fallback result instead of losing the lead.
- The Lead Dashboard reads from the CRM `leads` table, so external contacts must be pushed by API or synced from the bot database before they appear in dashboard totals.

### Google Form registrations

The registration Google Sheet can push signed submissions to the same lead endpoint with:

```json
{
  "source_system": "google_form",
  "source": "website",
  "external_id": "google-form:<spreadsheet-id>:<sheet-id>:<row-number>",
  "name": "Priya",
  "phone": "919876543210",
  "lead_category": "course",
  "course_name": "GenAI Course"
}
```

Add `google_form` to `INTEGRATION_ALLOWED_SOURCES`. The CRM stores the acquisition source as `website`, preserves `google_form` as the external system, and uses the external ID to make retries idempotent. No leads-table migration is required.

## CRM `.env`

Set these in `backend/.env` or the hosting environment:

```env
CRM_INTEGRATION_API_KEY=your-long-random-api-key
CRM_INTEGRATION_SIGNING_SECRET=your-long-random-signing-secret
INTEGRATION_ALLOWED_SOURCES=whatsapp,chatbot,website
```

Use the same API key and signing secret in the WhatsApp bot environment.

## Endpoint

```http
POST /api/integrations/leads
X-CRM-API-Key: <CRM_INTEGRATION_API_KEY>
X-CRM-Timestamp: <unix timestamp seconds>
X-CRM-Signature: <hex hmac sha256 of "timestamp." + raw JSON body>
Content-Type: application/json
```

Example JSON:

```json
{
  "source_system": "whatsapp",
  "external_id": "wa_919876543210_2026-07-21",
  "external_created_at": "2026-07-21T10:44:00Z",
  "name": "Priya",
  "phone": "919876543210",
  "email": "priya@example.com",
  "lead_category": "course",
  "course_name": "GenAI Course",
  "message": "Interested in course details",
  "city": "Coimbatore"
}
```

## Required Credentials From WhatsApp Bot Database

For direct read-only chat history in the CRM WhatsApp Messages page:

```env
BOT_DB_HOST=
BOT_DB_PORT=3306
BOT_DB_USER=
BOT_DB_PASSWORD=
BOT_DB_NAME=
```

The bot database should allow the CRM server IP to connect, and the user should have only `SELECT` permission for the bot tables.

After these values are configured, open the CRM WhatsApp Messages page and click the sync-to-leads icon. CRM will read unique WhatsApp contacts from the bot `messages` table and create or update leads with:

- `source=whatsapp`
- `source_system=whatsapp_bot`
- `external_id=bot-whatsapp:<phone>`
- `service=WhatsApp Enquiry`

Those synced records then appear in the Lead Dashboard, source reports, and `/leads?source=whatsapp`.
The latest user message is copied into lead notes and immediately triggers reclassification when it changes.

## Website Database Pull Sync

If the website database is available to the CRM server, CRM can sync these website tables into the Lead Dashboard:

- `chat_users`
- `contact_inquiries`

Set these in the CRM backend environment:

```env
WEBSITE_DB_HOST=
WEBSITE_DB_PORT=3306
WEBSITE_DB_USER=
WEBSITE_DB_PASSWORD=
WEBSITE_DB_NAME=
```

Sync endpoint:

```http
POST /api/external-sources/sync-website-leads
Authorization: Bearer <crm-login-token>
```

The Dashboard automatically tries this sync before loading totals. If the website DB credentials are not configured, the dashboard still loads from existing CRM leads.

Mapping:

- `chat_users` becomes CRM leads with `source=chatbot`
- `contact_inquiries` becomes CRM leads with `source=website`
- Duplicate prevention uses `source_system + external_id`
- Common columns such as `name`, `phone`, `email`, `message`, `course_name`, `service`, `created_at`, and `id` are detected automatically
- Each created or meaningfully updated record is classified and stored before the sync response is returned

For lead push API:

```env
CRM_API_URL=https://your-crm-domain.com/api/integrations/leads
CRM_INTEGRATION_API_KEY=
CRM_INTEGRATION_SIGNING_SECRET=
```

## WhatsApp Lead Acknowledgement Template

Create this approved template in Meta WhatsApp Manager:

- Template name: `lead_enquiry_acknowledgement`
- Category: `UTILITY`
- Language: `English`
- Body:

```text
Hi {{1}}, thank you for your interest in {{2}}. Our Digidara team will contact you shortly with the details.
```

Variables:

- `{{1}}` = lead name
- `{{2}}` = course, internship, service, or enquiry name

CRM environment:

```env
WHATSAPP_LEAD_TEMPLATE_NAME=lead_enquiry_acknowledgement
WHATSAPP_TEMPLATE_LANGUAGE=en
```

Example message sent to a course lead:

```text
Hi Priya, thank you for your interest in GenAI Course. Our Digidara team will contact you shortly with the details.
```

## WhatsApp Customer Conversion Template

Create this approved template in Meta WhatsApp Manager for the message sent when a lead is converted to a customer:

- Template name: `customer_conversion_welcome`
- Category: `UTILITY`
- Language: `English`
- Body:

```text
Hi {{1}}, welcome to Digidara Technologies. Your enquiry for {{2}} is confirmed, and our team will share the next steps shortly.
```

Variables:

- `{{1}}` = customer name
- `{{2}}` = course, internship, service, or project name

CRM environment:

```env
WHATSAPP_CUSTOMER_TEMPLATE_NAME=customer_conversion_welcome
WHATSAPP_TEMPLATE_LANGUAGE=en
```

Example message sent after conversion:

```text
Hi Priya, welcome to Digidara Technologies. Your enquiry for GenAI Course is confirmed, and our team will share the next steps shortly.
```

## WhatsApp AI Periodic Follow-up Template

Create this approved template in Meta WhatsApp Manager for AI-generated periodic lead follow-ups:

- Template name: `ai_lead_followup_message`
- Category: `MARKETING`
- Language: `English`
- Body:

```text
Hi {{1}}, this is a quick follow-up from Digidara Technologies about {{2}}.

{{3}}

Reply here and our team will help you with the next step.
```

Variables:

- `{{1}}` = lead name
- `{{2}}` = course, internship, service, or project name
- `{{3}}` = AI-generated 2-3 line follow-up message based on past lead notes, previous messages, tasks, and CRM activity

CRM environment:

```env
WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME=ai_lead_followup_message
WHATSAPP_TEMPLATE_LANGUAGE=en
```

Example AI-generated message inside `{{3}}`:

```text
We noticed you were interested in GenAI Course and may still be comparing options.
The next batch details and guidance can be shared today if you are available.
```

Final WhatsApp message:

```text
Hi Priya, this is a quick follow-up from Digidara Technologies about GenAI Course.

We noticed you were interested in GenAI Course and may still be comparing options.
The next batch details and guidance can be shared today if you are available.

Reply here and our team will help you with the next step.
```

## WhatsApp Staff Lead Assignment Template

Create this approved template in Meta WhatsApp Manager for notifying a staff member when a lead is assigned or reassigned:

- Template name: `staff_lead_assignment`
- Category: `UTILITY`
- Language: `English`
- Body:

```text
Hello {{1}}, a new lead has been assigned to you in Digidara CRM.

Lead: {{2}}
Interest: {{3}}
Phone: {{4}}
Priority: {{5}}

Please log in to the CRM and follow up promptly.
```

Variables:

- `{{1}}` = assigned staff name
- `{{2}}` = lead name
- `{{3}}` = course, internship, service, or project interest
- `{{4}}` = lead phone number
- `{{5}}` = lead priority/tag

CRM environment:

```env
WHATSAPP_LEAD_ASSIGNMENT_TEMPLATE_NAME=staff_lead_assignment
WHATSAPP_TEMPLATE_LANGUAGE=en
```

The CRM sends this template for new assignments and reassignments. Assigning a lead to the same staff member again does not send a duplicate message. Delivery attempts are retained in the message log.
