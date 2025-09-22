from pathlib import Path

from pydantic import EmailStr, Field, field_validator, model_validator
from typing import Any, Dict, ClassVar, Optional, List
from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path(__file__).parent

search_path = "vault,public"


class GitHosting(str, Enum):
    GITLAB = "gitlab"
    GITHUB = "github"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class MailSettings(BaseSettings):
    MAIL_USERNAME: str = Field(
        ...,
        description="SMTP username. Some providers require it separately, others just use MAIL_FROM.",
    )
    MAIL_PASSWORD: str = Field(
        ...,
        description="Password or app-specific key for authenticating to the SMTP server.",
    )
    MAIL_FROM: EmailStr = Field(
        ...,
        description="Default sender email address (appears in the 'From' header).",
    )
    MAIL_FROM_NAME: str | None = Field(
        default=None,
        description="Friendly name for the sender (appears alongside MAIL_FROM).",
    )
    MAIL_PORT: int = Field(
        default=587,
        description="Port for SMTP server. Usually 587 for STARTTLS, 465 for SSL/TLS, 25 as legacy.",
    )
    MAIL_SERVER: str = Field(
        ...,
        description="SMTP server hostname or IP address (e.g., smtp.gmail.com).",
    )
    MAIL_STARTTLS: bool = Field(
        default=True,
        description="Use STARTTLS (opportunistic TLS upgrade). Set false if server doesn’t support it.",
    )
    MAIL_SSL_TLS: bool = Field(
        default=False,
        description="Use direct SSL/TLS connection (usually on port 465).",
    )
    MAIL_USE_CREDENTIALS: bool = Field(
        default=True,
        description="Whether to authenticate with username/password. Set False for open relays (rare).",
    )
    MAIL_VALIDATE_CERTS: bool = Field(
        default=True,
        description="Validate SMTP server's TLS/SSL certificate. Set False only for self-signed certs.",
    )
    
    MAIL_SUPPRESS_SEND: bool = Field(
        default=False,
        description="If True, suppresses actual sending (emails are 'mocked'). Useful in testing.",
    )
    MAIL_DEBUG: int = Field(
        default=0,
        description="Debug output level for SMTP interactions. 0 = silent, 1+ = verbose.",
    )
    
    MAIL_SEND_TIMEOUT: int | None = Field(
        default=60,
        ge=20,
        description=(
            "Max seconds to wait for the SMTP send to complete. If omitted, defaults to 60s. "
            "Set to None to disable the timeout entirely (use with caution). "
            "Values below 20s are rejected to avoid flaky timeouts under normal network operation."
        ),
    )
    
    MAIL_TEMPLATES_PARENT_DIR: Path | None = Field(
        default=None,
        description=(
            "Absolute or relative path to a *parent* directory that contains an 'email/' "
            "subfolder with Jinja templates. The effective template folder passed to the mail "
            "engine is <MAIL_TEMPLATES_PARENT_DIR>/email. If the value is empty, 'none', or "
            "'null', template rendering is disabled and only raw bodies may be used. The path "
            "is expanded (supports ~) and resolved at load time; when set, the '<parent>/email' "
            "directory must exist or settings validation will fail."
        )
    )
    
    # ---- Derived convenience properties ----
    
    @property
    def templates_enabled(self) -> bool:
        return self.MAIL_TEMPLATES_PARENT_DIR is not None

    @property
    def templates_dir(self) -> Path | None:
        
        if not self.templates_enabled:
            return None
        
        return (self.MAIL_TEMPLATES_PARENT_DIR / "email").expanduser().resolve()
    
    # ---- Normalizers & validation ----
    
    @field_validator("MAIL_SEND_TIMEOUT", mode="before")
    @classmethod
    def _noneify_timeout(cls, v:str) -> str | None:
        # Allow '', 'none', 'null' (case-insensitive) to disable the timeout via env
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"", "none", "null"}:
                return None
        return v
    
    @field_validator("MAIL_TEMPLATES_PARENT_DIR", mode="before")
    @classmethod
    def _noneify_mail_template_parent_dir(cls, v:str) -> str | None:
        # Treat "", "none", "null" as disabling templates
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if not s or s.lower() in {"none", "null"}:
                return None
        return v
    
    @field_validator("MAIL_TEMPLATES_PARENT_DIR", mode="after")
    @classmethod
    def _normalize_parent(cls, v: Path | None) -> Path | None:
        return v.expanduser().resolve() if isinstance(v, Path) else v
    
    @model_validator(mode="after")
    def _validate(self) -> "MailSettings":
        # TLS mode sanity
        if self.MAIL_STARTTLS and self.MAIL_SSL_TLS:
            raise ValueError("Set only one of MAIL_STARTTLS or MAIL_SSL_TLS, not both.")

        # If templates are enabled, require <parent>/email to exist
        if self.templates_enabled:
            td = self.templates_dir
            if not (td and td.is_dir()):
                raise ValueError(f"Templates directory does not exist: {td}")
        return self
    
    # ---- Configuration manager ----
    model_config = SettingsConfigDict(
        env_file=CONFIG_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    # Application
    app_name: str = "DevDox AI Context Queue Worker"
    Environment: str = "development"
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    HOST: str = Field(
        default="127.0.0.1",
        description="Host to bind to. Use 127.0.0.1 for dev, 0.0.0.0 for production"
    )
    PORT:int = 8004

    VERSION:str = "0.0.1"

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
    
    mail: MailSettings = Field(default_factory=MailSettings)
    
    CORS_ORIGINS: List[str] = ["http://localhost:8002"]
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v
    
    model_config = SettingsConfigDict(
        env_file=CONFIG_DIR.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


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
    return {
        "engine": "tortoise.backends.asyncpg",
        "credentials": credentials,
        "max_inactive_connection_lifetime": 1800.0,  # 30 minutes (default is 300)
        "command_timeout": 120.0,                    # 2 minutes default per op
    }


def get_tortoise_config():
    """Get Tortoise ORM configuration"""
    db_config = get_database_config()

    return {
        "connections": {"default": db_config},
        "apps": {
            "models": {
                "models": [
                    "models_src.models",
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
