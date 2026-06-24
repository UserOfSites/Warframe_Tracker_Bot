import logging
import tomllib
from functools import lru_cache
from importlib import resources
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_LOCALES: tuple[str, ...] = ("en", "it")
DEFAULT_LOCALE: str = "en"


def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    elif isinstance(value, str):
        out[prefix] = value
    else:
        out[prefix] = str(value)


@lru_cache(maxsize=None)
def _load_catalog(locale: str) -> dict[str, str]:
    try:
        raw = (
            resources.files("titania.i18n").joinpath(f"{locale}.toml").read_bytes()
        )
    except FileNotFoundError:
        log.warning("missing i18n catalog for locale %r", locale)
        return {}
    data = tomllib.loads(raw.decode("utf-8"))
    flat: dict[str, str] = {}
    _flatten("", data, flat)
    return flat


class Translator:
    """Looks up template strings in a TOML catalog, with English fallback.

    Keys use dotted notation matching the TOML table hierarchy, e.g.
    `embed.section.normal`. Templates use `.format(**kwargs)`.
    """

    def __init__(self, locale: str) -> None:
        self.locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
        self._catalog = _load_catalog(self.locale)
        self._fallback = _load_catalog(DEFAULT_LOCALE) if self.locale != DEFAULT_LOCALE else {}

    def t(self, key: str, **kwargs: Any) -> str:
        text = self._catalog.get(key) or self._fallback.get(key) or key
        return text.format(**kwargs) if kwargs else text
