from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Security settings
    MAX_REQUEST_SIZE: int = 10 * 1024 * 1024  # 10MB
    PASSWORD_MIN_LENGTH: int = 8
    MAX_LOGIN_ATTEMPTS: int = 5
    
    # Email settings
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str
    SMTP_FROM_NAME: str = "BridgeAI"
    # AI settings
    GROQ_API_KEY: str
    
    # LLM Model Configuration
    # Default model for all AI operations (can be overridden per component)
    LLM_DEFAULT_MODEL: str = "llama-3.3-70b-versatile"
    
    # Component-specific model configurations
    LLM_CLARIFICATION_MODEL: str = "llama-3.3-70b-versatile"
    LLM_CLARIFICATION_TEMPERATURE: float = 0.3
    LLM_CLARIFICATION_MAX_TOKENS: int = 2048
    
    LLM_TEMPLATE_FILLER_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TEMPLATE_FILLER_TEMPERATURE: float = 0.2
    LLM_TEMPLATE_FILLER_MAX_TOKENS: int = 4096
    
    LLM_SUGGESTIONS_MODEL: str = "llama-3.3-70b-versatile"
    LLM_SUGGESTIONS_TEMPERATURE: float = 0.7
    LLM_SUGGESTIONS_MAX_TOKENS: int = 2000
    
    # ChromaDB settings
    CHROMA_DB_PATH: str = "./chroma_db"
    CHROMA_COLLECTION_NAME: str = "project_memories"
    EMBEDDING_MODEL: str = "openai"  # or "default" for Chroma's default
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()