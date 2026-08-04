# Safe API Push Deployment

Use this production setup when the CRM is deployed on one domain and lead sources live on other domains.

## Production Flow

```text
WhatsApp bot / website form / chatbot
        |
        | signed HTTPS POST
        v
https://digidaralms.com/api/integrations/leads
        |
        v
CRM leads table
        |
        v
Lead Dashboard
```

The external apps do not need CRM database credentials. They only need the CRM API URL and shared integration secrets.

If you temporarily need CRM to pull from an existing website database instead, configure `WEBSITE_DB_*` and use `/api/external-sources/sync-website-leads`. API push is still the preferred production method.

## CRM Server Environment

Set these on the CRM backend server:

```env
CRM_INTEGRATION_API_KEY=replace-with-long-random-secret
CRM_INTEGRATION_SIGNING_SECRET=replace-with-different-long-random-secret
INTEGRATION_ALLOWED_SOURCES=whatsapp,chatbot,website
```

Keep these secrets private. Use HTTPS only in production.

## External App Environment

Set these on each external app server:

```env
CRM_API_URL=https://digidaralms.com/api/integrations/leads
CRM_INTEGRATION_API_KEY=replace-with-long-random-secret
CRM_INTEGRATION_SIGNING_SECRET=replace-with-different-long-random-secret
```

Use the exact same API key and signing secret configured on the CRM server.

## Payload Fields

Minimum required:

```json
{
  "source_system": "whatsapp",
  "external_id": "wa_919876543210_20260722_103000",
  "name": "Priya",
  "phone": "919876543210",
  "service": "GenAI Course"
}
```

Recommended full payload:

```json
{
  "source_system": "website",
  "external_id": "web_enquiry_12345",
  "external_created_at": "2026-07-22T10:30:00Z",
  "name": "Priya",
  "phone": "919876543210",
  "email": "priya@example.com",
  "lead_category": "course",
  "course_name": "GenAI Course",
  "message": "Interested in course details",
  "city": "Coimbatore"
}
```

Supported `source_system` values:

- `whatsapp`
- `chatbot`
- `website`

Supported `lead_category` values:

- `course`
- `internship`
- `business`

## Python Sender Example

Use this in the WhatsApp bot app.

```python
import hashlib
import hmac
import json
import os
import time

import requests


CRM_API_URL = os.environ["CRM_API_URL"]
CRM_API_KEY = os.environ["CRM_INTEGRATION_API_KEY"]
CRM_SIGNING_SECRET = os.environ["CRM_INTEGRATION_SIGNING_SECRET"]


def push_lead_to_crm(lead):
    body = json.dumps(lead, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        CRM_SIGNING_SECRET.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    response = requests.post(
        CRM_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-CRM-API-Key": CRM_API_KEY,
            "X-CRM-Timestamp": timestamp,
            "X-CRM-Signature": signature,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


push_lead_to_crm({
    "source_system": "whatsapp",
    "external_id": "wa_919876543210_20260722_103000",
    "external_created_at": "2026-07-22T10:30:00Z",
    "name": "Priya",
    "phone": "919876543210",
    "lead_category": "course",
    "course_name": "GenAI Course",
    "message": "Interested in course details",
})
```

## PHP Sender Example

Use this in a PHP website enquiry form.

```php
<?php

$crmApiUrl = getenv('CRM_API_URL');
$crmApiKey = getenv('CRM_INTEGRATION_API_KEY');
$crmSigningSecret = getenv('CRM_INTEGRATION_SIGNING_SECRET');

$lead = [
    'source_system' => 'website',
    'external_id' => 'web_enquiry_' . time(),
    'external_created_at' => gmdate('c'),
    'name' => $_POST['name'] ?? 'Website Visitor',
    'phone' => $_POST['phone'] ?? '',
    'email' => $_POST['email'] ?? '',
    'lead_category' => $_POST['lead_category'] ?? 'course',
    'course_name' => $_POST['course_name'] ?? '',
    'message' => $_POST['message'] ?? '',
];

$body = json_encode($lead, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
$timestamp = (string) time();
$signature = hash_hmac('sha256', $timestamp . '.' . $body, $crmSigningSecret);

$ch = curl_init($crmApiUrl);
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => [
        'Content-Type: application/json',
        'X-CRM-API-Key: ' . $crmApiKey,
        'X-CRM-Timestamp: ' . $timestamp,
        'X-CRM-Signature: ' . $signature,
    ],
    CURLOPT_POSTFIELDS => $body,
    CURLOPT_TIMEOUT => 15,
]);

$result = curl_exec($ch);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
if ($result === false || $status >= 400) {
    error_log('CRM lead push failed: ' . curl_error($ch) . ' response=' . $result);
}
curl_close($ch);
```

## Test Checklist

1. Deploy CRM backend with `CRM_INTEGRATION_API_KEY` and `CRM_INTEGRATION_SIGNING_SECRET`.
2. Confirm `https://digidaralms.com/api/health` works.
3. Add the same secrets to the WhatsApp bot and website app.
4. Submit one WhatsApp test lead and one website test enquiry.
5. In CRM, open `/leads?source=whatsapp` and `/leads?source=website`.
6. Check Lead Dashboard totals and Source Effectiveness.

## Security Notes

- Do not expose MySQL ports publicly.
- Do not send database passwords to the CRM when using API push.
- Rotate API secrets if they are shared accidentally.
- Use one stable `external_id` per source record to prevent duplicates.
- If a request fails, retry with the same `external_id`.
