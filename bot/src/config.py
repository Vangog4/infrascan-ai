from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    admin_ids: list[int] = []
    employee_tg_ids: list[int] = []
    log_level: str = "INFO"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""

    redis_url: str = "redis://infrascan-ai_redis:6379/0"


settings = Settings()
