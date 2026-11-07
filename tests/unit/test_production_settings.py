from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings_error_message

_ROOT = Path(__file__).resolve().parents[2]
_JWT = "production-jwt-secret-value-0123456789abcdef"
_PASSWORD = "production-db-password-0123456789"


def _production(**overrides: str) -> Settings:
    values = {
        "environment": "production",
        "database_url": (
            f"postgresql+psycopg://finsight:{_PASSWORD}@db:5432/finsight"
        ),
        "jwt_secret_key": _JWT,
        "cors_origins": "https://portfolytix.example",
        "ai_provider": "local",
        "ai_api_key": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_local_settings_keep_development_defaults() -> None:
    settings = Settings(_env_file=None, environment="local")
    assert settings.jwt_secret_key == (
        "dev-only-change-this-secret-at-least-32-bytes"
    )
    assert "finsight:finsight@" in settings.database_url


def test_production_accepts_unique_secrets_and_https_origins() -> None:
    settings = _production(
        cors_origins="https://portfolytix.example, https://preview.example"
    )
    assert settings.environment == "production"
    assert settings.jwt_secret_key == _JWT


def test_production_rejects_development_and_placeholder_secrets() -> None:
    with pytest.raises(ValidationError):
        _production(
            jwt_secret_key="dev-only-change-this-secret-at-least-32-bytes"
        )
    with pytest.raises(ValidationError):
        _production(jwt_secret_key="short-secret")
    with pytest.raises(ValidationError):
        _production(
            jwt_secret_key="replace-with-a-random-secret-at-least-32-characters"
        )
    with pytest.raises(ValidationError):
        _production(
            database_url="postgresql+psycopg://finsight:finsight@db:5432/finsight"
        )
    with pytest.raises(ValidationError):
        _production(
            database_url=(
                "postgresql+psycopg://finsight:"
                "replace-with-a-unique-password@db:5432/finsight"
            )
        )


def test_production_requires_explicit_https_origins() -> None:
    with pytest.raises(ValidationError):
        _production(cors_origins="http://localhost:3000")
    with pytest.raises(ValidationError):
        _production(cors_origins="*")
    with pytest.raises(ValidationError):
        _production(cors_origins="")


def test_remote_model_requires_a_real_key_on_the_api_host() -> None:
    with pytest.raises(ValidationError):
        _production(ai_provider="openai", ai_api_key="")
    with pytest.raises(ValidationError):
        _production(
            ai_provider="openai",
            ai_api_key="replace-with-the-backend-only-key",
        )
    settings = _production(
        ai_provider="openai",
        ai_api_key="test-provider-key-not-a-real-secret",
    )
    assert settings.ai_provider == "openai"


def test_startup_error_omits_submitted_secret_values() -> None:
    weak_jwt = "q" * 8
    with pytest.raises(ValidationError) as caught:
        _production(jwt_secret_key=weak_jwt)
    message = settings_error_message(caught.value)
    assert weak_jwt not in message
    assert "JWT_SECRET_KEY" in message


def test_production_compose_keeps_data_stores_private() -> None:
    text = (_ROOT / "docker-compose.prod.yml").read_text()
    assert "127.0.0.1:8000:8000" in text
    assert "15432:5432" not in text
    assert "16379:6379" not in text
    assert ":-finsight" not in text
    assert "dev-only-change-this-secret" not in text
    assert "NEXT_PUBLIC_API_URL" not in text
    assert "\n  web:" not in text
    assert 'command: ["alembic", "upgrade", "head"]' in text
    assert "finsight_pg:" in text
    assert "service_completed_successfully" in text
    assert 'restart: "no"' in text
    assert "unless-stopped" in text
    example = (_ROOT / ".env.production.example").read_text()
    assert "sk-" not in example
    assert "finsight:finsight" not in example
    assert "POSTGRES_PASSWORD=replace-with-a-unique-password" in example
    ignored = (_ROOT / ".gitignore").read_text()
    assert ".env.production\n" in ignored
