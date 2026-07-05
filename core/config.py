from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "velar"
    MILVUS_URI: str
    OLLAMA_URI: str | None = None  # optional single host
    OLLAMA_HOSTS: str | None = None  # comma-separated list
    EMBED_MODEL: str
    LLM_MODEL: str
    VELAR_API_KEY: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def ollama_hosts_list(self) -> list[str]:
        """Convert comma-separated hosts into a list."""
        if self.OLLAMA_HOSTS:
            return [h.strip() for h in self.OLLAMA_HOSTS.split(",")]
        return []

settings = Settings()
