from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    MODEL_NAME: str = "llama-3.3-70b-versatile"
    DB_NAME: str = "food_ai"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    ENTREZ_EMAIL: str = ""
    SERPAPI_KEY: str = ""
    USDA_API_KEY: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    ADMIN_PASSWORD: str = "change-me"
    SESSION_TTL_SECONDS: int = 14400

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
