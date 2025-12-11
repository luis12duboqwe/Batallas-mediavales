from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Batalla Medieval"
    secret_key: str = "supersecretkey"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./batalla_medieval.db"
    protection_hours: int = 48
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_email: str = ""

    class Config:
        env_file = ".env"


def get_settings() -> Settings:
    return Settings()
