-- OTP delivery audit fields used by duplicate-send protection.
-- Safe to run against an existing MySQL CRM database.

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

CALL add_column_if_missing(
    'login_otp_challenges',
    'send_attempts',
    'SMALLINT UNSIGNED NOT NULL DEFAULT 0'
);
CALL add_column_if_missing(
    'login_otp_challenges',
    'delivery_status',
    'VARCHAR(20) NOT NULL DEFAULT ''pending'''
);
CALL add_column_if_missing(
    'login_otp_challenges',
    'meta_message_id',
    'VARCHAR(190) NULL'
);
CALL add_index_if_missing(
    'login_otp_challenges',
    'idx_login_otp_delivery',
    'ALTER TABLE `login_otp_challenges` ADD KEY `idx_login_otp_delivery` (`delivery_status`, `created_at`)'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_column_if_missing;
