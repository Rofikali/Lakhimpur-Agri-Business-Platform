from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env.local",
        extra="ignore",
    )


settings = Settings()
