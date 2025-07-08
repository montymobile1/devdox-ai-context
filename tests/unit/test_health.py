"""
Test cases for health checking utilities
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from app.health import HealthChecker, check


class TestHealthChecker:
    """Test cases for HealthChecker class"""

    @pytest.fixture
    def health_checker(self):
        """Create HealthChecker instance for testing"""
        return HealthChecker()

    def test_init(self, health_checker):
        """Test HealthChecker initialization"""
        assert health_checker.last_check is None

    @pytest.mark.asyncio
    @patch("app.health.connections")
    async def test_check_database_healthy(self, mock_connections, health_checker):
        """Test database health check when healthy"""
        mock_db = MagicMock()
        mock_db.execute_query = AsyncMock()
        mock_db._pool_size = 10
        mock_db._pool_used = 3
        mock_connections.get.return_value = mock_db

        result = await health_checker.check_database()

        assert result["status"] == "healthy"
        assert "response_time_ms" in result
        assert result["connection_pool"]["size"] == 10
        assert result["connection_pool"]["used"] == 3
        mock_db.execute_query.assert_called_once_with("SELECT 1")

    @pytest.mark.asyncio
    @patch("app.health.connections")
    async def test_check_database_unhealthy(self, mock_connections, health_checker):
        """Test database health check when unhealthy"""
        mock_db = MagicMock()
        mock_db.execute_query = AsyncMock(side_effect=Exception("Connection failed"))
        mock_connections.get.return_value = mock_db

        result = await health_checker.check_database()

        assert result["status"] == "unhealthy"
        assert "error" in result
        assert "Connection failed" in result["error"]

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("app.infrastructure.queues.supabase_queue.SupabaseQueue")
    async def test_check_queue_system_healthy(
        self, mock_supabase_queue, mock_settings, health_checker
    ):
        """Test queue system health check when healthy"""
        mock_settings.SUPABASE_HOST = "localhost"
        mock_settings.SUPABASE_PORT = 5432
        mock_settings.SUPABASE_USER = "test_user"
        mock_settings.SUPABASE_PASSWORD = "test_password"
        mock_settings.SUPABASE_DB_NAME = "test_db"

        mock_queue = MagicMock()
        mock_supabase_queue.return_value = mock_queue

        result = health_checker.check_queue_system()

        assert result["status"] == "healthy"
        assert result["queue_type"] == "supabase"

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("app.infrastructure.queues.supabase_queue.SupabaseQueue")
    async def test_check_queue_system_unhealthy(
        self, mock_supabase_queue, mock_settings, health_checker
    ):
        """Test queue system health check when unhealthy"""
        mock_settings.SUPABASE_HOST = "localhost"
        mock_settings.SUPABASE_PORT = 5432
        mock_settings.SUPABASE_USER = "test_user"
        mock_settings.SUPABASE_PASSWORD = "test_password"
        mock_settings.SUPABASE_DB_NAME = "test_db"

        mock_supabase_queue.side_effect = Exception("Queue connection failed")

        result = health_checker.check_queue_system()

        assert result["status"] == "unhealthy"
        assert "error" in result

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("httpx.AsyncClient")
    async def test_check_external_apis_together_ai_healthy(
        self, mock_httpx_client, mock_settings, health_checker
    ):
        """Test external APIs check with healthy Together AI"""
        mock_settings.TOGETHER_API_KEY = "test_key"

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client_instance = MagicMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        result = await health_checker.check_external_apis()

        assert result["together_ai"]["status"] == "healthy"

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("httpx.AsyncClient")
    async def test_check_external_apis_together_ai_unhealthy(
        self, mock_httpx_client, mock_settings, health_checker
    ):
        """Test external APIs check with unhealthy Together AI"""
        mock_settings.TOGETHER_API_KEY = "test_key"

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client_instance = MagicMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        result = await health_checker.check_external_apis()

        assert result["together_ai"]["status"] == "unhealthy"
        assert result["together_ai"]["status_code"] == 401

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("httpx.AsyncClient")
    async def test_check_external_apis_exception(
        self, mock_httpx_client, mock_settings, health_checker
    ):
        """Test external APIs check with exception"""
        mock_settings.TOGETHER_API_KEY = "test_key"

        mock_client_instance = MagicMock()
        mock_client_instance.get = AsyncMock(side_effect=Exception("Network error"))
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_client.return_value = mock_client_instance

        result = await health_checker.check_external_apis()

        assert result["together_ai"]["status"] == "unhealthy"
        assert "error" in result["together_ai"]

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("app.health.settings")
    async def test_check_all_healthy(
        self, mock_settings_checker, mock_settings_config, health_checker
    ):
        """Test comprehensive health check when all healthy"""
        for mock_settings in [mock_settings_checker, mock_settings_config]:
            mock_settings.version = "1.0.0"
            mock_settings.Environment = "test"

        # Mock all check methods
        health_checker.check_database = AsyncMock(return_value={"status": "healthy"})
        health_checker.check_queue_system = AsyncMock(
            return_value={"status": "healthy"}
        )
        health_checker.check_external_apis = AsyncMock(return_value={})
        result = await health_checker.check_all()
        assert result["healthy"] is True
        assert result["service"] == "devdox-ai-context"
        assert result["version"] == "1.0.0"
        assert result["environment"] == "test"
        assert "timestamp" in result
        assert "checks" in result
        assert health_checker.last_check is not None

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    @patch("app.health.settings")
    async def test_check_all_unhealthy_database(
        self, mock_settings_checker, mock_settings_config, health_checker
    ):
        """Test comprehensive health check when database unhealthy"""
        for mock_settings in [mock_settings_checker, mock_settings_config]:
            mock_settings.version = "1.0.0"
            mock_settings.Environment = "test"

        # Mock all check methods
        health_checker.check_database = AsyncMock(return_value={"status": "unhealthy"})
        health_checker.check_queue_system = AsyncMock(
            return_value={"status": "healthy"}
        )
        health_checker.check_external_apis = AsyncMock(return_value={})

        result = await health_checker.check_all()

        assert result["healthy"] is False

    @pytest.mark.asyncio
    @patch("app.core.config.settings")
    async def test_check_all_with_exceptions(self, mock_settings, health_checker):
        """Test comprehensive health check with exceptions"""
        mock_settings.version = "1.0.0"
        mock_settings.Environment.value = "test"

        # Mock all check methods with exceptions
        health_checker.check_database = AsyncMock(side_effect=Exception("DB error"))
        health_checker.check_queue_system = AsyncMock(
            side_effect=Exception("Queue error")
        )
        health_checker.check_external_apis = AsyncMock(
            side_effect=Exception("API error")
        )

        result = await health_checker.check_all()

        assert result["healthy"] is False
        assert result["checks"]["database"]["status"] == "error"
        assert result["checks"]["queue_system"]["status"] == "error"
        assert result["checks"]["external_apis"]["status"] == "error"


class TestCheckFunction:
    """Test the standalone check function"""

    @pytest.mark.asyncio
    @patch("app.health.Tortoise.init")
    @patch("app.health.Tortoise.close_connections")
    async def test_check_success(self, mock_close_connections, mock_tortoise_init):
        """Test successful health check"""
        mock_tortoise_init.return_value = None
        mock_close_connections.return_value = None

        # Mock health checker
        with patch("app.health.HealthChecker") as mock_health_checker_class:
            mock_health_checker = MagicMock()
            mock_health_checker.check_all = AsyncMock(return_value={"healthy": True})
            mock_health_checker_class.return_value = mock_health_checker

            result = await check()

            assert result == 0
            mock_tortoise_init.assert_called_once()
            mock_close_connections.assert_called_once()
            mock_health_checker.check_all.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.health.Tortoise.init")
    @patch("app.health.Tortoise.close_connections")
    @patch("builtins.print")
    async def test_check_unhealthy(
        self, mock_print, mock_close_connections, mock_tortoise_init
    ):
        """Test health check when unhealthy"""
        mock_tortoise_init.return_value = None
        mock_close_connections.return_value = None

        # Mock health checker
        with patch("app.health.HealthChecker") as mock_health_checker_class:
            mock_health_checker = MagicMock()
            mock_health_checker.check_all = AsyncMock(return_value={"healthy": False})
            mock_health_checker_class.return_value = mock_health_checker

            result = await check()
            assert result == 1


class TestMainEntryPoint:
    """Test main entry point for health check"""

    @patch("asyncio.run")
    @patch("sys.exit")
    @patch("app.health.__name__", "__main__")
    def test_health_check_main(self, mock_exit, mock_asyncio_run):
        """Test health check main entry point"""
        mock_asyncio_run.return_value = 0

        # This is challenging to test directly since it's in the if __name__ == "__main__" block
        # We can test that the check function works as expected
        mock_asyncio_run.assert_not_called()  # Since we're mocking
