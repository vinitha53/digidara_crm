USE digidara_crm12;

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

CREATE TABLE IF NOT EXISTS workflow_rules (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name           VARCHAR(190) NOT NULL,
    description    TEXT NULL,
    entity_type    VARCHAR(40) NOT NULL DEFAULT 'lead',
    trigger_type   VARCHAR(80) NOT NULL DEFAULT 'status_changed',
    trigger_config JSON NULL,
    conditions     JSON NULL,
    actions        JSON NOT NULL,
    is_active      TINYINT(1) NOT NULL DEFAULT 1,
    created_by     INT UNSIGNED NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_workflow_rules_created_by
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_workflow_rules_entity CHECK (entity_type IN ('lead', 'task')),
    CONSTRAINT chk_workflow_rules_trigger CHECK (trigger_type IN ('status_changed')),
    CONSTRAINT chk_workflow_rules_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workflow_rule_runs (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    rule_id     INT UNSIGNED NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    entity_id   INT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL DEFAULT 'success',
    detail      TEXT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_workflow_runs_rule
        FOREIGN KEY (rule_id) REFERENCES workflow_rules(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_workflow_runs_status CHECK (status IN ('success', 'skipped', 'error'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CALL add_index_if_missing(
    'workflow_rules',
    'idx_workflow_rules_active',
    'ALTER TABLE `workflow_rules` ADD KEY `idx_workflow_rules_active` (`is_active`, `entity_type`, `trigger_type`)'
);

CALL add_index_if_missing(
    'workflow_rules',
    'idx_workflow_rules_created_by',
    'ALTER TABLE `workflow_rules` ADD KEY `idx_workflow_rules_created_by` (`created_by`)'
);

CALL add_index_if_missing(
    'workflow_rule_runs',
    'idx_workflow_runs_rule',
    'ALTER TABLE `workflow_rule_runs` ADD KEY `idx_workflow_runs_rule` (`rule_id`)'
);

CALL add_index_if_missing(
    'workflow_rule_runs',
    'idx_workflow_runs_entity',
    'ALTER TABLE `workflow_rule_runs` ADD KEY `idx_workflow_runs_entity` (`entity_type`, `entity_id`)'
);

CALL add_index_if_missing(
    'workflow_rule_runs',
    'idx_workflow_runs_status',
    'ALTER TABLE `workflow_rule_runs` ADD KEY `idx_workflow_runs_status` (`status`)'
);

CALL add_index_if_missing(
    'workflow_rule_runs',
    'idx_workflow_runs_created_at',
    'ALTER TABLE `workflow_rule_runs` ADD KEY `idx_workflow_runs_created_at` (`created_at`)'
);

DROP PROCEDURE IF EXISTS add_index_if_missing;
