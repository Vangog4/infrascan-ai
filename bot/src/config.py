from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    admin_ids: list[int] = []
    employee_tg_ids: list[int] = []
    log_level: str = "INFO"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    # Optional fallback model used after the primary model exhausts retries on
    # transient errors. Read from env GEMINI_FALLBACK_MODEL; empty/None = disabled.
    gemini_fallback_model: str | None = None
    gemini_stub: bool = False  # True → return hardcoded demo responses (no API call)

    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""
    odoo_api_key: str = ""  # Bearer token for JSON-2 API (Odoo 19)

    redis_url: str = "redis://infrascan-ai_redis:6379/0"

    # Freemium
    free_daily_scans: int = 3
    premium_price_stars: int = 150  # ~$1.5/month
    premium_duration_days: int = 30

    # Webhook (leave empty to use long-polling)
    webhook_url: str = ""  # e.g. https://infrascan-ai.ru/bot/webhook
    webhook_path: str = "/bot/webhook"
    webhook_secret: str = ""  # random string; required when webhook_url is set
    webhook_port: int = 8080

    # Logging: "json" for structured output, "text" for human-readable
    log_format: str = "json"

    # Telegram WebApp URL (served via Odoo static or CDN)
    webapp_url: str = "https://infrascan-ai.ru/infrascan_ai/static/src/webapp/index.html"

    sentry_dsn: str = ""


settings = Settings()
