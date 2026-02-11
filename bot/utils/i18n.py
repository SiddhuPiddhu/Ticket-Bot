from __future__ import annotations

import json
from pathlib import Path


class I18N:
    def __init__(self, base_dir: Path, default_locale: str) -> None:
        self.base_dir = base_dir
        self.default_locale = default_locale
        self._messages: dict[str, dict[str, str]] = {}

    def load_locale(self, locale: str) -> None:
        path = self.base_dir / f"{locale}.json"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            self._messages[locale] = {str(k): str(v) for k, v in payload.items()}

    def t(self, key: str, locale: str | None = None, **kwargs: object) -> str:
        locale_key = locale or self.default_locale
        if locale_key not in self._messages:
            self.load_locale(locale_key)
        if self.default_locale not in self._messages:
            self.load_locale(self.default_locale)
        template = self._messages.get(locale_key, {}).get(
            key, self._messages.get(self.default_locale, {}).get(key, key)
        )
        return template.format(**kwargs)
