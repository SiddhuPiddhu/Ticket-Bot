CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT PRIMARY KEY,
    locale TEXT NOT NULL DEFAULT 'en-US',
    timezone TEXT NOT NULL DEFAULT 'UTC',
    ticket_counter BIGINT NOT NULL DEFAULT 0,
    transcript_channel_id BIGINT,
    log_channel_id BIGINT,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticket_panels (
    id TEXT PRIMARY KEY,
    panel_id TEXT NOT NULL UNIQUE,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    button_label TEXT NOT NULL,
    button_emoji TEXT NOT NULL,
    button_style TEXT NOT NULL,
    category_map_json TEXT NOT NULL DEFAULT '{}',
    support_role_ids_json TEXT NOT NULL DEFAULT '[]',
    log_channel_id BIGINT,
    transcript_channel_id BIGINT,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ticket_panels_guild_channel
    ON ticket_panels (guild_id, channel_id);

CREATE TABLE IF NOT EXISTS ticket_categories (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL,
    channel_category_id BIGINT,
    support_role_ids_json TEXT NOT NULL DEFAULT '[]',
    modal_questions_json TEXT NOT NULL DEFAULT '[]',
    template_json TEXT NOT NULL DEFAULT '{}',
    priority_default TEXT NOT NULL DEFAULT 'normal',
    tags_default_json TEXT NOT NULL DEFAULT '[]',
    sla_minutes INTEGER NOT NULL DEFAULT 120,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, key)
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    ticket_number BIGINT NOT NULL,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL UNIQUE,
    opener_id BIGINT NOT NULL,
    opener_display TEXT NOT NULL,
    panel_id TEXT,
    category_key TEXT NOT NULL,
    category_channel_id BIGINT,
    status TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    tags_json TEXT NOT NULL DEFAULT '[]',
    form_answers_json TEXT NOT NULL DEFAULT '{}',
    internal_notes_json TEXT NOT NULL DEFAULT '[]',
    claimed_by_id BIGINT,
    claimed_at TIMESTAMP,
    first_response_at TIMESTAMP,
    first_response_by_id BIGINT,
    response_due_at TIMESTAMP,
    close_reason TEXT,
    closed_by_id BIGINT,
    closed_at TIMESTAMP,
    reopened_count INTEGER NOT NULL DEFAULT 0,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_anonymous BOOLEAN NOT NULL DEFAULT FALSE,
    transcript_html_path TEXT,
    transcript_txt_path TEXT,
    soft_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    hard_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    escalation_level INTEGER NOT NULL DEFAULT 0,
    department TEXT,
    feedback_stars INTEGER,
    feedback_text TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_guild_status
    ON tickets (guild_id, status);

CREATE INDEX IF NOT EXISTS idx_tickets_opener_status
    ON tickets (guild_id, opener_id, status);

CREATE TABLE IF NOT EXISTS ticket_participants (
    ticket_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    added_by_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(ticket_id, user_id)
);

CREATE TABLE IF NOT EXISTS ticket_events (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    guild_id BIGINT NOT NULL,
    actor_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket
    ON ticket_events (ticket_id, created_at);

CREATE TABLE IF NOT EXISTS ticket_blacklist (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    until_at TIMESTAMP,
    created_by_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS staff_stats (
    guild_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    tickets_claimed INTEGER NOT NULL DEFAULT 0,
    tickets_closed INTEGER NOT NULL DEFAULT 0,
    total_messages INTEGER NOT NULL DEFAULT 0,
    total_first_response_seconds BIGINT NOT NULL DEFAULT 0,
    first_response_count INTEGER NOT NULL DEFAULT 0,
    warnings_count INTEGER NOT NULL DEFAULT 0,
    last_active_at TIMESTAMP,
    PRIMARY KEY(guild_id, staff_id)
);

CREATE TABLE IF NOT EXISTS ticket_ratings (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL UNIQUE,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    stars INTEGER NOT NULL,
    feedback TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staff_warnings (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    staff_id BIGINT NOT NULL,
    moderator_id BIGINT NOT NULL,
    reason TEXT NOT NULL,
    expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS automation_jobs (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    guild_id BIGINT NOT NULL,
    job_type TEXT NOT NULL,
    run_at TIMESTAMP NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_automation_jobs_status_run_at
    ON automation_jobs (status, run_at);

CREATE TABLE IF NOT EXISTS security_events (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    actor_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_guild_created_at
    ON audit_logs (guild_id, created_at);

CREATE TABLE IF NOT EXISTS ticket_templates (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    category_key TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_by_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS suggestion_items (
    id TEXT PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    ticket_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
