from decimal import Decimal
from functools import lru_cache
from typing import Self
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known development and example values. Production must not sign tokens
# or open the database with any of these.
_DEV_JWT_SECRET = "dev-only-change-this-secret-at-least-32-bytes"
_DEV_DATABASE_PASSWORD = "finsight"
_PLACEHOLDER_PREFIX = "replace-with"
_KNOWN_WEAK_SECRETS = {
    _DEV_DATABASE_PASSWORD,
    _DEV_JWT_SECRET,
    "replace-with-a-long-random-secret",
    "ollama",
}


def _database_password(database_url: str) -> str:
    password = urlsplit(database_url).password
    if password is None:
        return ""
    return unquote(password)


def _is_weak_secret(value: str, *, minimum: int) -> bool:
    text = value.strip()
    if len(text) < minimum or len(set(text)) < 8:
        return True
    folded = text.lower()
    return folded.startswith(_PLACEHOLDER_PREFIX) or folded in _KNOWN_WEAK_SECRETS


def _require_https_origins(value: str) -> None:
    origins = [item.strip() for item in value.split(",") if item.strip()]
    if not origins or any(
        "*" in origin or not origin.startswith("https://") for origin in origins
    ):
        raise ValueError(
            "CORS_ORIGINS must list explicit https:// origins in production"
        )


def settings_error_message(exc: ValidationError) -> str:
    """Return validation text without the submitted secret values."""
    parts = []
    for error in exc.errors():
        message = str(error.get("msg", "invalid settings"))
        parts.append(message.removeprefix("Value error, "))
    return "; ".join(parts)


class Settings(BaseSettings):
    # Runtime settings come from environment variables and optional .env.
    """Runtime settings loaded from environment variables (and optional `.env`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Portfolytix"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://finsight:finsight@localhost:15432/finsight"
    )
    # Annual decimal, e.g. 0.05 = 5%. Used only for Sharpe. Not a forecast.
    risk_free_rate: Decimal = Decimal("0.05")
    trading_days_per_year: int = 252
    # Market-data pipeline. MARKET_DATA_PROVIDER selects the adapter.
    # MARKET_DATA_API_KEY does not. yahoo is an unofficial daily-chart
    # source: delayed closes, not live quotes, and not a licensed feed.
    market_data_provider: str = "stooq"
    market_data_api_key: str = ""
    # Published S&P 500 constituent file. Not every listed stock, and not
    # an official S&P Global feed.
    universe_code: str = "sp500"
    universe_source_url: str = (
        "https://raw.githubusercontent.com/datasets/"
        "s-and-p-500-companies/master/data/constituents.csv"
    )
    # Background jobs. Tests set SCHEDULER_ENABLED=false so TestClient
    # does not start APScheduler or call a live vendor.
    scheduler_enabled: bool = True
    # 22:00 UTC is after the US cash close in both EST and EDT.
    market_data_cron: str = "0 22 * * *"
    market_data_lookback_days: int = 7
    # Portfolio analytics loads a year of daily closes when a holding has
    # only a short stored sample. Tests turn this off so they stay offline.
    portfolio_history_backfill: bool = True
    # One run cannot walk the whole universe or a multi-decade window.
    market_data_max_securities: int = 25
    market_data_max_window_days: int = 1825
    market_data_max_attempts: int = 3
    market_data_retry_backoff_seconds: float = 0.0
    market_data_pause_seconds: float = 0.0
    # Alpha Vantage "full" is the entire daily history. Compact is enough
    # unless an older window is explicitly allowed.
    market_data_allow_full_history: bool = False
    job_stale_after_seconds: int = 3600
    # Redis is an acceleration layer only. PostgreSQL remains authoritative.
    cache_enabled: bool = True #enable caching to speed up the application
    redis_url: str = "redis://localhost:16379/0" #Redis URL for the cache
    cache_key_prefix: str = "finsight" #prefix for the cache keys
    analytics_cache_ttl_seconds: int = 300 #time to live for the analytics cache
    screening_cache_ttl_seconds: int = 300 #time to live for the screening cache
    redis_socket_timeout_seconds: float = 0.2 #timeout for the Redis connection
    # Phase 10 authentication. Override the development secret outside local.
    jwt_secret_key: str = "dev-only-change-this-secret-at-least-32-bytes"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "finsight"
    jwt_access_token_minutes: int = 30
    # Phase 12. local uses rules and a template. openai defaults to Responses.
    # The model never receives a database connection.
    ai_provider: str = "local"
    ai_openai_api: str = "responses"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = 20.0
    # If the remote model is unavailable, retain an evidence-only local answer.
    ai_fallback_to_local: bool = True
    # Optional cited web research. Search results become bounded evidence
    # before the language model runs; the model never receives an HTTP tool.
    web_research_provider: str = "none"
    web_research_api_key: str = ""
    web_research_max_results: int = 5
    web_research_timeout_seconds: float = 15.0
    # Live quotes are current state in Redis. Daily bars stay in PostgreSQL.
    # simulator needs no key. finnhub streams trades. alpha_vantage polls
    # GLOBAL_QUOTE (delayed unless the key has a realtime entitlement).
    quote_provider: str = "simulator"
    quote_symbols: str = "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA"
    quote_poll_seconds: float = 2.0
    quote_ttl_seconds: int = 30
    # Yahoo marks share the live-quote keys. 45s is long enough that a
    # dashboard refresh does not call Yahoo again, and short enough that
    # the next poll still replaces the print.
    provider_mark_ttl_seconds: int = 45
    provider_quote_workers: int = 4
    # A provider tick older than this can no longer be presented as real-time.
    quote_stale_after_seconds: float = 15.0
    # Delayed quotes go stale when Portfolytix has not refreshed them. The
    # vendor print can be the previous session without being a failure.
    quote_delayed_stale_after_seconds: float = 120.0
    # Daily bars older than this many sessions are stale. Weekends and
    # NYSE holidays are not sessions.
    history_stale_after_business_days: int = 3
    quote_worker_heartbeat_ttl_seconds: int = 30
    # Watchlist names above this count are not subscribed in one worker pass.
    quote_max_symbols: int = 50
    quote_reconnect_seconds: float = 2.0
    quote_symbol_refresh_seconds: float = 30.0
    # GLOBAL_QUOTE stays delayed unless the key's entitlement is real-time.
    alpha_vantage_realtime: bool = False
    # Empty follows the quote provider. yahoo needs no key. none stores none.
    news_provider: str = ""
    finnhub_api_key: str = ""
    news_ttl_seconds: int = 900
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Suggestions refresh price, market cap, and P/E from Yahoo's latest quote.
    ideas_live_quotes: bool = True
    # Portfolio marks and new trades use Yahoo's latest published price.
    provider_marks: bool = True

    @model_validator(mode="after")
    def require_production_secrets(self) -> Self:
        # Local and test processes keep the development defaults.
        if self.environment.strip().lower() != "production":
            return self
        if _is_weak_secret(self.jwt_secret_key, minimum=32):
            raise ValueError(
                "JWT_SECRET_KEY must be a unique random secret "
                "of at least 32 characters in production"
            )
        if _is_weak_secret(_database_password(self.database_url), minimum=16):
            raise ValueError(
                "Database password must be a unique value "
                "of at least 16 characters in production"
            )
        _require_https_origins(self.cors_origins)
        if self.ai_provider.strip().lower() == "openai" and _is_weak_secret(
            self.ai_api_key, minimum=20
        ):
            raise ValueError(
                "AI_API_KEY must be set on the API host when AI_PROVIDER is openai"
            )
        if (
            "openrouter.ai" in self.ai_base_url.lower()
            and self.ai_openai_api.strip().lower() != "chat"
        ):
            raise ValueError("OpenRouter requires AI_OPENAI_API=chat")
        if (
            self.web_research_provider.strip().lower() == "tavily"
            and len(self.web_research_api_key.strip()) < 8
        ):
            raise ValueError(
                "WEB_RESEARCH_API_KEY must be set when "
                "WEB_RESEARCH_PROVIDER is tavily"
            )
        if (
            self.quote_provider.strip().lower() == "finnhub"
            and len(self.finnhub_api_key.strip()) < 8
        ):
            raise ValueError(
                "FINNHUB_API_KEY must be set when QUOTE_PROVIDER is finnhub"
            )
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        raise RuntimeError(settings_error_message(exc)) from None


@lru_cache
def get_settings() -> Settings: #dependency function to get the settings
    return load_settings()


settings = get_settings()
