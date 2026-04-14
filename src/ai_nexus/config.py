"""
Configuration management for AI Nexus.

Uses pydantic-settings for environment-based configuration with validation.
All settings can be overridden via environment variables with the AI_NEXUS_ prefix.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings for AI Nexus.

    Attributes:
        host: Service bind address for FastAPI server
        port: Service port for FastAPI server
        sqlite_path: File path to SQLite database (relative or absolute)
        mem0_api_url: Base URL for Mem0 search service
        openviking_url: Base URL for OpenViking search service
        anthropic_api_key: API key for Anthropic Claude (required for AI features)
        feishu_app_id: Feishu/Lark app ID for document ingestion
        feishu_app_secret: Feishu/Lark app secret for document ingestion
        feishu_base_url: Base URL for Feishu Open API

    Environment variables:
        All settings can be overridden via environment variables prefixed with
        AI_NEXUS_, e.g., AI_NEXUS_HOST, AI_NEXUS_PORT.
    """

    # Service Configuration
    host: str = "0.0.0.0"
    port: int = 8015

    # Database Configuration
    sqlite_path: str = "data/ai_nexus.db"

    # Search Provider Configuration
    mem0_api_url: str = "http://localhost:8080"
    openviking_url: str = "http://localhost:1933"

    # API Keys
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096

    # Refund Configuration (部分退款上限比例)
    refund_max_ratio: float = 1.0

    # Feishu/Lark Integration
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_base_url: str = "https://open.feishu.cn/open-apis"

    model_config = SettingsConfigDict(
        env_prefix="AI_NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
