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

CALL add_column_if_missing('leads', 'ai_score_factors', 'TEXT NULL');
CALL add_column_if_missing('leads', 'ai_scored_at', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_next_best_action', 'TEXT NULL');

CREATE TABLE IF NOT EXISTS communication_summaries (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    recipient_type VARCHAR(50) NOT NULL,
    recipient_id   INT UNSIGNED NOT NULL,
    recipient_name VARCHAR(190) NULL,
    channel        VARCHAR(40) NOT NULL DEFAULT 'Mixed',
    summary_text   TEXT NOT NULL,
    key_points     TEXT NULL,
    sentiment      VARCHAR(40) NOT NULL DEFAULT 'neutral',
    next_action    TEXT NULL,
    message_count  INT NOT NULL DEFAULT 0,
    model          VARCHAR(120) NULL,
    created_by     INT UNSIGNED NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_comm_summaries_recipient (recipient_type, recipient_id),
    KEY idx_comm_summaries_channel (channel),
    KEY idx_comm_summaries_created_by (created_by),
    KEY idx_comm_summaries_created_at (created_at),
    CONSTRAINT fk_comm_summaries_created_by
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_comm_summaries_message_count CHECK (message_count >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP PROCEDURE IF EXISTS add_column_if_missing;

-- Rollback: hide the related UI/actions. Keep lead scoring columns and summaries for audit/history retention.
