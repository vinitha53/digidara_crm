-- Persistent multi-message AI Chat conversations.
-- Upgrade-safe and safe to rerun against an existing MySQL CRM database.

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
        SET @ddl = CONCAT(
            'ALTER TABLE `', table_name_in, '` ADD COLUMN `',
            column_name_in, '` ', column_definition_in
        );
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

CALL add_column_if_missing('ai_interactions', 'conversation_id', 'VARCHAR(64) NULL AFTER `user_id`');
CALL add_column_if_missing('ai_interactions', 'conversation_title', 'VARCHAR(160) NULL AFTER `conversation_id`');

UPDATE ai_interactions
SET conversation_id = CONCAT('legacy-', id),
    conversation_title = LEFT(TRIM(prompt), 80)
WHERE conversation_id IS NULL OR conversation_id = '';

CALL add_index_if_missing(
    'ai_interactions',
    'idx_ai_interactions_conversation',
    'ALTER TABLE `ai_interactions` ADD KEY `idx_ai_interactions_conversation` (`user_id`, `conversation_id`, `created_at`)'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_column_if_missing;
