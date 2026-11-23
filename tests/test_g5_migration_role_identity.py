"""G5 split DB role validation: static and adversarial, no real credentials."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.g5_migration_role_identity import RoleSplitError, SplitRoles, validate_split


@pytest.fixture
def values():
    return {
        "POSTGRES_DB": "game_db",
        "POSTGRES_USER": "game_admin",
        "POSTGRES_PASSWORD": "admin-credential-synthetic",
        "DB_URL": "postgresql+psycopg://game_app:game-credential-synthetic@database:5432/game_db",
        "G5_MIGRATION_DB_URL": (
            "postgresql+psycopg://game_admin:admin-credential-synthetic@database:5432/game_db"
        ),
    }


def test_dedicated_app_and_maintenance_urls_are_accepted(values):
    assert validate_split(values) == SplitRoles("game_app", "game_admin", "game_db")


@pytest.mark.parametrize("field,substitution", [
    ("POSTGRES_DB", "another_db"),
    ("POSTGRES_DB", "game_db;drop"),
    ("POSTGRES_USER", "game_app"),
    ("POSTGRES_USER", "pg_write_all_data"),
    ("POSTGRES_USER", "some;statement"),
    ("DB_URL", "postgresql+psycopg://game_admin:admin-credential-synthetic@database:5432/game_db"),
    ("DB_URL", "postgresql+psycopg://postgres:x@database:5432/game_db"),
    ("DB_URL", "postgresql+psycopg://pg_read_all_data:x@database:5432/game_db"),
    ("DB_URL", "postgresql+psycopg://game_app:x@other-server:5432/game_db"),
    ("DB_URL", "postgresql+psycopg://game_app:x@database:5433/game_db"),
    ("DB_URL", "postgresql+psycopg://game_app:x@database:5432/other_db"),
    ("DB_URL", "postgresql+psycopg://game_app:x@database/game_db?options=-c%20search_path%3Dpublic"),
    ("DB_URL", "postgresql+psycopg://game_app:x@database/game_db#fragment"),
    ("DB_URL", "mysql://game_app:x@database/game_db"),
    ("DB_URL", "postgresql+psycopg://game_app:x@database:bad/game_db"),
    ("DB_URL", "postgresql+psycopg://game_app:x@database:5432/game_db\nDB_URL=override"),
    ("DB_URL", "postgresql+psycopg://game_app:$APP_PASSWORD@database/game_db"),
    ("DB_URL", "postgresql+psycopg://game_app:admin-credential-synthetic@database/game_db"),
    ("G5_MIGRATION_DB_URL", ""),
    ("G5_MIGRATION_DB_URL", "postgresql+psycopg://game_app:x@database/game_db"),
    ("G5_MIGRATION_DB_URL", "postgresql+psycopg://game_admin:bad-password@database/game_db"),
    ("G5_MIGRATION_DB_URL", "postgresql+psycopg://game_admin:x@different-host/game_db"),
    ("G5_MIGRATION_DB_URL", "postgresql+psycopg://game_admin:x@database/game_db?target_session_attrs=read-write"),
    ("G5_MIGRATION_DB_URL", "postgresql+psycopg://game_admin:$ADMIN_PASSWORD@database/game_db"),
    ("POSTGRES_PASSWORD", ""),
])
def test_misrouted_credentials_and_injection_are_refused_without_secret_leaks(values, field, substitution):
    values[field] = substitution
    with pytest.raises(RoleSplitError) as error:
        validate_split(values)
    rendered = str(error.value)
    assert "synthetic" not in rendered
    assert "postgresql+psycopg" not in rendered


@pytest.mark.parametrize("url_field,raw_url", [
    ("DB_URL", "postgresql+psycopg://game_app:part1@part2@database:5432/game_db"),
    ("G5_MIGRATION_DB_URL",
     "postgresql+psycopg://game_admin:part1@part2@database:5432/game_db"),
])
def test_raw_at_sign_in_password_never_certifies_ambiguous_destination(
    values, url_field, raw_url
):
    # urllib.split.hostname uses last @, SQLAlchemy's URL parser uses first.
    # Both user-info URLs must refuse unsafe ambiguous delimiters.
    values[url_field] = raw_url
    if url_field == "G5_MIGRATION_DB_URL":
        values["POSTGRES_PASSWORD"] = "part1@part2"
    with pytest.raises(RoleSplitError, match="ambiguous user-info"):
        validate_split(values)


@pytest.mark.parametrize("url_field", ["DB_URL", "G5_MIGRATION_DB_URL"])
def test_percent_encoded_at_in_password_can_be_unambiguously_routed(values, url_field):
    if url_field == "DB_URL":
        values[url_field] = (
            "postgresql+psycopg://game_app:part1%40part2@database:5432/game_db"
        )
    else:
        values[url_field] = (
            "postgresql+psycopg://game_admin:part1%40part2@database:5432/game_db"
        )
        values["POSTGRES_PASSWORD"] = "part1@part2"
    result = validate_split(values)
    assert result.application == "game_app"
    assert result.maintenance == "game_admin"


def test_missing_and_malformed_env_values_are_refused(values):
    for field in values:
        missing = dict(values)
        missing.pop(field)
        with pytest.raises(RoleSplitError):
            validate_split(missing)
    with pytest.raises(RoleSplitError):
        validate_split(None)


@pytest.mark.parametrize("bad", ["postgresql+psycopg://game_app:@database/game_db",
                                   "postgresql+psycopg://game_app:x@database:99999/game_db",
                                   "postgresql+psycopg://game_app:x@database/game_db?sslmode=require"])
def test_app_role_requires_same_postgres_target_and_explicit_password(values, bad):
    values["DB_URL"] = bad
    with pytest.raises(RoleSplitError):
        validate_split(values)


def test_migration_overlay_changes_only_one_shot_services():
    overlay = (Path(__file__).resolve().parents[1] /
               "docker-compose.g5-migration.yml").read_text()
    assert "services:" in overlay
    assert "  migrate:" in overlay
    assert "  seed:" in overlay
    assert "      DATABASE_URL: ${G5_MIGRATION_DB_URL:?" in overlay
    assert "  backend:" not in overlay
    assert "  worker:" not in overlay
    assert overlay.count("      DATABASE_URL:") == 2
