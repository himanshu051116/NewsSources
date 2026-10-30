import pytest
from pydantic import ValidationError

from newsintel.core.config import Settings


def test_ai_is_disabled_by_default() -> None:
    assert Settings(_env_file=None).ai_provider == "disabled"


def test_production_rejects_unsafe_defaults() -> None:
    with pytest.raises(ValidationError, match="unsafe production defaults"):
        Settings(environment="production", _env_file=None)



def _safe_production_settings(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://newsintel:strong-password@db.internal:5432/newsintel",
        "public_base_url": "https://news.example.com",
        "object_store_secret_key": "a" * 32,
        "crawler_user_agent": "NewsIntelligenceBot/0.2 (+https://example.com/crawler)",
        "auth_mode": "jwt",
        "auth_session_secret": "s" * 32,
        "auth_cookie_secure": True,
        "raw_artifact_store_backend": "s3",
        "auth_jwt_issuer": "https://identity.example.com",
        "auth_jwt_audience": "newsintel",
        "auth_jwt_jwks_url": "https://identity.example.com/.well-known/jwks.json",
        "auth_jwt_algorithms": "RS256",
        "_env_file": None,
    }
    values.update(overrides)
    return values


def test_production_rejects_mixed_symmetric_and_asymmetric_jwt_algorithms() -> None:
    with pytest.raises(ValidationError, match="auth_jwt_algorithms"):
        Settings(**_safe_production_settings(auth_jwt_algorithms="HS256,RS256"))


def test_production_rejects_short_hs256_secret() -> None:
    weak_secret = "".join(("s", "h", "o", "r", "t"))
    with pytest.raises(ValidationError, match="auth_jwt_hs256_secret"):
        Settings(
            **_safe_production_settings(
                auth_jwt_algorithms="HS256",
                auth_jwt_jwks_url=None,
                auth_jwt_hs256_secret=weak_secret,
            )
        )


def test_production_accepts_strong_hs256_configuration() -> None:
    settings = Settings(
        **_safe_production_settings(
            auth_jwt_algorithms="hs256",
            auth_jwt_jwks_url=None,
            auth_jwt_hs256_secret="h" * 32,
        )
    )

    assert settings.auth_algorithm_list == ["HS256"]


def test_production_rejects_default_database_credentials() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(**_safe_production_settings(
            database_url="postgresql+asyncpg://newsintel:newsintel@localhost:5432/newsintel"
        ))


def test_production_requires_https_public_base_url() -> None:
    with pytest.raises(ValidationError, match="public_base_url"):
        Settings(**_safe_production_settings(public_base_url="http://news.example.com"))


def test_env_local_overrides_env(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NEWSINTEL_DEV_AUTH_BYPASS_ENABLED", raising=False)
    monkeypatch.delenv("NEWSINTEL_API_PORT", raising=False)
    (tmp_path / ".env").write_text(
        "NEWSINTEL_DEV_AUTH_BYPASS_ENABLED=false\nNEWSINTEL_API_PORT=8010\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "NEWSINTEL_DEV_AUTH_BYPASS_ENABLED=true\nNEWSINTEL_API_PORT=9001\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.dev_auth_bypass_enabled is True
    assert settings.api_port == 9001
