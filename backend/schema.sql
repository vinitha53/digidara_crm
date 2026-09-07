-- ============================================================
-- DIGIDARA CRM - MYSQL WORKBENCH DATABASE SETUP
-- ============================================================
-- Run this full file in MySQL Workbench to create the database
-- used by the Flask + React CRM application.
--
-- Database/schema name: digidara_crm12
--
-- Backend .env format:
-- DB_HOST=localhost
-- DB_PORT=3306
-- DB_USER=root
-- DB_PASSWORD=YOUR_MYSQL_PASSWORD
-- DB_NAME=digidara_crm12
-- ============================================================

CREATE DATABASE IF NOT EXISTS digidara_crm12
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE digidara_crm12;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS project_updates;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS program_progress_updates;
DROP TABLE IF EXISTS program_enrollments;

-- Create order is parent tables first.

CREATE TABLE IF NOT EXISTS roles (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `key`       VARCHAR(30) NOT NULL,
    label       VARCHAR(80) NOT NULL,
    description VARCHAR(255) NULL,
    is_system   TINYINT(1) NOT NULL DEFAULT 0,
    is_active   TINYINT(1) NOT NULL DEFAULT 1,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_roles_key (`key`),
    KEY idx_roles_active_label (is_active, label),
    CONSTRAINT chk_roles_system CHECK (is_system IN (0, 1)),
    CONSTRAINT chk_roles_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name            VARCHAR(150) NOT NULL,
    login_id        VARCHAR(80) NULL,
    email           VARCHAR(190) NOT NULL,
    phone           VARCHAR(40) NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(30) NOT NULL DEFAULT 'staff',
    branch          VARCHAR(100) NULL,
    department      VARCHAR(80) NULL,
    avatar_initials VARCHAR(10) NULL,
    avatar_color    VARCHAR(20) NOT NULL DEFAULT '#534AB7',
    is_active       TINYINT(1) NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login      DATETIME NULL,
    otp_secret      VARCHAR(255) NULL,
    otp_enabled     TINYINT(1) NOT NULL DEFAULT 1,

    PRIMARY KEY (id),
    UNIQUE KEY uq_users_login_id (login_id),
    UNIQUE KEY uq_users_email (email),
    KEY idx_users_role (role),
    KEY idx_users_active (is_active),
    CONSTRAINT chk_users_is_active CHECK (is_active IN (0, 1)),
    CONSTRAINT chk_users_otp_enabled CHECK (otp_enabled IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

CREATE TABLE IF NOT EXISTS role_permissions (
    id        INT UNSIGNED NOT NULL AUTO_INCREMENT,
    role      VARCHAR(30) NOT NULL,
    page_key  VARCHAR(80) NOT NULL,
    action    VARCHAR(80) NOT NULL,
    allowed   TINYINT(1) NOT NULL DEFAULT 0,
    updated_by INT UNSIGNED NULL,
    updated_at DATETIME NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_role_permissions_scope (role, page_key, action),
    KEY idx_role_permissions_role (role),
    KEY idx_role_permissions_page (page_key),
    KEY idx_role_permissions_updated (role, updated_at),
    CONSTRAINT chk_role_permissions_allowed CHECK (allowed IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS leads (
    id                   INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name                 VARCHAR(150) NOT NULL,
    phone                VARCHAR(40) NOT NULL,
    email                VARCHAR(190) NULL,
    company              VARCHAR(190) NULL,
    service              VARCHAR(190) NOT NULL,
    lead_category        VARCHAR(30) NOT NULL DEFAULT 'course',
    qualification        VARCHAR(190) NULL,
    program_duration     VARCHAR(50) NULL,
    course_name          VARCHAR(190) NULL,
    internship_name      VARCHAR(190) NULL,
    business_name        VARCHAR(190) NULL,
    business_requirement VARCHAR(190) NULL,
    source               VARCHAR(30) NOT NULL DEFAULT 'website',
    tag                  VARCHAR(30) NOT NULL DEFAULT 'new',
    status               VARCHAR(30) NOT NULL DEFAULT 'new',
    deal_value           INT NOT NULL DEFAULT 0,
    probability          TINYINT UNSIGNED NOT NULL DEFAULT 10,
    expected_close_date  DATE NULL,
    lost_reason          VARCHAR(255) NULL,
    lost_reason_detail   TEXT NULL,
    assigned_to          INT UNSIGNED NULL,
    notes                TEXT NULL,
    ai_score             INT NULL,
    ai_reason            TEXT NULL,
    ai_score_factors     TEXT NULL,
    ai_scored_at         DATETIME NULL,
    ai_next_best_action  TEXT NULL,
    city                 VARCHAR(120) NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    last_contacted       DATETIME NULL,
    ai_followup_enabled  TINYINT(1) NOT NULL DEFAULT 1,
    ai_followup_paused_reason VARCHAR(255) NULL,
    ai_preferred_channel VARCHAR(40) NULL,
    ai_last_followup_at  DATETIME NULL,
    ai_next_followup_at  DATETIME NULL,
    ai_followup_count    INT NOT NULL DEFAULT 0,
    ai_engagement_score  TINYINT UNSIGNED NOT NULL DEFAULT 0,
    ai_followup_outcome  VARCHAR(80) NULL,
    ai_followup_stop_reason TEXT NULL,
    ai_followup_stopped_at DATETIME NULL,
    source_system        VARCHAR(40) NULL,
    external_id          VARCHAR(190) NULL,
    external_created_at  DATETIME NULL,

    PRIMARY KEY (id),
    KEY idx_leads_assigned (assigned_to),
    KEY idx_leads_status (status),
    KEY idx_leads_status_lost_reason (status, lost_reason),
    KEY idx_leads_expected_close (expected_close_date),
    KEY idx_leads_tag (tag),
    KEY idx_leads_source (source),
    KEY idx_leads_category (lead_category),
    KEY idx_leads_ai_next_followup (ai_next_followup_at),
    KEY idx_leads_ai_followup_enabled (ai_followup_enabled),
    UNIQUE KEY uq_leads_source_external (source_system, external_id),
    KEY idx_leads_created_at (created_at),
    KEY idx_leads_report_period_status_category (created_at, status, lead_category),
    KEY idx_leads_report_owner_period (assigned_to, created_at, status),
    KEY idx_leads_report_owner_status_contact (assigned_to, status, last_contacted),
    KEY idx_leads_report_conversion_velocity (status, updated_at, created_at),
    CONSTRAINT fk_leads_assigned_to
        FOREIGN KEY (assigned_to) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_leads_category CHECK (lead_category IN ('course', 'internship', 'business')),
    CONSTRAINT chk_leads_source CHECK (source IN ('website', 'chatbot', 'whatsapp', 'email', 'inperson')),
    CONSTRAINT chk_leads_tag CHECK (tag IN ('new', 'hot', 'warm', 'cold')),
    CONSTRAINT chk_leads_status CHECK (status IN ('new', 'contacted', 'qualified', 'won', 'lost', 'converted', 'closed', 'not_interested')),
    CONSTRAINT chk_leads_deal_value CHECK (deal_value >= 0),
    CONSTRAINT chk_leads_probability CHECK (probability >= 0 AND probability <= 100),
    CONSTRAINT chk_leads_ai_score CHECK (ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)),
    CONSTRAINT chk_leads_ai_followup_enabled CHECK (ai_followup_enabled IN (0, 1)),
    CONSTRAINT chk_leads_ai_engagement_score CHECK (ai_engagement_score BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_followup_history (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    lead_id           INT UNSIGNED NOT NULL,
    user_id           INT UNSIGNED NULL,
    channel           VARCHAR(40) NOT NULL DEFAULT 'WhatsApp',
    message_type      VARCHAR(80) NOT NULL DEFAULT 'follow_up',
    generated_message TEXT NULL,
    edited_message    TEXT NULL,
    final_message     TEXT NULL,
    sequence_step     INT NULL,
    temperature_snapshot VARCHAR(30) NULL,
    recipient_phone   VARCHAR(40) NULL,
    original_phone    VARCHAR(40) NULL,
    template_id       INT UNSIGNED NULL,
    template_text     TEXT NULL,
    status            VARCHAR(40) NOT NULL DEFAULT 'generated',
    delivery_status   VARCHAR(40) NOT NULL DEFAULT 'pending',
    skip_reason       TEXT NULL,
    outcome           VARCHAR(80) NULL,
    scheduled_for     DATETIME NULL,
    sent_at           DATETIME NULL,
    generated_at      DATETIME NULL,
    stopped_at        DATETIME NULL,
    stopped_reason    TEXT NULL,
    provider_message_id VARCHAR(190) NULL,
    provider_status   VARCHAR(40) NULL,
    provider_response LONGTEXT NULL,
    provider_error    TEXT NULL,
    automation_mode   VARCHAR(30) NOT NULL DEFAULT 'automatic',
    response_received_at DATETIME NULL,
    claimed_at        DATETIME NULL,
    idempotency_key   VARCHAR(190) NOT NULL,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_ai_followup_idempotency (idempotency_key),
    KEY idx_ai_followup_lead (lead_id),
    KEY idx_ai_followup_status (status),
    KEY idx_ai_followup_scheduled (scheduled_for),
    KEY idx_ai_followup_sequence (temperature_snapshot, sequence_step),
    KEY idx_ai_followup_recipient (recipient_phone),
    KEY idx_ai_followup_provider_message (provider_message_id),
    CONSTRAINT fk_ai_followup_lead
        FOREIGN KEY (lead_id) REFERENCES leads(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ai_followup_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_ai_followup_status CHECK (status IN ('generated', 'pending', 'sent', 'delivered', 'read', 'failed', 'skipped', 'paused', 'manual', 'stopped', 'cancelled')),
    CONSTRAINT chk_ai_followup_delivery CHECK (delivery_status IN ('pending', 'accepted', 'sent', 'delivered', 'read', 'failed', 'skipped', 'stopped', 'cancelled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

CREATE TABLE IF NOT EXISTS ai_followup_prompt_logs (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    followup_id INT UNSIGNED NULL,
    lead_id     INT UNSIGNED NOT NULL,
    model       VARCHAR(120) NULL,
    prompt      LONGTEXT NOT NULL,
    response    LONGTEXT NULL,
    status      VARCHAR(40) NOT NULL DEFAULT 'success',
    error       TEXT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_ai_prompt_followup (followup_id),
    KEY idx_ai_prompt_lead (lead_id),
    CONSTRAINT fk_ai_prompt_followup
        FOREIGN KEY (followup_id) REFERENCES ai_followup_history(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_ai_prompt_lead
        FOREIGN KEY (lead_id) REFERENCES leads(id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customers (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    lead_id      INT UNSIGNED NOT NULL,
    name         VARCHAR(150) NOT NULL,
    phone        VARCHAR(40) NOT NULL,
    email        VARCHAR(190) NULL,
    company      VARCHAR(190) NULL,
    service      VARCHAR(190) NOT NULL,
    value        INT NOT NULL DEFAULT 0,
    status       VARCHAR(30) NOT NULL DEFAULT 'active',
    assigned_to  INT UNSIGNED NULL,
    last_contact DATE NULL,
    notes        TEXT NULL,
    rating       TINYINT UNSIGNED NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_customers_lead_id (lead_id),
    KEY idx_customers_assigned (assigned_to),
    KEY idx_customers_status (status),
    KEY idx_customers_scope_status_contact (assigned_to, status, last_contact),
    KEY idx_customers_created_at (created_at),
    CONSTRAINT fk_customers_lead
        FOREIGN KEY (lead_id) REFERENCES leads(id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_customers_assigned_to
        FOREIGN KEY (assigned_to) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_customers_rating CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    CONSTRAINT chk_customers_value CHECK (value >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tasks (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    title        VARCHAR(255) NOT NULL,
    notes        TEXT NULL,
    related_type VARCHAR(50) NULL,
    related_id   INT UNSIGNED NULL,
    related_name VARCHAR(190) NULL,
    due_date     DATE NULL,
    reminder_at  DATETIME NULL,
    recurrence_rule VARCHAR(80) NULL,
    recurrence_parent_id INT UNSIGNED NULL,
    recurrence_next_due DATE NULL,
    reminder_sent_at DATETIME NULL,
    meeting_invite_sent_at DATETIME NULL,
    dependency_task_id INT UNSIGNED NULL,
    meeting_start DATETIME NULL,
    meeting_end DATETIME NULL,
    meeting_location VARCHAR(255) NULL,
    assigned_to  INT UNSIGNED NULL,
    priority     VARCHAR(30) NOT NULL DEFAULT 'Medium',
    status       VARCHAR(30) NOT NULL DEFAULT 'pending',
    completed_at DATETIME NULL,
    created_by   INT UNSIGNED NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_tasks_assigned (assigned_to),
    KEY idx_tasks_status (status),
    KEY idx_tasks_due_date (due_date),
    KEY idx_tasks_scope_status_due (assigned_to, status, due_date),
    KEY idx_tasks_reminder (reminder_at),
    KEY idx_tasks_recurrence_parent (recurrence_parent_id),
    KEY idx_tasks_dependency (dependency_task_id),
    KEY idx_tasks_created_by (created_by),
    KEY idx_tasks_report_completed (status, completed_at, assigned_to),
    CONSTRAINT fk_tasks_recurrence_parent
        FOREIGN KEY (recurrence_parent_id) REFERENCES tasks(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_tasks_dependency
        FOREIGN KEY (dependency_task_id) REFERENCES tasks(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_tasks_assigned_to
        FOREIGN KEY (assigned_to) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_tasks_created_by
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_tasks_priority CHECK (priority IN ('Low', 'Medium', 'High')),
    CONSTRAINT chk_tasks_status CHECK (status IN ('pending', 'done'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS meeting_invites (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    task_id         INT UNSIGNED NOT NULL,
    user_id         INT UNSIGNED NULL,
    recipient_name  VARCHAR(190) NULL,
    recipient_phone VARCHAR(40) NULL,
    recipient_email VARCHAR(190) NULL,
    channel         VARCHAR(40) NOT NULL DEFAULT 'WhatsApp',
    status          VARCHAR(30) NOT NULL DEFAULT 'sent',
    sent_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_meeting_invites_task (task_id),
    KEY idx_meeting_invites_user (user_id),
    CONSTRAINT fk_meeting_invites_task
        FOREIGN KEY (task_id) REFERENCES tasks(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_meeting_invites_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_meeting_invites_status CHECK (status IN ('sent', 'failed', 'skipped'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customer_notes (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id INT UNSIGNED NOT NULL,
    user_id     INT UNSIGNED NULL,
    note        TEXT NOT NULL,
    note_type   VARCHAR(40) NOT NULL DEFAULT 'general',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_customer_notes_customer (customer_id),
    KEY idx_customer_notes_user (user_id),
    CONSTRAINT fk_customer_notes_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_customer_notes_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_customer_notes_type CHECK (note_type IN ('general', 'call', 'meeting', 'risk', 'success'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS customer_documents (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id    INT UNSIGNED NOT NULL,
    user_id        INT UNSIGNED NULL,
    file_name      VARCHAR(255) NOT NULL,
    mime_type      VARCHAR(120) NULL,
    file_size      INT NOT NULL DEFAULT 0,
    content_base64 LONGTEXT NOT NULL,
    description    TEXT NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_customer_documents_customer (customer_id),
    KEY idx_customer_documents_user (user_id),
    CONSTRAINT fk_customer_documents_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_customer_documents_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_customer_documents_size CHECK (file_size >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS saved_views (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    INT UNSIGNED NOT NULL,
    module     VARCHAR(80) NOT NULL,
    name       VARCHAR(150) NOT NULL,
    filters    JSON NOT NULL,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_saved_views_user_module (user_id, module),
    CONSTRAINT fk_saved_views_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_saved_views_default CHECK (is_default IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS support_tickets (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    subject          VARCHAR(255) NOT NULL,
    description      TEXT NULL,
    customer_id      INT UNSIGNED NULL,
    customer_name    VARCHAR(190) NULL,
    priority         VARCHAR(30) NOT NULL DEFAULT 'Medium',
    status           VARCHAR(30) NOT NULL DEFAULT 'open',
    sla_due_at       DATETIME NULL,
    assigned_to      INT UNSIGNED NULL,
    created_by       INT UNSIGNED NULL,
    resolved_at      DATETIME NULL,
    resolution_notes TEXT NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_support_status (status),
    KEY idx_support_priority (priority),
    KEY idx_support_assigned (assigned_to),
    KEY idx_support_customer (customer_id),
    KEY idx_support_sla (sla_due_at),
    CONSTRAINT fk_support_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_support_assigned
        FOREIGN KEY (assigned_to) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_support_created_by
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_support_priority CHECK (priority IN ('Low', 'Medium', 'High')),
    CONSTRAINT chk_support_status CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ticket_history (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    ticket_id  INT UNSIGNED NOT NULL,
    user_id    INT UNSIGNED NULL,
    action     VARCHAR(80) NOT NULL,
    note       TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_ticket_history_ticket (ticket_id),
    CONSTRAINT fk_ticket_history_ticket
        FOREIGN KEY (ticket_id) REFERENCES support_tickets(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ticket_history_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS courses (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name        VARCHAR(190) NOT NULL,
    category    VARCHAR(40) NOT NULL DEFAULT 'course',
    duration    VARCHAR(80) NULL,
    fee         INT NOT NULL DEFAULT 0,
    status      VARCHAR(30) NOT NULL DEFAULT 'active',
    description TEXT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_courses_status (status),
    CONSTRAINT chk_courses_category CHECK (category IN ('course', 'internship')),
    CONSTRAINT chk_courses_status CHECK (status IN ('active', 'inactive')),
    CONSTRAINT chk_courses_fee CHECK (fee >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS batches (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    course_id  INT UNSIGNED NULL,
    name       VARCHAR(190) NOT NULL,
    mentor_id  INT UNSIGNED NULL,
    start_date DATE NULL,
    end_date   DATE NULL,
    schedule   VARCHAR(190) NULL,
    capacity   INT NOT NULL DEFAULT 0,
    status     VARCHAR(30) NOT NULL DEFAULT 'planned',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_batches_course (course_id),
    KEY idx_batches_mentor (mentor_id),
    KEY idx_batches_status (status),
    CONSTRAINT fk_batches_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_batches_mentor
        FOREIGN KEY (mentor_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_batches_status CHECK (status IN ('planned', 'running', 'completed', 'cancelled')),
    CONSTRAINT chk_batches_capacity CHECK (capacity >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS students (
    id                 INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name               VARCHAR(150) NOT NULL,
    phone              VARCHAR(40) NOT NULL,
    email              VARCHAR(190) NULL,
    course_id          INT UNSIGNED NULL,
    batch_id           INT UNSIGNED NULL,
    lead_id            INT UNSIGNED NULL,
    status             VARCHAR(30) NOT NULL DEFAULT 'enrolled',
    attendance_percent TINYINT UNSIGNED NOT NULL DEFAULT 0,
    placement_status   VARCHAR(40) NOT NULL DEFAULT 'not_started',
    notes              TEXT NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_students_course (course_id),
    KEY idx_students_batch (batch_id),
    KEY idx_students_status (status),
    CONSTRAINT fk_students_course
        FOREIGN KEY (course_id) REFERENCES courses(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_students_batch
        FOREIGN KEY (batch_id) REFERENCES batches(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_students_lead
        FOREIGN KEY (lead_id) REFERENCES leads(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_students_status CHECK (status IN ('enrolled', 'active', 'completed', 'dropped')),
    CONSTRAINT chk_students_attendance CHECK (attendance_percent BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ai_interactions (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    INT UNSIGNED NULL,
    conversation_id VARCHAR(64) NULL,
    conversation_title VARCHAR(160) NULL,
    prompt     TEXT NOT NULL,
    response   TEXT NOT NULL,
    intent     VARCHAR(80) NOT NULL DEFAULT 'copilot',
    model      VARCHAR(100) NULL,
    status     VARCHAR(30) NOT NULL DEFAULT 'success',
    sources    VARCHAR(255) NULL,
    response_format VARCHAR(30) NOT NULL DEFAULT 'summary',
    response_data JSON NULL,
    row_count INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_ai_interactions_user (user_id),
    KEY idx_ai_interactions_user_created (user_id, created_at),
    KEY idx_ai_interactions_conversation (user_id, conversation_id, created_at),
    CONSTRAINT fk_ai_interactions_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
    KEY idx_workflow_rules_active (is_active, entity_type, trigger_type),
    KEY idx_workflow_rules_created_by (created_by),
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
    KEY idx_workflow_runs_rule (rule_id),
    KEY idx_workflow_runs_entity (entity_type, entity_id),
    KEY idx_workflow_runs_status (status),
    KEY idx_workflow_runs_created_at (created_at),
    CONSTRAINT fk_workflow_runs_rule
        FOREIGN KEY (rule_id) REFERENCES workflow_rules(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_workflow_runs_status CHECK (status IN ('success', 'skipped', 'error'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS campaigns (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name          VARCHAR(190) NOT NULL,
    channel       VARCHAR(40) NOT NULL,
    audience      VARCHAR(190) NOT NULL,
    message_body  TEXT NOT NULL,
    from_name     VARCHAR(190) NOT NULL DEFAULT 'Digidara Technologies',
    status        VARCHAR(30) NOT NULL DEFAULT 'draft',
    scheduled_at  DATETIME NULL,
    sent_at       DATETIME NULL,
    sent_count    INT NOT NULL DEFAULT 0,
    opened_count  INT NOT NULL DEFAULT 0,
    reply_count   INT NOT NULL DEFAULT 0,
    created_by    INT UNSIGNED NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_campaigns_status (status),
    KEY idx_campaigns_channel (channel),
    KEY idx_campaigns_created_by (created_by),
    KEY idx_campaigns_created_at (created_at),
    CONSTRAINT fk_campaigns_created_by
        FOREIGN KEY (created_by) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_campaigns_status CHECK (status IN ('draft', 'scheduled', 'sent')),
    CONSTRAINT chk_campaigns_counts CHECK (sent_count >= 0 AND opened_count >= 0 AND reply_count >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS message_logs (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    campaign_id    INT UNSIGNED NULL,
    recipient_type VARCHAR(50) NULL,
    recipient_id   INT UNSIGNED NULL,
    recipient_name VARCHAR(190) NULL,
    channel        VARCHAR(40) NULL,
    message_body   TEXT NULL,
    status         VARCHAR(30) NOT NULL DEFAULT 'sent',
    template_used  VARCHAR(190) NULL,
    recipient_phone VARCHAR(40) NULL,
    provider_message_id VARCHAR(190) NULL,
    provider_status VARCHAR(40) NULL,
    provider_response LONGTEXT NULL,
    error_message TEXT NULL,
    followup_id INT UNSIGNED NULL,
    sent_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_message_logs_campaign (campaign_id),
    KEY idx_message_logs_recipient (recipient_type, recipient_id),
    KEY idx_message_logs_recipient_sent (recipient_type, recipient_id, sent_at),
    KEY idx_message_logs_status (status),
    KEY idx_message_logs_template (template_used),
    KEY idx_message_logs_followup (followup_id),
    KEY idx_message_logs_sent_at (sent_at),
    CONSTRAINT fk_message_logs_campaign
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT chk_message_logs_status CHECK (status IN ('sent', 'failed', 'skipped'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

CREATE TABLE IF NOT EXISTS activity_log (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     INT UNSIGNED NULL,
    action      VARCHAR(120) NOT NULL,
    entity_type VARCHAR(80) NULL,
    entity_id   INT UNSIGNED NULL,
    entity_name VARCHAR(190) NULL,
    meta        TEXT NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_activity_user (user_id),
    KEY idx_activity_entity (entity_type, entity_id),
    KEY idx_activity_created_at (created_at),
    CONSTRAINT fk_activity_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notifications (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    INT UNSIGNED NULL,
    type       VARCHAR(80) NULL,
    title      VARCHAR(190) NOT NULL,
    body       TEXT NULL,
    is_read    TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_notifications_user (user_id, is_read),
    KEY idx_notifications_user_read_created (user_id, is_read, created_at),
    KEY idx_notifications_created_at (created_at),
    KEY idx_notifications_type (type),
    CONSTRAINT fk_notifications_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_notifications_is_read CHECK (is_read IN (0, 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS company_settings (
    id                         TINYINT UNSIGNED NOT NULL DEFAULT 1,
    company_name               VARCHAR(190) NOT NULL DEFAULT 'Digidara Technologies Pvt Ltd',
    tagline                    VARCHAR(255) NULL,
    about_crm                  TEXT NULL,
    website                    VARCHAR(255) NOT NULL DEFAULT 'https://digidaratechnologies.com',
    email                      VARCHAR(190) NOT NULL DEFAULT 'info@digidaratechnologies.com',
    phone                      VARCHAR(40) NULL,
    city                       VARCHAR(190) NOT NULL DEFAULT 'Coimbatore, Tamil Nadu, India',
    gst_number                 VARCHAR(40) NULL,
    logo_url                   VARCHAR(500) NULL,
    primary_color              VARCHAR(20) NOT NULL DEFAULT '#534AB7',
    google_review_url          VARCHAR(500) NOT NULL DEFAULT 'https://g.page/r/CXarerFSXX1qEBM/review',
    google_review_place_id     VARCHAR(255) NULL,
    google_review_api_key      VARCHAR(255) NULL,
    whatsapp_api_token         TEXT NULL,
    whatsapp_phone_number_id   VARCHAR(100) NULL,
    gmail_address              VARCHAR(190) NULL,
    gmail_app_password         VARCHAR(255) NULL,
    course_name_options        TEXT NULL,
    internship_name_options    TEXT NULL,
    business_service_options   TEXT NULL,
    ai_followups_enabled       TINYINT(1) NOT NULL DEFAULT 0,
    ai_followup_hot_interval_days INT NOT NULL DEFAULT 2,
    ai_followup_warm_interval_days INT NOT NULL DEFAULT 4,
    ai_followup_cold_interval_days INT NOT NULL DEFAULT 5,
    ai_followup_business_hours VARCHAR(40) NOT NULL DEFAULT '09:00-18:00',
    ai_followup_working_days   VARCHAR(80) NOT NULL DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat',
    ai_followup_max_count      INT NOT NULL DEFAULT 10,
    ai_followup_stop_after_no_response INT NOT NULL DEFAULT 0,
    ai_followup_preferred_channel VARCHAR(40) NOT NULL DEFAULT 'WhatsApp',
    ai_followup_llm_model      VARCHAR(120) NOT NULL DEFAULT 'llama3-8b-8192',
    updated_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    CONSTRAINT chk_company_settings_single_row CHECK (id = 1),
    CONSTRAINT chk_company_ai_followups_enabled CHECK (ai_followups_enabled IN (0, 1)),
    CONSTRAINT chk_company_ai_followup_max CHECK (ai_followup_max_count >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- Existing database upgrade helpers
-- ============================================================
-- The Flask app has small SQLite-only startup migrations for columns
-- added during the project. This MySQL block keeps an older teammate
-- database in sync when this schema is re-run in Workbench.

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

DROP PROCEDURE IF EXISTS drop_check_if_exists;
DELIMITER //
CREATE PROCEDURE drop_check_if_exists(
    IN table_name_in VARCHAR(64),
    IN constraint_name_in VARCHAR(64)
)
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_in
          AND CONSTRAINT_NAME = constraint_name_in
          AND CONSTRAINT_TYPE = 'CHECK'
    ) THEN
        SET @ddl = CONCAT('ALTER TABLE `', table_name_in, '` DROP CHECK `', constraint_name_in, '`');
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

-- Older CRM builds stored the assignee in a text column named
-- assigned_to_id. Use dynamic SQL so a current database that never had
-- that legacy column can run this entire schema without error 1054.
DROP PROCEDURE IF EXISTS migrate_legacy_lead_assignments;
DELIMITER //
CREATE PROCEDURE migrate_legacy_lead_assignments()
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'leads'
          AND COLUMN_NAME = 'assigned_to_id'
    ) THEN
        SET @dml = 'UPDATE leads l
            LEFT JOIN users u ON u.id = CAST(l.assigned_to_id AS UNSIGNED)
            SET l.assigned_to = u.id
            WHERE l.assigned_to IS NULL
              AND l.assigned_to_id REGEXP ''^[0-9]+$''';
        PREPARE stmt FROM @dml;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//
DELIMITER ;

CALL add_column_if_missing('company_settings', 'about_crm', 'TEXT NULL');
CALL add_column_if_missing('company_settings', 'google_review_url', 'VARCHAR(500) NOT NULL DEFAULT ''https://g.page/r/CXarerFSXX1qEBM/review''');
CALL add_column_if_missing('company_settings', 'google_review_place_id', 'VARCHAR(255) NULL');
CALL add_column_if_missing('company_settings', 'google_review_api_key', 'VARCHAR(255) NULL');
CALL add_column_if_missing('company_settings', 'whatsapp_api_token', 'TEXT NULL');
CALL add_column_if_missing('company_settings', 'whatsapp_phone_number_id', 'VARCHAR(100) NULL');
CALL add_column_if_missing('company_settings', 'gmail_address', 'VARCHAR(190) NULL');
CALL add_column_if_missing('company_settings', 'gmail_app_password', 'VARCHAR(255) NULL');
CALL add_column_if_missing('company_settings', 'course_name_options', 'TEXT NULL');
CALL add_column_if_missing('company_settings', 'internship_name_options', 'TEXT NULL');
CALL add_column_if_missing('company_settings', 'business_service_options', 'TEXT NULL');
CALL add_column_if_missing('company_settings', 'ai_followups_enabled', 'TINYINT(1) NOT NULL DEFAULT 0');
CALL add_column_if_missing('company_settings', 'ai_followup_hot_interval_days', 'INT NOT NULL DEFAULT 2');
CALL add_column_if_missing('company_settings', 'ai_followup_warm_interval_days', 'INT NOT NULL DEFAULT 4');
CALL add_column_if_missing('company_settings', 'ai_followup_cold_interval_days', 'INT NOT NULL DEFAULT 5');
CALL add_column_if_missing('company_settings', 'ai_followup_business_hours', 'VARCHAR(40) NOT NULL DEFAULT ''09:00-18:00''');
CALL add_column_if_missing('company_settings', 'ai_followup_working_days', 'VARCHAR(80) NOT NULL DEFAULT ''Mon,Tue,Wed,Thu,Fri,Sat''');
CALL add_column_if_missing('company_settings', 'ai_followup_max_count', 'INT NOT NULL DEFAULT 10');
CALL add_column_if_missing('company_settings', 'ai_followup_stop_after_no_response', 'INT NOT NULL DEFAULT 0');
CALL add_column_if_missing('company_settings', 'ai_followup_preferred_channel', 'VARCHAR(40) NOT NULL DEFAULT ''WhatsApp''');
CALL add_column_if_missing('company_settings', 'ai_followup_llm_model', 'VARCHAR(120) NOT NULL DEFAULT ''llama3-8b-8192''');

CALL add_column_if_missing('users', 'login_id', 'VARCHAR(80) NULL');
CALL add_column_if_missing('users', 'branch', 'VARCHAR(100) NULL');
CALL add_column_if_missing('users', 'phone', 'VARCHAR(40) NULL');
CALL add_column_if_missing('users', 'otp_secret', 'VARCHAR(255) NULL');
CALL add_column_if_missing('users', 'otp_enabled', 'TINYINT(1) NOT NULL DEFAULT 1');
CALL modify_column_if_exists('users', 'otp_enabled', 'TINYINT(1) NOT NULL DEFAULT 1');
CALL add_column_if_missing('login_otp_challenges', 'send_attempts', 'SMALLINT UNSIGNED NOT NULL DEFAULT 0');
CALL add_column_if_missing('login_otp_challenges', 'delivery_status', 'VARCHAR(20) NOT NULL DEFAULT ''pending''');
CALL add_column_if_missing('login_otp_challenges', 'meta_message_id', 'VARCHAR(190) NULL');
CALL add_index_if_missing(
    'login_otp_challenges',
    'idx_login_otp_delivery',
    'ALTER TABLE `login_otp_challenges` ADD KEY `idx_login_otp_delivery` (`delivery_status`, `created_at`)'
);
CALL drop_check_if_exists('users', 'chk_users_role');
CALL drop_check_if_exists('role_permissions', 'chk_role_permissions_role');
CALL add_column_if_missing('role_permissions', 'updated_by', 'INT UNSIGNED NULL');
CALL add_column_if_missing('role_permissions', 'updated_at', 'DATETIME NULL');
CALL add_index_if_missing(
    'role_permissions',
    'idx_role_permissions_updated',
    'ALTER TABLE `role_permissions` ADD KEY `idx_role_permissions_updated` (`role`, `updated_at`)'
);
CALL add_index_if_missing(
    'users',
    'uq_users_login_id',
    'ALTER TABLE `users` ADD UNIQUE KEY `uq_users_login_id` (`login_id`)'
);

UPDATE users
SET login_id = LOWER(SUBSTRING_INDEX(email, '@', 1))
WHERE login_id IS NULL OR login_id = '';

CALL add_column_if_missing('leads', 'lead_category', 'VARCHAR(30) NOT NULL DEFAULT ''course''');
CALL add_column_if_missing('leads', 'qualification', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'program_duration', 'VARCHAR(50) NULL');
CALL add_column_if_missing('leads', 'course_name', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'internship_name', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'business_name', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'business_requirement', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'tag', 'VARCHAR(50) NOT NULL DEFAULT ''new''');
CALL add_column_if_missing('leads', 'deal_value', 'INT NOT NULL DEFAULT 0');
CALL add_column_if_missing('leads', 'probability', 'TINYINT UNSIGNED NOT NULL DEFAULT 10');
CALL add_column_if_missing('leads', 'expected_close_date', 'DATE NULL');
CALL add_column_if_missing('leads', 'lost_reason', 'VARCHAR(255) NULL');
CALL add_column_if_missing('leads', 'lost_reason_detail', 'TEXT NULL');
CALL add_column_if_missing('leads', 'assigned_to', 'INT UNSIGNED NULL');
CALL add_column_if_missing('leads', 'ai_score', 'TINYINT UNSIGNED NULL');
CALL add_column_if_missing('leads', 'ai_reason', 'TEXT NULL');
CALL add_column_if_missing('leads', 'ai_score_factors', 'TEXT NULL');
CALL add_column_if_missing('leads', 'ai_scored_at', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_next_best_action', 'TEXT NULL');
CALL add_column_if_missing('leads', 'city', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'last_contacted', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_followup_enabled', 'TINYINT(1) NOT NULL DEFAULT 1');
CALL add_column_if_missing('leads', 'ai_followup_paused_reason', 'VARCHAR(255) NULL');
CALL add_column_if_missing('leads', 'ai_preferred_channel', 'VARCHAR(40) NULL');
CALL add_column_if_missing('leads', 'ai_last_followup_at', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_next_followup_at', 'DATETIME NULL');
CALL add_column_if_missing('leads', 'ai_followup_count', 'INT NOT NULL DEFAULT 0');
CALL add_column_if_missing('leads', 'ai_engagement_score', 'TINYINT UNSIGNED NOT NULL DEFAULT 0');
CALL add_column_if_missing('leads', 'ai_followup_outcome', 'VARCHAR(80) NULL');
CALL add_column_if_missing('leads', 'source_system', 'VARCHAR(40) NULL');
CALL add_column_if_missing('leads', 'external_id', 'VARCHAR(190) NULL');
CALL add_column_if_missing('leads', 'external_created_at', 'DATETIME NULL');

CALL modify_column_if_exists('leads', 'agency_id', 'INT NULL DEFAULT NULL');

CALL add_column_if_missing('tasks', 'reminder_at', 'DATETIME NULL');
CALL add_column_if_missing('tasks', 'recurrence_rule', 'VARCHAR(80) NULL');
CALL add_column_if_missing('tasks', 'recurrence_parent_id', 'INT UNSIGNED NULL');
CALL add_column_if_missing('tasks', 'recurrence_next_due', 'DATE NULL');
CALL add_column_if_missing('tasks', 'reminder_sent_at', 'DATETIME NULL');
CALL add_column_if_missing('tasks', 'meeting_invite_sent_at', 'DATETIME NULL');
CALL add_column_if_missing('tasks', 'dependency_task_id', 'INT UNSIGNED NULL');
CALL add_column_if_missing('tasks', 'meeting_start', 'DATETIME NULL');
CALL add_column_if_missing('tasks', 'meeting_end', 'DATETIME NULL');
CALL add_column_if_missing('tasks', 'meeting_location', 'VARCHAR(255) NULL');

-- AI Chat stores the exact structured answer so ChatGPT-style answer sections,
-- owner-attention points, explicitly requested tables and calculation context remain available when a
-- user reloads query history. Both points and tables use response_data JSON;
-- no separate presentation-only database column is required.
CALL add_column_if_missing('ai_interactions', 'model', 'VARCHAR(100) NULL');
CALL add_column_if_missing('ai_interactions', 'status', 'VARCHAR(30) NOT NULL DEFAULT ''success''');
CALL add_column_if_missing('ai_interactions', 'sources', 'VARCHAR(255) NULL');
CALL add_column_if_missing('ai_interactions', 'response_format', 'VARCHAR(30) NOT NULL DEFAULT ''summary''');
CALL add_column_if_missing('ai_interactions', 'response_data', 'JSON NULL');
CALL add_column_if_missing('ai_interactions', 'row_count', 'INT UNSIGNED NOT NULL DEFAULT 0');
CALL add_column_if_missing('ai_interactions', 'conversation_id', 'VARCHAR(64) NULL');
CALL add_column_if_missing('ai_interactions', 'conversation_title', 'VARCHAR(160) NULL');

-- Consolidate the retired AI Copilot permission key into the current AI Chat
-- key without overwriting an already configured AI Chat permission.
INSERT IGNORE INTO role_permissions (role, page_key, action, allowed, updated_by, updated_at)
SELECT role, 'ai_chat', action, allowed, updated_by, updated_at
FROM role_permissions
WHERE page_key = 'ai_copilot';

DELETE FROM role_permissions WHERE page_key = 'ai_copilot';

UPDATE ai_interactions
SET conversation_id = CONCAT('legacy-', id),
    conversation_title = LEFT(TRIM(prompt), 80)
WHERE conversation_id IS NULL OR conversation_id = '';

CALL add_index_if_missing(
    'leads',
    'idx_leads_expected_close',
    'ALTER TABLE `leads` ADD KEY `idx_leads_expected_close` (`expected_close_date`)'
);

CALL add_index_if_missing(
    'leads',
    'idx_leads_status_lost_reason',
    'ALTER TABLE `leads` ADD KEY `idx_leads_status_lost_reason` (`status`, `lost_reason`)'
);

CALL add_index_if_missing(
    'leads',
    'idx_leads_ai_next_followup',
    'ALTER TABLE `leads` ADD KEY `idx_leads_ai_next_followup` (`ai_next_followup_at`)'
);

CALL add_index_if_missing(
    'leads',
    'uq_leads_source_external',
    'ALTER TABLE `leads` ADD UNIQUE KEY `uq_leads_source_external` (`source_system`, `external_id`)'
);

-- Period-aware owner reporting: cohort status/category performance, employee
-- lead accountability and completed-task execution.
CALL add_index_if_missing(
    'leads',
    'idx_leads_report_period_status_category',
    'ALTER TABLE `leads` ADD KEY `idx_leads_report_period_status_category` (`created_at`, `status`, `lead_category`)'
);

CALL add_index_if_missing(
    'leads',
    'idx_leads_report_owner_period',
    'ALTER TABLE `leads` ADD KEY `idx_leads_report_owner_period` (`assigned_to`, `created_at`, `status`)'
);

CALL add_index_if_missing(
    'leads',
    'idx_leads_report_owner_status_contact',
    'ALTER TABLE `leads` ADD KEY `idx_leads_report_owner_status_contact` (`assigned_to`, `status`, `last_contacted`)'
);

CALL add_index_if_missing(
    'leads',
    'idx_leads_report_conversion_velocity',
    'ALTER TABLE `leads` ADD KEY `idx_leads_report_conversion_velocity` (`status`, `updated_at`, `created_at`)'
);

CALL add_index_if_missing(
    'tasks',
    'idx_tasks_reminder',
    'ALTER TABLE `tasks` ADD KEY `idx_tasks_reminder` (`reminder_at`)'
);

CALL add_index_if_missing(
    'ai_interactions',
    'idx_ai_interactions_user_created',
    'ALTER TABLE `ai_interactions` ADD KEY `idx_ai_interactions_user_created` (`user_id`, `created_at`)'
);

CALL add_index_if_missing(
    'ai_interactions',
    'idx_ai_interactions_conversation',
    'ALTER TABLE `ai_interactions` ADD KEY `idx_ai_interactions_conversation` (`user_id`, `conversation_id`, `created_at`)'
);

CALL add_index_if_missing(
    'message_logs',
    'idx_message_logs_recipient_sent',
    'ALTER TABLE `message_logs` ADD KEY `idx_message_logs_recipient_sent` (`recipient_type`, `recipient_id`, `sent_at`)'
);

CALL add_index_if_missing(
    'notifications',
    'idx_notifications_user_read_created',
    'ALTER TABLE `notifications` ADD KEY `idx_notifications_user_read_created` (`user_id`, `is_read`, `created_at`)'
);

CALL sync_leads_status_check();

UPDATE company_settings
SET google_review_url = 'https://g.page/r/CXarerFSXX1qEBM/review'
WHERE id = 1
  AND (google_review_url IS NULL OR google_review_url = '' OR google_review_url = 'https://g.page/r/example');

UPDATE company_settings
SET course_name_options = 'GenAI Course\nPython Full Stack\nAI Training'
WHERE id = 1
  AND (course_name_options IS NULL OR course_name_options = '');

UPDATE company_settings
SET internship_name_options = 'AI Internship\nML / Data Science\nWeb Development Internship'
WHERE id = 1
  AND (internship_name_options IS NULL OR internship_name_options = '');

UPDATE company_settings
SET business_service_options = 'AI Product Development\nDigital Marketing\nAI Consulting\nWebsite Development\nSoftware Development'
WHERE id = 1
  AND (business_service_options IS NULL OR business_service_options = '');

UPDATE leads
SET program_duration = NULL
WHERE lead_category != 'internship';

-- Standardize historical free-text loss reasons for reliable dashboard
-- grouping while retaining the original wording in lost_reason_detail.
UPDATE leads
SET lost_reason_detail = COALESCE(NULLIF(TRIM(lost_reason_detail), ''), NULLIF(TRIM(lost_reason), ''))
WHERE status = 'lost'
  AND lost_reason IS NOT NULL
  AND TRIM(lost_reason) != ''
  AND lost_reason NOT IN (
      'Payment too high', 'Timing issue', 'Family issue', 'Chose a competitor',
      'No response', 'Not interested', 'Not a good fit', 'Other'
  );

UPDATE leads
SET lost_reason = CASE
    WHEN lost_reason IS NULL OR TRIM(lost_reason) = '' THEN 'Other'
    WHEN LOWER(TRIM(lost_reason)) IN (
        'payment too high', 'timing issue', 'family issue', 'chose a competitor',
        'no response', 'not interested', 'not a good fit', 'other'
    ) THEN CASE LOWER(TRIM(lost_reason))
        WHEN 'payment too high' THEN 'Payment too high'
        WHEN 'timing issue' THEN 'Timing issue'
        WHEN 'family issue' THEN 'Family issue'
        WHEN 'chose a competitor' THEN 'Chose a competitor'
        WHEN 'no response' THEN 'No response'
        WHEN 'not interested' THEN 'Not interested'
        WHEN 'not a good fit' THEN 'Not a good fit'
        ELSE 'Other'
    END
    WHEN LOWER(lost_reason) REGEXP 'payment|price|pricing|cost|budget|expensive|fee' THEN 'Payment too high'
    WHEN LOWER(lost_reason) REGEXP 'timing|not now|later|delay|schedule|busy' THEN 'Timing issue'
    WHEN LOWER(lost_reason) REGEXP 'family|parent|personal reason' THEN 'Family issue'
    WHEN LOWER(lost_reason) REGEXP 'competitor|another provider|other provider|alternative' THEN 'Chose a competitor'
    WHEN LOWER(lost_reason) REGEXP 'no response|not responding|unresponsive|unreachable|no reply' THEN 'No response'
    WHEN LOWER(lost_reason) REGEXP 'not interested|declined|changed mind' THEN 'Not interested'
    WHEN LOWER(lost_reason) REGEXP 'not qualified|not a fit|not suitable|requirement mismatch|ineligible' THEN 'Not a good fit'
    ELSE 'Other'
END
WHERE status = 'lost';

UPDATE leads
SET lost_reason = NULL,
    lost_reason_detail = NULL
WHERE status != 'lost';

UPDATE leads
SET source = CASE LOWER(source)
    WHEN 'website' THEN 'website'
    WHEN 'chatbot' THEN 'chatbot'
    WHEN 'whatsapp' THEN 'whatsapp'
    WHEN 'email' THEN 'email'
    WHEN 'inperson' THEN 'inperson'
    WHEN 'in person' THEN 'inperson'
    ELSE 'website'
END;

CALL migrate_legacy_lead_assignments();

INSERT INTO customers (lead_id, name, phone, email, company, service, status, assigned_to, notes, created_at, updated_at)
SELECT l.id, l.name, l.phone, l.email, COALESCE(l.company, l.business_name), l.service, 'active', l.assigned_to, l.notes, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM leads l
WHERE l.status = 'won'
  AND NOT EXISTS (SELECT 1 FROM customers c WHERE c.lead_id = l.id);

CALL add_index_if_missing(
    'customers',
    'uq_customers_lead_id',
    'ALTER TABLE `customers` ADD UNIQUE KEY `uq_customers_lead_id` (`lead_id`)'
);

CALL add_index_if_missing(
    'customers',
    'idx_customers_scope_status_contact',
    'ALTER TABLE `customers` ADD KEY `idx_customers_scope_status_contact` (`assigned_to`, `status`, `last_contact`)'
);

CALL add_index_if_missing(
    'tasks',
    'idx_tasks_scope_status_due',
    'ALTER TABLE `tasks` ADD KEY `idx_tasks_scope_status_due` (`assigned_to`, `status`, `due_date`)'
);

CALL add_index_if_missing(
    'tasks',
    'idx_tasks_report_completed',
    'ALTER TABLE `tasks` ADD KEY `idx_tasks_report_completed` (`status`, `completed_at`, `assigned_to`)'
);

DROP PROCEDURE IF EXISTS sync_leads_status_check;
DROP PROCEDURE IF EXISTS migrate_legacy_lead_assignments;
DROP PROCEDURE IF EXISTS drop_check_if_exists;
DROP PROCEDURE IF EXISTS modify_column_if_exists;
DROP PROCEDURE IF EXISTS add_index_if_missing;
DROP PROCEDURE IF EXISTS add_column_if_missing;

-- Starter users for development/client setup.
-- Login:
-- Admin:    admin@digidaratechnologies.com / Admin@1234
-- Employee: arjun@digidaratechnologies.com / Emp@1234
-- Employee: sneha@digidaratechnologies.com / Emp@1234
-- Employee: karthik@digidaratechnologies.com / Emp@1234

INSERT IGNORE INTO users
    (id, name, login_id, email, phone, password_hash, role, branch, department, avatar_initials, avatar_color, is_active)
VALUES
    (1, 'Digidara Admin', 'admin', 'admin@digidaratechnologies.com', '+916369979579', 'pbkdf2:sha256:1000000$qxmbmIL54dBOY1Tr$d4b08afc3213c296cbf35f35c5c1e490d500e54fd90c2f3678f8fabc1fa8ed3e', 'admin', 'Coimbatore', 'management', 'DA', '#534AB7', 1),
    (2, 'Arjun Kumar', 'arjun', 'arjun@digidaratechnologies.com', '+91 98765 11111', 'pbkdf2:sha256:1000000$XLrhDyHgg0g0D5nF$dd1875f919900a91f9b35616b887b3963cfeaa6c91fa02d865a184caa2c17912', 'employee', 'Coimbatore', 'sales', 'AK', '#1D9E75', 1),
    (3, 'Sneha Thilak', 'sneha', 'sneha@digidaratechnologies.com', '+91 98765 22222', 'pbkdf2:sha256:1000000$XLrhDyHgg0g0D5nF$dd1875f919900a91f9b35616b887b3963cfeaa6c91fa02d865a184caa2c17912', 'employee', 'Coimbatore', 'support', 'ST', '#BA7517', 1),
    (4, 'Karthik M', 'karthik', 'karthik@digidaratechnologies.com', '+91 98765 33333', 'pbkdf2:sha256:1000000$XLrhDyHgg0g0D5nF$dd1875f919900a91f9b35616b887b3963cfeaa6c91fa02d865a184caa2c17912', 'employee', 'Coimbatore', 'marketing', 'KM', '#A32D2D', 1);

UPDATE users
SET phone = '+916369979579', otp_enabled = 1
WHERE id = 1 OR login_id = 'admin' OR email = 'admin@digidaratechnologies.com';

UPDATE users
SET otp_enabled = 1
WHERE is_active = 1 AND phone IS NOT NULL AND phone != '';

INSERT INTO roles (`key`, label, description, is_system, is_active)
VALUES
    ('admin', 'Administrator', 'Full CRM access', 1, 1),
    ('staff', 'Staff', 'Standard employee access', 1, 1)
ON DUPLICATE KEY UPDATE
    label = VALUES(label), description = VALUES(description), is_system = 1, is_active = 1;

DELETE FROM role_permissions WHERE page_key IN ('programs', 'projects', 'support');

INSERT IGNORE INTO role_permissions (role, page_key, action, allowed)
VALUES
    ('admin', 'dashboard', 'view', 1),
    ('admin', 'leads', 'view', 1), ('admin', 'leads', 'create', 1), ('admin', 'leads', 'update', 1), ('admin', 'leads', 'delete', 1), ('admin', 'leads', 'assign', 1), ('admin', 'leads', 'convert', 1), ('admin', 'leads', 'classify', 1),
    ('admin', 'customers', 'view', 1), ('admin', 'customers', 'create', 1), ('admin', 'customers', 'update', 1), ('admin', 'customers', 'delete', 1), ('admin', 'customers', 'send_review', 1), ('admin', 'customers', 'sync_review', 1),
    ('admin', 'tasks', 'view', 1), ('admin', 'tasks', 'create', 1), ('admin', 'tasks', 'update', 1), ('admin', 'tasks', 'delete', 1), ('admin', 'tasks', 'assign', 1), ('admin', 'tasks', 'complete', 1),
    ('admin', 'notifications', 'view', 1), ('admin', 'notifications', 'update', 1),
    ('admin', 'calendar', 'view', 1), ('admin', 'calendar', 'schedule', 1),
    ('admin', 'ai_chat', 'view', 1), ('admin', 'ai_chat', 'ask', 1),
    ('admin', 'ai_followups', 'view', 1), ('admin', 'ai_followups', 'generate', 1), ('admin', 'ai_followups', 'send', 1), ('admin', 'ai_followups', 'run', 1),
    ('admin', 'workflows', 'view', 1), ('admin', 'workflows', 'manage', 1),
    ('admin', 'campaigns', 'view', 1), ('admin', 'campaigns', 'create', 1), ('admin', 'campaigns', 'update', 1), ('admin', 'campaigns', 'send', 1), ('admin', 'campaigns', 'schedule', 1),
    ('admin', 'communication', 'view', 1), ('admin', 'communication', 'send', 1),
    ('admin', 'whatsapp_messages', 'view', 1),
    ('admin', 'reports', 'view', 1), ('admin', 'reports', 'export', 1),
    ('admin', 'employees', 'view', 1), ('admin', 'employees', 'create', 1), ('admin', 'employees', 'update', 1), ('admin', 'employees', 'delete', 1),
    ('admin', 'settings', 'view', 1), ('admin', 'settings', 'update', 1), ('admin', 'settings', 'manage', 1),
    ('staff', 'dashboard', 'view', 1),
    ('staff', 'leads', 'view', 1), ('staff', 'leads', 'create', 1), ('staff', 'leads', 'update', 1), ('staff', 'leads', 'delete', 0), ('staff', 'leads', 'assign', 0), ('staff', 'leads', 'convert', 1), ('staff', 'leads', 'classify', 1),
    ('staff', 'customers', 'view', 1), ('staff', 'customers', 'create', 0), ('staff', 'customers', 'update', 1), ('staff', 'customers', 'delete', 0), ('staff', 'customers', 'send_review', 1), ('staff', 'customers', 'sync_review', 1),
    ('staff', 'tasks', 'view', 1), ('staff', 'tasks', 'create', 1), ('staff', 'tasks', 'update', 1), ('staff', 'tasks', 'delete', 0), ('staff', 'tasks', 'assign', 0), ('staff', 'tasks', 'complete', 1),
    ('staff', 'notifications', 'view', 1), ('staff', 'notifications', 'update', 1),
    ('staff', 'calendar', 'view', 1), ('staff', 'calendar', 'schedule', 1),
    ('staff', 'ai_chat', 'view', 1), ('staff', 'ai_chat', 'ask', 1),
    ('staff', 'ai_followups', 'view', 1), ('staff', 'ai_followups', 'generate', 1), ('staff', 'ai_followups', 'send', 1), ('staff', 'ai_followups', 'run', 0),
    ('staff', 'workflows', 'view', 0), ('staff', 'workflows', 'manage', 0),
    ('staff', 'campaigns', 'view', 0), ('staff', 'campaigns', 'create', 0), ('staff', 'campaigns', 'update', 0), ('staff', 'campaigns', 'send', 0), ('staff', 'campaigns', 'schedule', 0),
    ('staff', 'communication', 'view', 1), ('staff', 'communication', 'send', 1),
    ('staff', 'whatsapp_messages', 'view', 1),
    ('staff', 'reports', 'view', 0), ('staff', 'reports', 'export', 0),
    ('staff', 'employees', 'view', 0), ('staff', 'employees', 'create', 0), ('staff', 'employees', 'update', 0), ('staff', 'employees', 'delete', 0),
    ('staff', 'settings', 'view', 0), ('staff', 'settings', 'update', 0), ('staff', 'settings', 'manage', 0);

INSERT INTO company_settings
    (
        id,
        tagline,
        about_crm,
        phone,
        gst_number,
        google_review_url,
        google_review_place_id,
        google_review_api_key,
        whatsapp_api_token,
        whatsapp_phone_number_id,
        gmail_address,
        gmail_app_password,
        course_name_options,
        internship_name_options,
        business_service_options
    )
VALUES
    (
        1,
        'AI training, automation and product engineering',
        'Digidara CRM manages leads, customers, tasks, campaigns, communication and revenue reporting for Digidara Technologies.',
        '+91 98765 43210',
        '33ABCDE1234F1Z5',
        'https://g.page/r/CXarerFSXX1qEBM/review',
        '',
        '',
        '',
        '1234567890',
        'info@digidaratechnologies.com',
        '',
        'GenAI Course\nPython Full Stack\nAI Training',
        'AI Internship\nML / Data Science\nWeb Development Internship',
        'AI Product Development\nDigital Marketing\nAI Consulting\nWebsite Development\nSoftware Development'
    )
ON DUPLICATE KEY UPDATE
    tagline = VALUES(tagline),
    about_crm = VALUES(about_crm),
    phone = VALUES(phone),
    gst_number = VALUES(gst_number),
    google_review_url = VALUES(google_review_url),
    course_name_options = VALUES(course_name_options),
    internship_name_options = VALUES(internship_name_options),
    business_service_options = VALUES(business_service_options);

-- Integration credentials are intentionally not stored in source control.
-- These inactive records provide the correct JSON structure for a new setup.
-- Enter secrets in CRM Settings > Company & Integrations, environment
-- variables, or update the matching database rows during deployment.
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

-- Notification and task assignment flow:
-- Notifications are shown only in the authenticated topbar bell. The
-- backend API remains at /api/notifications for list/read operations.
--
-- The Communication page sends permission-scoped single and bulk customer
-- WhatsApp messages and records each delivery in message_logs.
--
-- When a task is created or reassigned from the CRM, the backend writes:
-- 1. notifications.type = 'task_assigned' for the assigned user
-- 2. message_logs.recipient_type = 'employee' with template_used = 'Task assignment'
--
-- The topbar bell reads only the logged-in user's notifications and uses
-- the user/read/created composite index for recent and unread views.

-- Quick check after running:
-- SHOW DATABASES;
-- USE digidara_crm12;
-- SHOW TABLES;
-- SELECT id, name, email, role FROM users;
 
