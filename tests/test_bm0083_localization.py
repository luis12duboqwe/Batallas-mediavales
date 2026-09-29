import httpx

from app import schemas
from app.services.i18n import DEFAULT_LANGUAGE, available_languages, get_translator, normalize_language


def test_spanish_is_the_only_production_language():
    assert DEFAULT_LANGUAGE == "es"
    assert available_languages() == ["es"]
    assert normalize_language("en-US") == "es"
    assert normalize_language("fr") == "es"


def test_legacy_client_language_values_are_normalized():
    created = schemas.UserCreate(
        username="legacy-language",
        email="legacy-language@example.com",
        password="Castle12345",
        language="en",
    )
    updated = schemas.UserUpdate(language="en-US")

    assert created.language == "es"
    assert updated.language == "es"


def test_unsupported_translator_uses_spanish_catalog():
    spanish = get_translator("es")
    legacy_english = get_translator("en")

    assert legacy_english("wood", "resources") == spanish("wood", "resources")


def test_accept_language_english_falls_back_to_spanish(client: httpx.Client):
    response = client.get("/health", headers={"Accept-Language": "en-US,en;q=0.9"})

    assert response.status_code == 200
    assert response.headers["Content-Language"] == "es"
