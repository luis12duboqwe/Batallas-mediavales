import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Optional

DEFAULT_LANGUAGE = "en"
LANGUAGE_PATH = Path(__file__).resolve().parent.parent / "config" / "languages"


def _load_language_file(language_code: str) -> Dict[str, Dict[str, str]]:
    language_file = LANGUAGE_PATH / f"{language_code}.json"
    if not language_file.exists():
        return {}
    with language_file.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def get_language(language_code: str) -> Dict[str, Dict[str, str]]:
    return _load_language_file(language_code)


def available_languages() -> list[str]:
    return [path.stem for path in LANGUAGE_PATH.glob("*.json")]


def get_translator(language_code: str, default_language: str = DEFAULT_LANGUAGE) -> Callable[[str, Optional[str]], str]:
    translations = get_language(language_code or default_language)
    fallback_translations = get_language(default_language)

    def translate(key: str, category: Optional[str] = None) -> str:
        category_map = translations.get(category or "", {}) if category else translations
        fallback_map = fallback_translations.get(category or "", {}) if category else fallback_translations

        value = None
        if category:
            value = category_map.get(key)
            if value is None:
                value = fallback_map.get(key)
        else:
            value = translations.get(key)
            if value is None:
                value = fallback_translations.get(key)

        return value or key

    return translate
