from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # API Gateway settings
    GATEWAY_UPSTREAM: str | None = None
    RATE_LIMIT_REQUESTS: int = 100  # number of requests
    RATE_LIMIT_PERIOD: int = 60  # period in seconds

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
