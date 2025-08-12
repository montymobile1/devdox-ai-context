from pydantic import Field, validator
from typing import Any, Dict, ClassVar, Optional
from enum import Enum

from pydantic_settings import BaseSettings


search_path = "vault,public"


class GitHosting(str, Enum):
    GITLAB = "gitlab"
    GITHUB = "github"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    # Application
    app_name: str = "DevDox AI Context Queue Worker"
    Environment: str = "development"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    version: str = "0.0.1"

    # Database
    DB_MAX_CONNECTIONS: int = Field(default=20, ge=1, le=100)
    DB_MIN_CONNECTIONS: int = Field(default=5, ge=1, le=20)
    IS_PRODUCTION: bool = Field(
        default=False, description="Whether the application is running in production"
    )

    # Vector Store - Supabase
    SUPABASE_URL: str = Field(..., description="Supabase instance URL")
    SUPABASE_KEY: str = Field(..., description="Supabase service key")
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-ada-002", description="Embedding model to use"
    )
    vector_dimensions: int = Field(default=1536, ge=256, le=4096)

    # Database Connection Method
    SUPABASE_REST_API: bool = Field(
        default=False, description="Use REST API instead of direct DB connection"
    )

    # Direct PostgreSQL Connection (when SUPABASE_REST_API=False)
    SUPABASE_HOST: str = Field(default="localhost", description="PostgreSQL host")
    SUPABASE_USER: str = Field(default="postgres", description="PostgreSQL user")
    SUPABASE_PASSWORD: str = Field(..., description="PostgreSQL password")
    SUPABASE_PORT: int = Field(default=5432, ge=1, le=65535)
    SUPABASE_DB_NAME: str = Field(default="postgres", description="Database name")

    # External APIs
    TOGETHER_API_KEY: str = Field(..., description="Together AI API key")
    GITLAB_TOKEN: Optional[str] = Field(default=None, description="GitLab API token")

    # Security
    SECRET_KEY: str = Field(..., description="Secret key for encryption")

    # Storage
    BASE_DIR: ClassVar[str] = "app/repos"

    # Queue Configuration
    WORKER_CONCURRENCY: int = Field(
        default=2, ge=1, le=11, description="Number of concurrent workers"
    )
    QUEUE_BATCH_SIZE: int = Field(
        default=10, ge=1, le=100, description="Queue batch processing size"
    )
    QUEUE_POLLING_INTERVAL_SECONDS: int = Field(
        default=5, ge=1, le=60, description="Queue polling interval"
    )
    JOB_TIMEOUT_MINUTES: int = Field(
        default=30, ge=5, le=120, description="Job processing timeout"
    )

    class Config:
        env_file = "app/.env"
        case_sensitive = True
        extra = "ignore"


def get_database_config() -> Dict[str, Any]:
    """
    Returns the appropriate database configuration based on available credentials.
    Uses REST API connection when SUPABASE_REST_API is True, otherwise uses direct PostgreSQL.
    """
    settings_instance = Settings()

    base_credentials = {
        "minsize": settings_instance.DB_MIN_CONNECTIONS,
        "maxsize": settings_instance.DB_MAX_CONNECTIONS,
        "ssl": "require" if settings_instance.IS_PRODUCTION else "prefer",
    }
    if settings_instance.SUPABASE_REST_API:
        # Extract database connection info from Supabase URL
        if not settings_instance.SUPABASE_URL.startswith(
            "https://"
        ) or not settings_instance.SUPABASE_URL.endswith(".supabase.co"):
            raise ValueError(
                f"Invalid Supabase URL format: {settings_instance.SUPABASE_URL}"
            )

        project_id = settings_instance.SUPABASE_URL.replace("https://", "").replace(
            ".supabase.co", ""
        )
        if not project_id:
            raise ValueError("Unable to extract project ID from Supabase URL")

        credentials = {
            **base_credentials,
            "host": f"db.{project_id}.supabase.co",
            "port": 5432,
            "user": "postgres",
            "password": settings_instance.SUPABASE_KEY,
            "database": "postgres",
            "server_settings": {"search_path": search_path},
        }
    else:
        # Direct PostgreSQL connection
        credentials = {
            **base_credentials,
            "host": settings_instance.SUPABASE_HOST,
            "port": settings_instance.SUPABASE_PORT,
            "user": settings_instance.SUPABASE_USER,
            "password": settings_instance.SUPABASE_PASSWORD,
            "database": settings_instance.SUPABASE_DB_NAME,
            "server_settings": {"search_path": search_path},
        }
    return {"engine": "tortoise.backends.asyncpg", "credentials": credentials}


def get_tortoise_config():
    """Get Tortoise ORM configuration"""
    db_config = get_database_config()

    return {
        "connections": {"default": db_config},
        "apps": {
            "models": {
                "models": [
                    "models",
                    "aerich.models",  # Required for aerich migrations
                ],
                "default_connection": "default",
            }
        },
        "use_tz": False,
        "timezone": "UTC",
    }


# Global settings instance
settings = Settings()
TORTOISE_ORM = get_tortoise_config()
