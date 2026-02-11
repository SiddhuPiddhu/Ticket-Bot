from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigError(RuntimeError):
    pass


@dataclass(slots=True)
class DiscordConfig:
    token: str
    prefix: str = "!"
    application_id: int | None = None
    sync_commands_on_start: bool = True
    shard_count: int | None = None
    status_text: str = "Ticket operations online"
    activity_type: str = "watching"
    allowed_mentions_everyone: bool = False


@dataclass(slots=True)
class DatabaseConfig:
    url: str = "sqlite:///./data/tickets.db"
    pool_min_size: int = 2
    pool_max_size: int = 10
    timeout_seconds: int = 30


@dataclass(slots=True)
class RedisConfig:
    enabled: bool = False
    url: str = "redis://localhost:6379/0"
    default_ttl: int = 120


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    directory: str = "logs"
    file_name: str = "bot.log"
    max_bytes: int = 10_000_000
    backup_count: int = 10
    json_console: bool = False


@dataclass(slots=True)
class SecurityConfig:
    ticket_creation_cooldown_seconds: int = 20
    ticket_creation_max_per_hour: int = 8
    max_open_tickets_per_user: int = 3
    anti_raid_window_seconds: int = 20
    anti_raid_join_threshold: int = 20
    anti_spam_messages_per_10s: int = 8
    require_ticket_close_reason: bool = True
    enable_captcha: bool = False
    allow_anonymous_tickets: bool = True


@dataclass(slots=True)
class TranscriptConfig:
    html_enabled: bool = True
    txt_enabled: bool = True
    include_attachments: bool = True
    storage_directory: str = "artifacts/transcripts"


@dataclass(slots=True)
class MetricsConfig:
    export_directory: str = "artifacts/exports"
    enable_graphs: bool = True
    scheduled_report_cron: str = "0 8 * * *"
    leaderboard_size: int = 10


@dataclass(slots=True)
class WebhookLogConfig:
    enabled: bool = False
    url: str = ""


@dataclass(slots=True)
class FastApiConfig:
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    jwt_secret: str = ""


@dataclass(slots=True)
class I18NConfig:
    default_locale: str = "en-US"
    supported_locales: list[str] = field(default_factory=lambda: ["en-US"])


@dataclass(slots=True)
class TicketPanelConfig:
    panel_id: str
    guild_id: int
    channel_id: int
    title: str
    description: str
    button_label: str = "Create Ticket"
    button_emoji: str = "🎫"
    button_style: str = "primary"
    category_map: dict[str, int] = field(default_factory=dict)
    support_role_ids: list[int] = field(default_factory=list)
    log_channel_id: int | None = None
    transcript_channel_id: int | None = None


@dataclass(slots=True)
class AppConfig:
    discord: DiscordConfig
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    transcripts: TranscriptConfig = field(default_factory=TranscriptConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    webhook_log: WebhookLogConfig = field(default_factory=WebhookLogConfig)
    fastapi: FastApiConfig = field(default_factory=FastApiConfig)
    i18n: I18NConfig = field(default_factory=I18NConfig)
    enabled_extensions: list[str] = field(
        default_factory=lambda: [
            "cogs.events",
            "cogs.tickets",
            "cogs.analytics",
            "cogs.admin",
            "cogs.security",
        ]
    )
    ticket_panels: list[TicketPanelConfig] = field(default_factory=list)


def _get_env_str(key: str, fallback: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None:
        return fallback
    cleaned = value.strip()
    return cleaned if cleaned else fallback


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
        if node is None:
            return default
    return node


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping")
    return raw


def _load_panel_configs(raw_panels: list[dict[str, Any]]) -> list[TicketPanelConfig]:
    panels: list[TicketPanelConfig] = []
    for row in raw_panels:
        panels.append(
            TicketPanelConfig(
                panel_id=str(row.get("panel_id", "")),
                guild_id=int(row.get("guild_id")),
                channel_id=int(row.get("channel_id")),
                title=str(row.get("title", "Support Panel")),
                description=str(row.get("description", "Open a ticket below.")),
                button_label=str(row.get("button_label", "Create Ticket")),
                button_emoji=str(row.get("button_emoji", "🎫")),
                button_style=str(row.get("button_style", "primary")),
                category_map={
                    str(key): int(val) for key, val in dict(row.get("category_map", {})).items()
                },
                support_role_ids=[int(role_id) for role_id in list(row.get("support_role_ids", []))],
                log_channel_id=(
                    int(row["log_channel_id"])
                    if row.get("log_channel_id") is not None
                    else None
                ),
                transcript_channel_id=(
                    int(row["transcript_channel_id"])
                    if row.get("transcript_channel_id") is not None
                    else None
                ),
            )
        )
    return panels


def load_config(config_path: Path) -> AppConfig:
    env_path = config_path.parent.parent / ".env"
    load_dotenv(env_path)
    raw = _load_yaml(config_path)

    discord_token = _get_env_str("DISCORD_TOKEN", _deep_get(raw, "discord", "token"))
    if not discord_token or "${" in discord_token:
        raise ConfigError("DISCORD_TOKEN is required")

    discord_cfg = DiscordConfig(
        token=discord_token,
        prefix=str(_get_env_str("BOT_PREFIX", _deep_get(raw, "discord", "prefix", default="!"))),
        application_id=(
            int(_get_env_str("DISCORD_APPLICATION_ID"))
            if _get_env_str("DISCORD_APPLICATION_ID")
            else _deep_get(raw, "discord", "application_id")
        ),
        sync_commands_on_start=_as_bool(
            _get_env_str("SYNC_COMMANDS"),
            _as_bool(_deep_get(raw, "discord", "sync_commands_on_start"), True),
        ),
        shard_count=(
            int(_get_env_str("SHARD_COUNT"))
            if _get_env_str("SHARD_COUNT")
            else _deep_get(raw, "discord", "shard_count")
        ),
        status_text=str(_deep_get(raw, "discord", "status_text", default="Ticket operations online")),
        activity_type=str(_deep_get(raw, "discord", "activity_type", default="watching")),
        allowed_mentions_everyone=_as_bool(
            _deep_get(raw, "discord", "allowed_mentions_everyone"), False
        ),
    )

    database_cfg = DatabaseConfig(
        url=str(_get_env_str("DATABASE_URL", _deep_get(raw, "database", "url", default="sqlite:///./data/tickets.db"))),
        pool_min_size=_as_int(
            _get_env_str("DB_POOL_MIN", None),
            _as_int(_deep_get(raw, "database", "pool_min_size"), 2),
        ),
        pool_max_size=_as_int(
            _get_env_str("DB_POOL_MAX", None),
            _as_int(_deep_get(raw, "database", "pool_max_size"), 10),
        ),
        timeout_seconds=_as_int(
            _get_env_str("DB_TIMEOUT_SECONDS", None),
            _as_int(_deep_get(raw, "database", "timeout_seconds"), 30),
        ),
    )

    redis_cfg = RedisConfig(
        enabled=_as_bool(_get_env_str("REDIS_ENABLED"), _as_bool(_deep_get(raw, "redis", "enabled"), False)),
        url=str(_get_env_str("REDIS_URL", _deep_get(raw, "redis", "url", default="redis://localhost:6379/0"))),
        default_ttl=_as_int(
            _get_env_str("REDIS_DEFAULT_TTL", None),
            _as_int(_deep_get(raw, "redis", "default_ttl"), 120),
        ),
    )

    logging_cfg = LoggingConfig(
        level=str(_get_env_str("LOG_LEVEL", _deep_get(raw, "logging", "level", default="INFO"))),
        directory=str(_deep_get(raw, "logging", "directory", default="logs")),
        file_name=str(_deep_get(raw, "logging", "file_name", default="bot.log")),
        max_bytes=_as_int(_deep_get(raw, "logging", "max_bytes"), 10_000_000),
        backup_count=_as_int(_deep_get(raw, "logging", "backup_count"), 10),
        json_console=_as_bool(_deep_get(raw, "logging", "json_console"), False),
    )

    security_cfg = SecurityConfig(
        ticket_creation_cooldown_seconds=_as_int(
            _deep_get(raw, "security", "ticket_creation_cooldown_seconds"), 20
        ),
        ticket_creation_max_per_hour=_as_int(
            _deep_get(raw, "security", "ticket_creation_max_per_hour"), 8
        ),
        max_open_tickets_per_user=_as_int(
            _deep_get(raw, "security", "max_open_tickets_per_user"), 3
        ),
        anti_raid_window_seconds=_as_int(_deep_get(raw, "security", "anti_raid_window_seconds"), 20),
        anti_raid_join_threshold=_as_int(_deep_get(raw, "security", "anti_raid_join_threshold"), 20),
        anti_spam_messages_per_10s=_as_int(_deep_get(raw, "security", "anti_spam_messages_per_10s"), 8),
        require_ticket_close_reason=_as_bool(
            _deep_get(raw, "security", "require_ticket_close_reason"), True
        ),
        enable_captcha=_as_bool(_deep_get(raw, "security", "enable_captcha"), False),
        allow_anonymous_tickets=_as_bool(_deep_get(raw, "security", "allow_anonymous_tickets"), True),
    )

    transcript_cfg = TranscriptConfig(
        html_enabled=_as_bool(_deep_get(raw, "transcripts", "html_enabled"), True),
        txt_enabled=_as_bool(_deep_get(raw, "transcripts", "txt_enabled"), True),
        include_attachments=_as_bool(_deep_get(raw, "transcripts", "include_attachments"), True),
        storage_directory=str(
            _deep_get(raw, "transcripts", "storage_directory", default="artifacts/transcripts")
        ),
    )

    metrics_cfg = MetricsConfig(
        export_directory=str(_deep_get(raw, "metrics", "export_directory", default="artifacts/exports")),
        enable_graphs=_as_bool(_deep_get(raw, "metrics", "enable_graphs"), True),
        scheduled_report_cron=str(_deep_get(raw, "metrics", "scheduled_report_cron", default="0 8 * * *")),
        leaderboard_size=_as_int(_deep_get(raw, "metrics", "leaderboard_size"), 10),
    )

    webhook_cfg = WebhookLogConfig(
        enabled=_as_bool(_deep_get(raw, "webhook_log", "enabled"), False),
        url=str(_get_env_str("WEBHOOK_LOG_URL", _deep_get(raw, "webhook_log", "url", default=""))),
    )

    fastapi_cfg = FastApiConfig(
        enabled=_as_bool(_deep_get(raw, "fastapi", "enabled"), False),
        host=str(_deep_get(raw, "fastapi", "host", default="0.0.0.0")),
        port=_as_int(_deep_get(raw, "fastapi", "port"), 8000),
        jwt_secret=str(_get_env_str("DASHBOARD_JWT_SECRET", _deep_get(raw, "fastapi", "jwt_secret", default=""))),
    )

    i18n_cfg = I18NConfig(
        default_locale=str(_deep_get(raw, "i18n", "default_locale", default="en-US")),
        supported_locales=list(_deep_get(raw, "i18n", "supported_locales", default=["en-US"])),
    )

    enabled_extensions = [
        str(ext)
        for ext in list(
            _deep_get(
                raw,
                "enabled_extensions",
                default=[
                    "cogs.events",
                    "cogs.tickets",
                    "cogs.analytics",
                    "cogs.admin",
                    "cogs.security",
                ],
            )
        )
    ]

    panel_rows = list(_deep_get(raw, "ticket_panels", default=[]))
    panel_cfgs = _load_panel_configs(panel_rows)

    return AppConfig(
        discord=discord_cfg,
        database=database_cfg,
        redis=redis_cfg,
        logging=logging_cfg,
        security=security_cfg,
        transcripts=transcript_cfg,
        metrics=metrics_cfg,
        webhook_log=webhook_cfg,
        fastapi=fastapi_cfg,
        i18n=i18n_cfg,
        enabled_extensions=enabled_extensions,
        ticket_panels=panel_cfgs,
    )
