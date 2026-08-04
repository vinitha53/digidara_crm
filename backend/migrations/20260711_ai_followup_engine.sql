USE digidara_crm12;

DROP PROCEDURE IF EXISTS add_column_if_missing;
DELIMITER //
CREATE PROCEDURE add_column_if_missing(
    IN table_name_in VARCHAR(64),
    IN column_name_in VARCHAR(64),
    IN column_definition_in TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_in
          AND COLUMN_NAME = column_name_in
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', table_name_in, '` ADD COLUMN `', column_name_in, '` ', column_definition_in);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

DROP PROCEDURE IF EXISTS add_index_if_missing;
DELIMITER //
CREATE PROCEDURE add_index_if_missing(
    IN table_name_in VARCHAR(64),
    IN index_name_in VARCHAR(64),
    IN index_ddl_in TEXT
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_in
          AND INDEX_NAME = index_name_in
    ) THEN
        SET @ddl = index_ddl_in;
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

DROP PROCEDURE IF EXISTS sync_leads_status_check;
DELIMITER //
CREATE PROCEDURE sync_leads_status_check()
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'leads'
          AND CONSTRAINT_TYPE = 'CHECK'
          AND CONSTRAINT_NAME = 'chk_leads_status'
    ) THEN
        ALTER TABLE leads DROP CHECK chk_leads_status;
    END IF;

    ALTER TABLE leads ADD CONSTRAINT chk_leads_status
        CHECK (status IN ('new', 'contacted', 'qualified', 'won', 'lost', 'converted', 'closed', 'not_interested'));
END//
DELIMITER ;

CALL add_column_if_missing('leads', 'ai_followup_enabled', 'TINYINT(1) NOT NULL DEFAULT 1');
CALL add_column_if_missing('leads', 'ai_followup_paused_reason', 'VARCHAR(255) NULL');
CALL add_column_if_missing('leads', 'ai_preferred_channel', 'VARCHAR(40) NULL');
CALL add_column_if_missing('leads', 'ai_last_followup_at', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_next_followup_at', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_followup_count', 'INT NOT NULL DEFAULT 0');
CALL add_column_if_missing('leads', 'ai_engagement_score', 'TINYINT UNSIGNED NOT NULL DEFAULT 0');
CALL add_column_if_missing('leads', 'ai_followup_outcome', 'VARCHAR(80) NULL');

CALL add_column_if_missing('company_settings', 'ai_followups_enabled', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_column_if_missing('company_settings', 'ai_followup_hot_interval_days', 'INT NOT NULL DEFAULT 2');
CALL add_column_if_missing('company_settings', 'ai_followup_warm_interval_days', 'INT NOT NULL DEFAULT 4');
CALL add_column_if_missing('company_settings', 'ai_followup_cold_interval_days', 'INT NOT NULL DEFAULT 5');
CALL add_column_if_missing('company_settings', 'ai_followup_business_hours', 'VARCHAR(40) NOT NULL DEFAULT ''09:00-18:00''');
CALL add_column_if_missing('company_settings', 'ai_followup_working_days', 'VARCHAR(80) NOT NULL DEFAULT ''Mon,Tue,Wed,Thu,Fri,Sat''');
CALL add_column_if_missing('company_settings', 'ai_followup_max_count', 'INT NOT NULL DEFAULT 6');
CALL add_column_if_missing('company_settings', 'ai_followup_stop_after_no_response', 'INT NOT NULL DEFAULT 4');
CALL add_column_if_missing('company_settings', 'ai_followup_preferred_channel', 'VARCHAR(40) NOT NULL DEFAULT ''WhatsApp''');
CALL add_column_if_missing('company_settings', 'ai_followup_llm_model', 'VARCHAR(120) NOT NULL DEFAULT ''llama3-8b-8192''');

CALL add_index_if_missing(
    'leads',
    'idx_leads_ai_next_followup',
    'ALTER TABLE `leads` ADD KEY `idx_leads_ai_next_followup` (`ai_next_followup_at`)'
);

CALL sync_leads_status_check();

CREATE TABLE IF NOT EXISTS ai_followup_history (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    lead_id           INT UNSIGNED NOT NULL,
    user_id           INT UNSIGNED NULL,
    channel           VARCHAR(40) NOT NULL DEFAULT 'WhatsApp',
    message_type      VARCHAR(80) NOT NULL DEFAULT 'follow_up',
    generated_message TEXT NULL,
    edited_message    TEXT NULL,
    status            VARCHAR(40) NOT NULL DEFAULT 'generated',
    delivery_status   VARCHAR(40) NOT NULL DEFAULT 'pending',
    skip_reason       TEXT NULL,
    outcome           VARCHAR(80) NULL,
    scheduled_for     DATETIME NULL,
    sent_at           DATETIME NULL,
    idempotency_key   VARCHAR(190) NOT NULL,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ai_followup_idempotency (idempotency_key),
    KEY idx_ai_followup_lead (lead_id),
    KEY idx_ai_followup_status (status),
    KEY idx_ai_followup_scheduled (scheduled_for),
    CONSTRAINT fk_ai_followup_lead FOREIGN KEY (lead_id) REFERENCES leads(id) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ai_followup_user FOREIGN KEY (user_id) REFERENCES users(id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_ai_followup_status CHECK (status IN ('generated', 'sent', 'failed', 'skipped', 'paused', 'manual')),
    CONSTRAINT chk_ai_followup_delivery CHECK (delivery_status IN ('pending', 'sent', 'failed', 'skipped'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_followup_prompt_logs (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    followup_id  INT UNSIGNED NULL,
    lead_id      INT UNSIGNED NOT NULL,
    model        VARCHAR(120) NULL,
    prompt       LONGTEXT NOT NULL,
    response     LONGTEXT NULL,
    status       VARCHAR(40) NOT NULL DEFAULT 'success',
    error        TEXT NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_ai_prompt_followup (followup_id),
    KEY idx_ai_prompt_lead (lead_id),
    CONSTRAINT fk_ai_prompt_followup FOREIGN KEY (followup_id) REFERENCES ai_followup_history(id) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_ai_prompt_lead FOREIGN KEY (lead_id) REFERENCES leads(id) ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Rollback: disable AI follow-ups in Settings, keep additive columns/tables for audit retention.
DROP PROCEDURE IF EXISTS sync_leads_status_check;
DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_column_if_missing;
