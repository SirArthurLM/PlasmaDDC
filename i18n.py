"""Small English/Spanish catalog shared by the GUI and backend.

English messages are the source text and fallback. Keep placeholders identical
in translations; format dynamic values after translation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

LANGUAGE_CHOICES = ("system", "en", "es")
SPANISH = json.loads(
    (Path(__file__).parent / "translations" / "es.json").read_text(encoding="utf-8")
)


def resolve_language(preference: str, system_locale: str) -> str:
    """Follow supported locales; unsupported or unavailable locales use English."""
    if preference in ("en", "es"):
        return preference
    code = system_locale.lower().replace("-", "_").split("_")[0].split(".")[0]
    return "es" if code == "es" else "en"


class LanguageManager:
    def __init__(self) -> None:
        self.preference = "system"
        self.system_locale = (
            os.environ.get("LC_ALL")
            or os.environ.get("LC_MESSAGES")
            or os.environ.get("LANG")
            or "en"
        )

    def configure(self, preference: str, system_locale: str) -> None:
        self.preference = preference if preference in LANGUAGE_CHOICES else "system"
        self.system_locale = system_locale

    @property
    def language(self) -> str:
        return resolve_language(self.preference, self.system_locale)

    def translate(self, message: str) -> str:
        if self.language == "es":
            return SPANISH.get(message, message)
        return message


language_manager = LanguageManager()


def _(message: str) -> str:
    return language_manager.translate(message)
