"""
Test cases for core configuration
"""
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError
from app.core.config import (
    Settings, 
    get_database_config, 
    get_tortoise_config,
    GitHosting,
    LogLevel,
    settings,
    TORTOISE_ORM
)


class TestEnums:
    """Test enum classes"""
    
    def test_git_hosting_enum(self):
        """Test GitHosting enum values"""
        assert GitHosting.GITLAB == "gitlab"
        assert GitHosting.GITHUB == "github"
    
    def test_log_level_enum(self):
        """Test LogLevel enum values"""
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARNING == "WARNING"
        assert LogLevel.ERROR == "ERROR"


class TestSettings:
    """Test Settings configuration class"""
    
    def test_settings_defaults(self):
        """Test default settings values"""
        # Mock required fields to avoid validation errors
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test_key',
            'SUPABASE_PASSWORD': 'test_password',
            'TOGETHER_API_KEY': 'test_together_key',
            'SECRET_KEY': 'test_secret_key_that_is_at_least_32_chars',
            'EMBEDDING_MODEL':"text-embedding-ada-003"

        }):
            test_settings = Settings()

            assert test_settings.app_name == "DevDox AI Context Queue Worker"
            assert test_settings.Environment == "development"
            assert test_settings.DEBUG is False
            assert test_settings.version == "0.0.1"
            assert test_settings.DB_MAX_CONNECTIONS == 20
            assert test_settings.DB_MIN_CONNECTIONS == 5
            assert test_settings.IS_PRODUCTION is False
            assert test_settings.EMBEDDING_MODEL == "text-embedding-ada-003"
            assert test_settings.vector_dimensions == 1536
            assert test_settings.SUPABASE_REST_API is False

    
    def test_settings_field_validation(self):
        """Test field validation"""
        # Test minimum values
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test_key',
            'SUPABASE_PASSWORD': 'test_password',
            'TOGETHER_API_KEY': 'test_together_key',
            'SECRET_KEY': 'test_secret_key_that_is_at_least_32_chars',
            'DB_MAX_CONNECTIONS': '0'  # Below minimum
        }):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_settings_secret_key_validation(self):
        """Test secret key minimum length validation"""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test_key',
            'SUPABASE_PASSWORD': 'test_password',
            'TOGETHER_API_KEY': 'test_together_key',
            'SECRET_KEY': 'short'  # Too short
        }):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_settings_with_environment_variables(self):
        """Test settings with environment variables"""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://custom.supabase.co',
            'SUPABASE_KEY': 'custom_key',
            'SUPABASE_PASSWORD': 'custom_password',
            'TOGETHER_API_KEY': 'custom_together_key',
            'SECRET_KEY': 'custom_secret_key_that_is_at_least_32_chars',
            'WORKER_CONCURRENCY': '5',
            'DEBUG': 'true',
            'IS_PRODUCTION': 'true'
        }):
            test_settings = Settings()
            
            assert test_settings.SUPABASE_URL == 'https://custom.supabase.co'
            assert test_settings.SUPABASE_KEY == 'custom_key'
            assert test_settings.WORKER_CONCURRENCY == 5
            assert test_settings.DEBUG is True
            assert test_settings.IS_PRODUCTION is True
    


class TestGetDatabaseConfig:
    """Test database configuration function"""
    
    @patch('app.core.config.Settings')
    def test_get_database_config_rest_api(self, mock_settings_class):
        """Test database config with REST API connection"""
        mock_settings = MagicMock()
        mock_settings.SUPABASE_REST_API = True
        mock_settings.SUPABASE_URL = "https://testproject.supabase.co"
        mock_settings.SUPABASE_KEY = "test_key"
        mock_settings.DB_MIN_CONNECTIONS = 5
        mock_settings.DB_MAX_CONNECTIONS = 20
        mock_settings.IS_PRODUCTION = False
        mock_settings_class.return_value = mock_settings
        
        config = get_database_config()
        
        assert config["engine"] == "tortoise.backends.asyncpg"
        assert config["credentials"]["host"] == "db.testproject.supabase.co"
        assert config["credentials"]["port"] == 5432
        assert config["credentials"]["user"] == "postgres"
        assert config["credentials"]["password"] == "test_key"
        assert config["credentials"]["database"] == "postgres"
        assert config["credentials"]["minsize"] == 5
        assert config["credentials"]["maxsize"] == 20
        assert config["credentials"]["ssl"] == "prefer"
    
    @patch('app.core.config.Settings')
    def test_get_database_config_direct_connection(self, mock_settings_class):
        """Test database config with direct PostgreSQL connection"""
        mock_settings = MagicMock()
        mock_settings.SUPABASE_REST_API = False
        mock_settings.SUPABASE_HOST = "localhost"
        mock_settings.SUPABASE_PORT = 5433
        mock_settings.SUPABASE_USER = "test_user"
        mock_settings.SUPABASE_PASSWORD = "test_password"
        mock_settings.SUPABASE_DB_NAME = "test_db"
        mock_settings.DB_MIN_CONNECTIONS = 3
        mock_settings.DB_MAX_CONNECTIONS = 15
        mock_settings.IS_PRODUCTION = True
        mock_settings_class.return_value = mock_settings
        
        config = get_database_config()
        
        assert config["engine"] == "tortoise.backends.asyncpg"
        assert config["credentials"]["host"] == "localhost"
        assert config["credentials"]["port"] == 5433
        assert config["credentials"]["user"] == "test_user"
        assert config["credentials"]["password"] == "test_password"
        assert config["credentials"]["database"] == "test_db"
        assert config["credentials"]["minsize"] == 3
        assert config["credentials"]["maxsize"] == 15
        assert config["credentials"]["ssl"] == "require"
    
    @patch('app.core.config.Settings')
    def test_get_database_config_invalid_supabase_url_no_https(self, mock_settings_class):
        """Test database config with invalid Supabase URL (no https)"""
        mock_settings = MagicMock()
        mock_settings.SUPABASE_REST_API = True
        mock_settings.SUPABASE_URL = "http://testproject.supabase.co"
        mock_settings_class.return_value = mock_settings
        
        with pytest.raises(ValueError) as exc_info:
            get_database_config()
        
        assert "Invalid Supabase URL format" in str(exc_info.value)
    
    @patch('app.core.config.Settings')
    def test_get_database_config_invalid_supabase_url_wrong_domain(self, mock_settings_class):
        """Test database config with invalid Supabase URL (wrong domain)"""
        mock_settings = MagicMock()
        mock_settings.SUPABASE_REST_API = True
        mock_settings.SUPABASE_URL = "https://testproject.other.co"
        mock_settings_class.return_value = mock_settings
        
        with pytest.raises(ValueError) as exc_info:
            get_database_config()
        
        assert "Invalid Supabase URL format" in str(exc_info.value)
    
    @patch('app.core.config.Settings')
    def test_get_database_config_empty_project_id(self, mock_settings_class):
        """Test database config with empty project ID"""
        mock_settings = MagicMock()
        mock_settings.SUPABASE_REST_API = True
        mock_settings.SUPABASE_URL = "https://.supabase.co"
        mock_settings_class.return_value = mock_settings
        
        with pytest.raises(ValueError) as exc_info:
            get_database_config()
        
        assert "Unable to extract project ID from Supabase URL" in str(exc_info.value)


class TestGetTortoiseConfig:
    """Test Tortoise ORM configuration function"""
    
    @patch('app.core.config.get_database_config')
    def test_get_tortoise_config(self, mock_get_db_config):
        """Test Tortoise ORM configuration"""
        mock_db_config = {
            "engine": "tortoise.backends.asyncpg",
            "credentials": {"host": "localhost"}
        }
        mock_get_db_config.return_value = mock_db_config
        
        config = get_tortoise_config()
        
        assert "connections" in config
        assert "default" in config["connections"]
        assert config["connections"]["default"] == mock_db_config
        
        assert "apps" in config
        assert "models" in config["apps"]
        assert "models" in config["apps"]["models"]["models"]
        assert "aerich.models" in config["apps"]["models"]["models"]
        assert config["apps"]["models"]["default_connection"] == "default"
        
        assert config["use_tz"] is False
        assert config["timezone"] == "UTC"


class TestGlobalInstances:
    """Test global settings and config instances"""
    
    def test_settings_instance(self):
        """Test global settings instance"""
        assert settings is not None
        assert isinstance(settings, Settings)
    
    def test_tortoise_orm_instance(self):
        """Test global TORTOISE_ORM instance"""
        assert TORTOISE_ORM is not None
        assert isinstance(TORTOISE_ORM, dict)
        assert "connections" in TORTOISE_ORM
        assert "apps" in TORTOISE_ORM


class TestSettingsConfig:
    """Test Settings configuration"""
    
    def test_settings_config_class(self):
        """Test Settings.Config class"""
        config = Settings.Config
        assert config.env_file == "app/.env"
        assert config.case_sensitive is True
        assert config.extra == "ignore"


class TestFieldValidation:
    """Test field validation edge cases"""
    
    def test_port_validation(self):
        """Test port number validation"""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test_key',
            'SUPABASE_PASSWORD': 'test_password',
            'TOGETHER_API_KEY': 'test_together_key',
            'SECRET_KEY': 'test_secret_key_that_is_at_least_32_chars',
            'SUPABASE_PORT': '70000'  # Above maximum
        }):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_worker_concurrency_validation(self):
        """Test worker concurrency validation"""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test_key',
            'SUPABASE_PASSWORD': 'test_password',
            'TOGETHER_API_KEY': 'test_together_key',
            'SECRET_KEY': 'test_secret_key_that_is_at_least_32_chars',
            'WORKER_CONCURRENCY': '15'  # Above maximum
        }):
            with pytest.raises(ValidationError):
                Settings()
    
    def test_vector_dimensions_validation(self):
        """Test vector dimensions validation"""
        with patch.dict('os.environ', {
            'SUPABASE_URL': 'https://test.supabase.co',
            'SUPABASE_KEY': 'test_key',
            'SUPABASE_PASSWORD': 'test_password',
            'TOGETHER_API_KEY': 'test_together_key',
            'SECRET_KEY': 'test_secret_key_that_is_at_least_32_chars',
            'vector_dimensions': '100'  # Below minimum
        }):
            with pytest.raises(ValidationError):
                Settings()
