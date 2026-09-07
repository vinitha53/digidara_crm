USE digidara_crm12;

DROP PROCEDURE IF EXISTS add_column_if_missing;
DELIMITER //
CREATE PROCEDURE add_column_if_missing(IN table_name_in VARCHAR(64), IN column_name_in VARCHAR(64), IN definition_in TEXT)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_in AND COLUMN_NAME = column_name_in) THEN
        SET @ddl = CONCAT('ALTER TABLE `', table_name_in, '` ADD COLUMN `', column_name_in, '` ', definition_in);
        PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

DROP PROCEDURE IF EXISTS add_index_if_missing;
DELIMITER //
CREATE PROCEDURE add_index_if_missing(IN table_name_in VARCHAR(64), IN index_name_in VARCHAR(64), IN ddl_in TEXT)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_in AND INDEX_NAME = index_name_in) THEN
        SET @ddl = ddl_in; PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

CALL add_column_if_missing('leads', 'ai_followup_stop_reason', 'TEXT NULL');
CALL add_column_if_missing('leads', 'ai_followup_stopped_at', 'DATETIME NULL');
CALL add_column_if_missing('ai_followup_history', 'final_message', 'TEXT NULL');
CALL add_column_if_missing('ai_followup_history', 'sequence_step', 'INT NULL');
CALL add_column_if_missing('ai_followup_history', 'temperature_snapshot', 'VARCHAR(30) NULL');
CALL add_column_if_missing('ai_followup_history', 'recipient_phone', 'VARCHAR(40) NULL');
CALL add_column_if_missing('ai_followup_history', 'original_phone', 'VARCHAR(40) NULL');
CALL add_column_if_missing('ai_followup_history', 'template_id', 'INT UNSIGNED NULL');
CALL add_column_if_missing('ai_followup_history', 'template_text', 'TEXT NULL');
CALL add_column_if_missing('ai_followup_history', 'generated_at', 'DATETIME NULL');
CALL add_column_if_missing('ai_followup_history', 'stopped_at', 'DATETIME NULL');
CALL add_column_if_missing('ai_followup_history', 'stopped_reason', 'TEXT NULL');
CALL add_column_if_missing('ai_followup_history', 'provider_message_id', 'VARCHAR(190) NULL');
CALL add_column_if_missing('ai_followup_history', 'provider_status', 'VARCHAR(40) NULL');
CALL add_column_if_missing('ai_followup_history', 'provider_response', 'LONGTEXT NULL');
CALL add_column_if_missing('ai_followup_history', 'provider_error', 'TEXT NULL');
CALL add_column_if_missing('ai_followup_history', 'automation_mode', 'VARCHAR(30) NOT NULL DEFAULT ''automatic''');
CALL add_column_if_missing('ai_followup_history', 'response_received_at', 'DATETIME NULL');
CALL add_column_if_missing('ai_followup_history', 'claimed_at', 'DATETIME NULL');
CALL add_column_if_missing('message_logs', 'recipient_phone', 'VARCHAR(40) NULL');
CALL add_column_if_missing('message_logs', 'provider_message_id', 'VARCHAR(190) NULL');
CALL add_column_if_missing('message_logs', 'provider_status', 'VARCHAR(40) NULL');
CALL add_column_if_missing('message_logs', 'provider_response', 'LONGTEXT NULL');
CALL add_column_if_missing('message_logs', 'error_message', 'TEXT NULL');
CALL add_column_if_missing('message_logs', 'followup_id', 'INT UNSIGNED NULL');

DROP PROCEDURE IF EXISTS replace_followup_checks;
DELIMITER //
CREATE PROCEDURE replace_followup_checks()
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_followup_history' AND CONSTRAINT_NAME = 'chk_ai_followup_status') THEN
        ALTER TABLE ai_followup_history DROP CHECK chk_ai_followup_status;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_followup_history' AND CONSTRAINT_NAME = 'chk_ai_followup_delivery') THEN
        ALTER TABLE ai_followup_history DROP CHECK chk_ai_followup_delivery;
    END IF;
    ALTER TABLE ai_followup_history ADD CONSTRAINT chk_ai_followup_status CHECK (status IN ('generated','pending','sent','delivered','read','failed','skipped','paused','manual','stopped','cancelled'));
    ALTER TABLE ai_followup_history ADD CONSTRAINT chk_ai_followup_delivery CHECK (delivery_status IN ('pending','accepted','sent','delivered','read','failed','skipped','stopped','cancelled'));
END//
DELIMITER ;
CALL replace_followup_checks();
DROP PROCEDURE IF EXISTS replace_followup_checks;

CREATE TABLE IF NOT EXISTS ai_followup_templates (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    temperature VARCHAR(30) NOT NULL,
    sequence_step INT NOT NULL,
    template_body TEXT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    description TEXT NULL,
    created_by INT UNSIGNED NULL,
    updated_by INT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ai_followup_template_step (temperature, sequence_step),
    KEY idx_ai_followup_template_active (temperature, is_active),
    CONSTRAINT fk_ai_template_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_ai_template_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT chk_ai_template_temperature CHECK (temperature IN ('hot', 'warm')),
    CONSTRAINT chk_ai_template_step CHECK (sequence_step BETWEEN 1 AND 10)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO ai_followup_templates (temperature, sequence_step, template_body, description) VALUES
('hot',1,'Hi {lead_name}, thanks for your interest in {service}. Would you like help with the next step?','Hot sequence message 1'),
('hot',2,'Hi {lead_name}, I’m following up on {service}. Is there anything you would like us to clarify?','Hot sequence message 2'),
('hot',3,'Hello {lead_name}, would a quick conversation help you decide how to proceed with {service}?','Hot sequence message 3'),
('hot',4,'Hi {lead_name}, we’re available to answer your questions about {service}. What would be most useful?','Hot sequence message 4'),
('hot',5,'Hello {lead_name}, checking whether you would like to continue with {service}. I can help with the next step.','Hot sequence message 5'),
('hot',6,'Hi {lead_name}, is {service} still a priority for you? Let us know how we can assist.','Hot sequence message 6'),
('hot',7,'Hello {lead_name}, I wanted to make sure you have the information you need about {service}.','Hot sequence message 7'),
('hot',8,'Hi {lead_name}, we’re ready to help whenever you want to move forward with {service}.','Hot sequence message 8'),
('hot',9,'Hello {lead_name}, would you like us to arrange the next step for your {service} enquiry?','Hot sequence message 9'),
('hot',10,'Hi {lead_name}, this is our final scheduled follow-up about {service}. Reply anytime if you would like assistance.','Hot sequence message 10'),
('warm',1,'Hi {lead_name}, thank you for considering {service}. Would you like more information?','Warm sequence message 1'),
('warm',2,'Hello {lead_name}, I’m checking in about your interest in {service}. How can we help?','Warm sequence message 2'),
('warm',3,'Hi {lead_name}, do you have any questions about {service} that we can answer?','Warm sequence message 3'),
('warm',4,'Hello {lead_name}, when the time is right, we can guide you through the next step for {service}.','Warm sequence message 4'),
('warm',5,'Hi {lead_name}, I wanted to keep your {service} enquiry moving. What information would help?','Warm sequence message 5'),
('warm',6,'Hello {lead_name}, are you still exploring {service}? Our team is available to assist.','Warm sequence message 6'),
('warm',7,'Hi {lead_name}, we can help you evaluate the next step for {service} whenever convenient.','Warm sequence message 7'),
('warm',8,'Hello {lead_name}, checking whether you need any clarification regarding {service}.','Warm sequence message 8'),
('warm',9,'Hi {lead_name}, would you like to reconnect with our team about {service}?','Warm sequence message 9'),
('warm',10,'Hello {lead_name}, this is our final scheduled check-in about {service}. You’re welcome to reply anytime.','Warm sequence message 10');

CALL add_index_if_missing('ai_followup_history', 'idx_ai_followup_sequence', 'ALTER TABLE ai_followup_history ADD KEY idx_ai_followup_sequence (temperature_snapshot, sequence_step)');
CALL add_index_if_missing('ai_followup_history', 'idx_ai_followup_recipient', 'ALTER TABLE ai_followup_history ADD KEY idx_ai_followup_recipient (recipient_phone)');
CALL add_index_if_missing('ai_followup_history', 'idx_ai_followup_provider_message', 'ALTER TABLE ai_followup_history ADD KEY idx_ai_followup_provider_message (provider_message_id)');
CALL add_index_if_missing('message_logs', 'idx_message_logs_followup', 'ALTER TABLE message_logs ADD KEY idx_message_logs_followup (followup_id)');

UPDATE company_settings SET ai_followup_max_count = 10 WHERE ai_followup_max_count IS NULL OR ai_followup_max_count = 6;
UPDATE company_settings SET ai_followup_stop_after_no_response = 0 WHERE ai_followup_stop_after_no_response = 4;

DROP PROCEDURE IF EXISTS add_column_if_missing;
DROP PROCEDURE IF EXISTS add_index_if_missing;
