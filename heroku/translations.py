# CopyLeft 2026 github.com/i-execute // i_execute.t.me
# Licensed under AGPLv3.

# Single strings source: each module holds ONE class-level `strings` dict,
# accessed as self.strings["key"] (via the Strings wrapper in loader).

import logging
import typing

logger = logging.getLogger(__name__)


def fmt(text: str, kwargs: dict) -> str:
    for key, value in kwargs.items():
        if f"{{{key}}}" in text:
            text = text.replace(f"{{{key}}}", str(value))

    return text


class Strings:
    """Dict-like accessor over a module's own `strings` dict."""

    def __init__(self, mod: typing.Any, translator: typing.Any = None):
        self._base_strings = mod.strings if isinstance(mod.strings, dict) else {}

    def __getitem__(self, key: str) -> str:
        return self._base_strings.get(key, f"Unknown strings: {key}")

    def get(self, key: str, lang: str | None = None) -> str:
        return self[key]

    def __call__(self, key: str, _: typing.Any | None = None) -> str:
        return self[key]

    def __iter__(self):
        return iter(self._base_strings)

    def __contains__(self, key: str) -> bool:
        return key in self._base_strings
