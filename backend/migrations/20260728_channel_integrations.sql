-- Shared Gmail and WhatsApp integration configuration.
-- Safe to run against an existing MySQL CRM database.

USE digidara_crm12;

CREATE TABLE IF NOT EXISTS integrations (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name       VARCHAR(100) NOT NULL,
    type       VARCHAR(40) NOT NULL,
    is_active  TINYINT(1) NOT NULL DEFAULT 1,
    config     JSON NOT NULL,
    agency_id  INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_integrations_agency_type (agency_id, type),
    KEY idx_integrations_type_active (type, is_active),
    KEY idx_integrations_agency (agency_id),
    CONSTRAINT chk_integrations_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Secrets are added through CRM Settings, environment variables, or the
-- production deployment process and are never committed to this migration.
INSERT IGNORE INTO integrations (name, type, is_active, config, agency_id)
VALUES
    (
        'Gmail',
        'email',
        0,
        JSON_OBJECT(
            'use_tls', TRUE,
            'smtp_host', 'smtp.gmail.com',
            'smtp_port', 587,
            'from_email', 'vini535353@gmail.com',
            'app_password', ''
        ),
        2
    ),
    (
        'WhatsApp',
        'whatsapp',
        0,
        JSON_OBJECT(
            'api_key', '',
            'api_url', 'https://graph.facebook.com/v19.0',
            'app_secret', '',
            'verify_token', '',
            'sender_number', '957554507448611',
            'template_namespace', '',
            'login_otp_template', 'staff_login_otp',
            'template_language', 'en',
            'login_otp_url_button', TRUE
        ),
        2
    );

UPDATE integrations
SET config = JSON_SET(
    config,
    '$.sender_number', '957554507448611',
    '$.login_otp_template', 'staff_login_otp',
    '$.template_language', 'en',
    '$.login_otp_url_button', TRUE
)
WHERE agency_id = 2 AND type = 'whatsapp';
