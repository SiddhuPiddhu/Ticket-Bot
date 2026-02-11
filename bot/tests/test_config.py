from __future__ import annotations

from pathlib import Path

from core.config import load_config


def test_load_config_reads_yaml(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        """
discord:
  token: test-token
  prefix: "?"
database:
  url: "sqlite:///./data/test.db"
ticket_panels: []
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    cfg = load_config(config_path)

    assert cfg.discord.token == "test-token"
    assert cfg.discord.prefix == "?"
    assert cfg.database.url.startswith("sqlite:///")


def test_env_overrides_token(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        """
discord:
  token: yaml-token
ticket_panels: []
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DISCORD_TOKEN", "env-token")
    cfg = load_config(config_path)
    assert cfg.discord.token == "env-token"
