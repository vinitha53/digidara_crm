-- Two-step CRM login using the approved WhatsApp template staff_login_otp.
-- Safe to run against an existing MySQL CRM database.

USE digidara_crm12;

CREATE TABLE IF NOT EXISTS login_otp_challenges (
    id           VARCHAR(36) NOT NULL,
    user_id      INT UNSIGNED NOT NULL,
    otp_hash     CHAR(64) NOT NULL,
    expires_at   DATETIME NOT NULL,
    attempts     TINYINT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts TINYINT UNSIGNED NOT NULL DEFAULT 5,
    last_sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    send_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    meta_message_id VARCHAR(190) NULL,
    consumed_at  DATETIME NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_login_otp_user_created (user_id, created_at),
    KEY idx_login_otp_expires (expires_at),
    KEY idx_login_otp_delivery (delivery_status, created_at),
    CONSTRAINT fk_login_otp_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_login_otp_attempts CHECK (attempts <= max_attempts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

CALL add_column_if_missing('users', 'phone', 'VARCHAR(40) NULL');
CALL add_column_if_missing('users', 'otp_secret', 'VARCHAR(255) NULL');
CALL add_column_if_missing('users', 'otp_enabled', 'TINYINT(1) NOT NULL DEFAULT 1');

ALTER TABLE users
    MODIFY COLUMN otp_enabled TINYINT(1) NOT NULL DEFAULT 1;

UPDATE users
SET phone = '+916369979579', otp_enabled = 1
WHERE id = 1 OR login_id = 'admin' OR email = 'admin@digidaratechnologies.com';

UPDATE users
SET otp_enabled = 1
WHERE is_active = 1 AND phone IS NOT NULL AND phone != '';

DROP PROCEDURE IF EXISTS add_column_if_missing;
