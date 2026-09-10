-- Production-safe WhatsApp campaign upgrade. Back up the database, select the
-- CRM schema, then run this file once before deploying the new backend.
SET NAMES utf8mb4;

DELIMITER $$
DROP PROCEDURE IF EXISTS campaign_add_column_if_missing$$
CREATE PROCEDURE campaign_add_column_if_missing(IN table_name_value VARCHAR(64), IN column_name_value VARCHAR(64), IN column_definition TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_value AND COLUMN_NAME = column_name_value
    ) THEN
        SET @statement = CONCAT('ALTER TABLE `', table_name_value, '` ADD COLUMN `', column_name_value, '` ', column_definition);
        PREPARE prepared_statement FROM @statement;
        EXECUTE prepared_statement;
        DEALLOCATE PREPARE prepared_statement;
    END IF;
END$$

DROP PROCEDURE IF EXISTS campaign_drop_check_if_exists$$
CREATE PROCEDURE campaign_drop_check_if_exists(IN table_name_value VARCHAR(64), IN constraint_name_value VARCHAR(64))
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = table_name_value AND CONSTRAINT_NAME = constraint_name_value AND CONSTRAINT_TYPE = 'CHECK'
    ) THEN
        SET @statement = CONCAT('ALTER TABLE `', table_name_value, '` DROP CHECK `', constraint_name_value, '`');
        PREPARE prepared_statement FROM @statement;
        EXECUTE prepared_statement;
        DEALLOCATE PREPARE prepared_statement;
    END IF;
END$$

DROP PROCEDURE IF EXISTS campaign_add_index_if_missing$$
CREATE PROCEDURE campaign_add_index_if_missing(IN table_name_value VARCHAR(64), IN index_name_value VARCHAR(64), IN index_columns TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_value AND INDEX_NAME = index_name_value
    ) THEN
        SET @statement = CONCAT('CREATE INDEX `', index_name_value, '` ON `', table_name_value, '` ', index_columns);
        PREPARE prepared_statement FROM @statement;
        EXECUTE prepared_statement;
        DEALLOCATE PREPARE prepared_statement;
    END IF;
END$$
DELIMITER ;

CALL campaign_add_column_if_missing('leads', 'destination', 'VARCHAR(190) NULL');
CALL campaign_add_column_if_missing('leads', 'travel_date', 'DATE NULL');
CALL campaign_add_column_if_missing('leads', 'marketing_opt_in', 'TINYINT(1) NULL');
CALL campaign_add_column_if_missing('leads', 'marketing_opt_in_at', 'DATETIME NULL');
CALL campaign_add_column_if_missing('leads', 'marketing_opt_in_source', 'VARCHAR(80) NULL');
CALL campaign_add_column_if_missing('leads', 'whatsapp_opt_in', 'TINYINT(1) NULL');
CALL campaign_add_column_if_missing('leads', 'opted_out', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('leads', 'opted_out_at', 'DATETIME NULL');
CALL campaign_add_column_if_missing('leads', 'opted_out_reason', 'VARCHAR(255) NULL');
CALL campaign_add_column_if_missing('leads', 'last_marketing_message_at', 'DATETIME NULL');

CALL campaign_add_column_if_missing('campaigns', 'agency_id', 'INT NULL');
CALL campaign_add_column_if_missing('campaigns', 'template_name', 'VARCHAR(190) NULL');
CALL campaign_add_column_if_missing('campaigns', 'template_language', 'VARCHAR(40) NULL');
CALL campaign_add_column_if_missing('campaigns', 'template_category', 'VARCHAR(40) NULL');
CALL campaign_add_column_if_missing('campaigns', 'template_snapshot', 'JSON NULL');
CALL campaign_add_column_if_missing('campaigns', 'variable_mapping', 'JSON NULL');
CALL campaign_add_column_if_missing('campaigns', 'header_type', 'VARCHAR(40) NULL');
CALL campaign_add_column_if_missing('campaigns', 'media_id', 'VARCHAR(190) NULL');
CALL campaign_add_column_if_missing('campaigns', 'media_filename', 'VARCHAR(255) NULL');
CALL campaign_add_column_if_missing('campaigns', 'audience_type', 'VARCHAR(40) NOT NULL DEFAULT ''all''');
CALL campaign_add_column_if_missing('campaigns', 'audience_filter', 'JSON NULL');
CALL campaign_add_column_if_missing('campaigns', 'audience_snapshot', 'JSON NULL');
CALL campaign_add_column_if_missing('campaigns', 'started_at', 'DATETIME NULL');
CALL campaign_add_column_if_missing('campaigns', 'completed_at', 'DATETIME NULL');
CALL campaign_add_column_if_missing('campaigns', 'paused_at', 'DATETIME NULL');
CALL campaign_add_column_if_missing('campaigns', 'cancelled_at', 'DATETIME NULL');
CALL campaign_add_column_if_missing('campaigns', 'total_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'eligible_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'queued_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'delivered_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'read_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'replied_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'failed_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'skipped_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'opted_out_count', 'INT NOT NULL DEFAULT 0');
CALL campaign_add_column_if_missing('campaigns', 'updated_at', 'DATETIME NULL');

CALL campaign_drop_check_if_exists('campaigns', 'chk_campaigns_status');
ALTER TABLE campaigns ADD CONSTRAINT chk_campaigns_status CHECK (status IN ('draft', 'validated', 'scheduled', 'queued', 'sending', 'paused', 'completed', 'cancelled', 'failed', 'sent'));

CREATE TABLE IF NOT EXISTS campaign_recipients (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    agency_id INT NULL,
    campaign_id INT UNSIGNED NOT NULL,
    lead_id INT UNSIGNED NULL,
    customer_id INT UNSIGNED NULL,
    recipient_name VARCHAR(190) NULL,
    recipient_phone VARCHAR(40) NULL,
    normalized_phone VARCHAR(32) NOT NULL,
    rendered_variables JSON NULL,
    provider_message_id VARCHAR(190) NULL,
    provider_response LONGTEXT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'queued',
    skip_reason TEXT NULL,
    error_code VARCHAR(80) NULL,
    error_message TEXT NULL,
    queued_at DATETIME NULL,
    sending_at DATETIME NULL,
    accepted_at DATETIME NULL,
    sent_at DATETIME NULL,
    delivered_at DATETIME NULL,
    read_at DATETIME NULL,
    replied_at DATETIME NULL,
    last_event_at DATETIME NULL,
    reply_count INT NOT NULL DEFAULT 0,
    last_reply_text TEXT NULL,
    last_reply_at DATETIME NULL,
    retry_count INT NOT NULL DEFAULT 0,
    next_retry_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_campaign_recipient_phone (campaign_id, normalized_phone),
    UNIQUE KEY uq_campaign_recipient_provider (provider_message_id),
    KEY idx_campaign_recipients_agency (agency_id),
    KEY idx_campaign_recipients_campaign (campaign_id),
    KEY idx_campaign_recipients_lead (lead_id),
    KEY idx_campaign_recipients_status (status),
    KEY idx_campaign_recipients_provider (provider_message_id),
    CONSTRAINT fk_campaign_recipients_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_campaign_recipients_lead FOREIGN KEY (lead_id) REFERENCES leads(id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_campaign_recipients_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS whatsapp_templates (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    agency_id INT NULL,
    meta_template_id VARCHAR(190) NOT NULL,
    name VARCHAR(190) NOT NULL,
    language VARCHAR(40) NOT NULL,
    category VARCHAR(40) NULL,
    status VARCHAR(40) NOT NULL,
    components JSON NOT NULL,
    header_type VARCHAR(40) NULL,
    body_text TEXT NULL,
    footer_text TEXT NULL,
    buttons JSON NULL,
    last_synced_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_whatsapp_template_agency_meta (agency_id, meta_template_id),
    KEY idx_whatsapp_templates_agency (agency_id),
    KEY idx_whatsapp_templates_name (name),
    KEY idx_whatsapp_templates_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS message_events (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    agency_id INT NULL,
    provider_message_id VARCHAR(190) NULL,
    campaign_recipient_id INT UNSIGNED NULL,
    event_type VARCHAR(40) NOT NULL,
    event_timestamp DATETIME NULL,
    raw_event JSON NULL,
    event_hash CHAR(64) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_message_events_hash (event_hash),
    KEY idx_message_events_agency (agency_id),
    KEY idx_message_events_provider (provider_message_id),
    KEY idx_message_events_recipient (campaign_recipient_id),
    KEY idx_message_events_type (event_type),
    CONSTRAINT fk_message_events_recipient FOREIGN KEY (campaign_recipient_id) REFERENCES campaign_recipients(id) ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL campaign_add_index_if_missing('campaigns', 'idx_campaigns_agency', '(agency_id)');

INSERT IGNORE INTO role_permissions (role, page_key, action, allowed)
VALUES
    ('admin', 'campaigns', 'pause', 1),
    ('admin', 'campaigns', 'cancel', 1),
    ('admin', 'campaigns', 'export', 1),
    ('admin', 'campaigns', 'manage_templates', 1),
    ('staff', 'campaigns', 'pause', 0),
    ('staff', 'campaigns', 'cancel', 0),
    ('staff', 'campaigns', 'export', 0),
    ('staff', 'campaigns', 'manage_templates', 0);

DROP PROCEDURE IF EXISTS campaign_add_index_if_missing;
DROP PROCEDURE IF EXISTS campaign_drop_check_if_exists;
DROP PROCEDURE IF EXISTS campaign_add_column_if_missing;
