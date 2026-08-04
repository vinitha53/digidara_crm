USE digidara_crm12;

ALTER TABLE ai_interactions ADD COLUMN model VARCHAR(100) NULL AFTER intent;
ALTER TABLE ai_interactions ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'success' AFTER model;
ALTER TABLE ai_interactions ADD COLUMN sources VARCHAR(255) NULL AFTER status;

UPDATE role_permissions SET page_key = 'ai_chat' WHERE page_key = 'ai_copilot';
