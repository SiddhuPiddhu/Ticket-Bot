# Enterprise Discord Ticket Bot

Production-grade Discord ticket bot built with `discord.py` using modular cogs, database abstraction (SQLite/PostgreSQL), persistent UI components, analytics, and security controls.

## Highlights
- Hybrid command architecture (`slash` + `prefix`).
- Persistent panel UI (`Buttons`, `Select`, `Modals`).
- Multi-guild ticket isolation.
- Database abstraction (`sqlite:///` and `postgresql://`).
- Structured logging with rotation.
- Transcript generation (`HTML` + `TXT`).
- Staff performance analytics + exports.
- Anti-spam + anti-raid guardrails.
- Cache abstraction (`memory` + optional Redis).
- Docker + CI ready.

## Architecture
```
bot/
 ├── main.py
 ├── core/
 ├── cogs/
 ├── views/
 ├── database/
 ├── services/
 ├── utils/
 ├── config/
 ├── logs/
 ├── tests/
 ├── requirements.txt
 ├── Dockerfile
 └── README.md
```

### Layering
- `core/`: bootstrapping, config, logging, extension lifecycle, global errors.
- `database/`: DB engine, migrations, repositories, typed models.
- `services/`: ticket, transcript, analytics, automation, security.
- `views/`: Discord UI component implementations.
- `cogs/`: command and event entrypoints.
- `utils/`: decorators, i18n, rate-limiter primitives, embed builders.

## Quick Start
1. Create Discord application + bot and enable intents:
   - `SERVER MEMBERS INTENT`
   - `MESSAGE CONTENT INTENT`
2. Copy env/config:
   - `cp .env.example .env`
   - `cp config/config.example.yaml config/config.yaml`
3. Set secrets in `.env`:
   - `DISCORD_TOKEN`
   - `DISCORD_APPLICATION_ID`
4. Install deps:
   - `pip install -r requirements.txt`
5. Run:
   - `python main.py`

## Prefix + Slash Commands

### Ticket (`/ticket` or `!ticket`)
- `create <category>`
- `claim`
- `unclaim`
- `lock`
- `unlock`
- `close <reason>`
- `reopen`
- `rename <new_name>`
- `transfer <member>`
- `adduser <member>`
- `removeuser <member>`
- `priority <low|normal|high|urgent|critical>`
- `tags <csv>`
- `note <text>`
- `escalate <level>`
- `department <name>`
- `scheduleclose <minutes>`
- `transcript`
- `softdelete`
- `harddelete`
- `forceclose <delete_channel> <reason>`
- `feedback <stars> [message]`
- `info`
- `list`

### Admin (`/admin` or `!admin`)
- `setup`
- `panel_create <panel_id> <channel> <title>`
- `panel_deploy <panel_id>`
- `panel_list`
- `category_upsert <key> <display_name> [sla_minutes]`
- `category_list`
- `set_channels <transcript_channel> <log_channel>`
- `blacklist_add <user> <hours> <reason>`
- `blacklist_remove <user>`
- `reload`
- `config_backup`
- `config_restore <filename>`
- `staff_warn <member> <reason>`

### Analytics (`/analytics` or `!analytics`)
- `dashboard`
- `leaderboard`
- `export`
- `graph`
- `response_times`

### Security (`/security` or `!security`)
- `status`
- `events`
- `lockdown`
- `unlockdown`

## Feature Inventory (100+)
### Ticket Creation
1. Multi-panel support
2. Panel button routing
3. Dropdown category selection
4. Dynamic modal questions
5. Modal validation
6. Custom panel title
7. Custom panel description
8. Custom button label
9. Custom button emoji
10. Custom button style
11. Category-based SLA defaults
12. Category default priority
13. Category default tags
14. Anonymous tickets (config-aware)
15. Per-user ticket cooldown
16. Hourly creation limit
17. Max open tickets per user
18. Blacklist enforcement
19. Category bootstrap defaults
20. Channel naming sanitization
21. Incremental ticket counters
22. Per-guild numbering
23. Category permission mapping
24. Support-role permission grants
25. Captcha challenge mode (optional)

### Ticket Operations
26. Claim ticket
27. Unclaim ticket
28. Lock ticket
29. Unlock ticket
30. Close ticket with reason
31. Reopen ticket
32. Rename channel
33. Transfer ownership
34. Add participant
35. Remove participant
36. Priority updates
37. Tag updates
38. Internal notes
39. Department routing
40. Escalation level
41. Feedback rating storage
42. Staff response tracking
43. First-response timestamp
44. Soft delete marker
45. Hard delete marker
46. Force close workflow
47. Auto-close scheduler
48. Scheduled close worker
49. Ticket info inspection
50. Ticket list view

### Transcript + Records
51. HTML transcript generation
52. TXT transcript generation
53. Attachment links in transcript
54. Per-ticket transcript artifacts
55. Transcript file persistence
56. Transcript auto-save on close
57. Transcript command export
58. Transcript log channel delivery
59. Event timeline storage
60. Audit action logging

### Analytics
61. Dashboard totals
62. Open vs closed split
63. Category analytics
64. Staff leaderboard
65. Avg first response metrics
66. P95 response insight
67. Daily ticket volume aggregation
68. CSV export of ticket data
69. Optional graph generation
70. Staff warnings counter

### Admin + Config
71. Setup wizard UI
72. Panel creation command
73. Panel deployment command
74. Panel listing command
75. Category upsert command
76. Category listing command
77. Runtime extension reload
78. Config backup command
79. Config restore command
80. Guild channel mapping
81. Blacklist add command
82. Blacklist remove command
83. Staff warning command
84. i18n locale loading
85. Env variable support
86. YAML config support
87. Extension auto-loader

### Security + Reliability
88. Anti-raid join-rate detector
89. Anti-spam detector
90. Optional user timeout for spam
91. Security event persistence
92. Security status command
93. Security event query command
94. Lockdown command
95. Unlockdown command
96. Webhook incident logging
97. Centralized command error handling
98. Slash error handling
99. Safe user-facing error responses
100. Rotating log files
101. DB migration runner
102. Cache abstraction fallback
103. Redis support
104. SQLite support
105. PostgreSQL support
106. Multi-guild support
107. Dockerized deployment
108. CI pipeline (ruff + pytest)
109. Unit tests for core logic
110. Modular production folder layout

## Deployment

### Docker
From repo root:
```bash
docker compose up --build -d
```

### VPS (systemd)
1. Provision Python 3.12 + virtualenv.
2. Clone repo and `pip install -r requirements.txt`.
3. Configure `.env` + `config/config.yaml`.
4. Create systemd service:
```ini
[Unit]
Description=Discord Ticket Bot
After=network.target

[Service]
WorkingDirectory=/opt/ticket-bot
ExecStart=/opt/ticket-bot/.venv/bin/python /opt/ticket-bot/main.py
Restart=always
User=bot
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
5. `sudo systemctl enable --now ticket-bot`.

## Scaling Guide
- Use PostgreSQL for durable high-concurrency workloads.
- Enable Redis for distributed rate limiting/caching.
- Increase shard count in config for large guild volumes.
- Offload exports/graphs/transcripts to worker queue if needed.
- Route logs to external sink (ELK/Loki/CloudWatch).
- Place bot in isolated container/network namespace.

## Security Recommendations
- Never commit `.env` or tokens.
- Rotate bot token on suspected leak.
- Restrict command usage with Discord role permissions.
- Use dedicated DB credentials with minimal privileges.
- Enable webhook + DB audit logs.
- Keep dependencies patched and pinned.
- Prefer PostgreSQL + backups in production.

## Testing
Run from `bot/`:
```bash
ruff check .
pytest -q
```

## Notes
- `fastapi` is included as an optional dependency for dashboard/API expansion.
- Existing structure is intentionally modular to support OAuth2 web dashboard and API worker split next.
