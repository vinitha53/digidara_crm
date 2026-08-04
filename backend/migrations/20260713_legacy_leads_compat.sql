USE digidara_crm12;

DROP PROCEDURE IF EXISTS modify_column_if_exists;
DELIMITER //
CREATE PROCEDURE modify_column_if_exists(
    IN table_name_in VARCHAR(64),
    IN column_name_in VARCHAR(64),
    IN column_definition_in TEXT
)
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_in
          AND COLUMN_NAME = column_name_in
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', table_name_in, '` MODIFY COLUMN `', column_name_in, '` ', column_definition_in);
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

CALL modify_column_if_exists('leads', 'agency_id', 'INT NULL DEFAULT NULL');

DROP PROCEDURE IF EXISTS modify_column_if_exists;
