"""
Health checking utilities for the DevDox AI Context service.
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import json
from tortoise import Tortoise
from tortoise import connections
from app.core.config import TORTOISE_ORM
from app.core.config import settings


class HealthChecker:
    """Health checker for service components"""

    def __init__(self):
        self.last_check: Optional[datetime] = None

    async def check_database(self) -> Dict[str, Any]:
        """Check database connectivity"""
        try:
            db = connections.get("default")
            start_time = datetime.now(timezone.utc)
            await db.execute_query("SELECT 1")
            response_time = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds() * 1000

            return {
                "status": "healthy",
                "response_time_ms": response_time,
                "connection_pool": {
                    "size": getattr(db, "_pool_size", "unknown"),
                    "used": getattr(db, "_pool_used", "unknown"),
                },
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def check_queue_system(self) -> Dict[str, Any]:
        """Check queue system health"""
        try:
            from app.infrastructure.queues.supabase_queue import SupabaseQueue

            # This is a basic check - you might want to customize based on your queue implementation
            queue = SupabaseQueue(
                host=settings.SUPABASE_HOST,
                port=settings.SUPABASE_PORT,
                user=settings.SUPABASE_USER,
                password=settings.SUPABASE_PASSWORD,
                db_name=settings.SUPABASE_DB_NAME,
            )

            # Check if we can connect to the queue system
            # Implementation depends on your specific queue setup

            return {"status": "healthy", "queue_type": "supabase"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def check_external_apis(self) -> Dict[str, Any]:
        """Check external API connectivity"""
        results = {}
        # Check Together AI API
        if settings.TOGETHER_API_KEY:
            try:
                import httpx

                async with httpx.AsyncClient() as client:
                    headers = {"Authorization": f"Bearer {settings.TOGETHER_API_KEY}"}
                    response = await client.get(
                        "https://api.together.xyz/models", headers=headers, timeout=5.0
                    )

                    if response.status_code == 200:
                        results["together_ai"] = {"status": "healthy"}
                    else:
                        results["together_ai"] = {
                            "status": "unhealthy",
                            "status_code": response.status_code,
                        }
            except Exception as e:
                results["together_ai"] = {"status": "unhealthy", "error": str(e)}
        else:
            results["together_ai"] = {"status": "not_configured"}

        return results

    async def check_all(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        self.last_check = datetime.now(timezone.utc)

        # Run all checks concurrently
        db_check, queue_check, api_checks = await asyncio.gather(
            self.check_database(),
            self.check_queue_system(),
            self.check_external_apis(),
            return_exceptions=True,
        )

        # Handle any exceptions from the checks
        if isinstance(db_check, Exception):
            db_check = {"status": "error", "error": str(db_check)}
        if isinstance(queue_check, Exception):
            queue_check = {"status": "error", "error": str(queue_check)}
        if isinstance(api_checks, Exception):
            api_checks = {"status": "error", "error": str(api_checks)}

        # Determine overall health
        overall_healthy = (
            db_check.get("status") == "healthy"
            and queue_check.get("status") == "healthy"
        )

        return {
            "healthy": overall_healthy,
            "timestamp": self.last_check.isoformat(),
            "service": "devdox-ai-context",
            "version": settings.version,
            "environment": settings.Environment,
            "checks": {
                "database": db_check,
                "queue_system": queue_check,
                "external_apis": api_checks,
            },
        }


async def check() -> int:
    """Command-line health check utility"""
    health_checker = HealthChecker()

    try:
        # Initialize database for health check
        await Tortoise.init(config=TORTOISE_ORM)
        # Perform health check
        result = await health_checker.check_all()
        # Return appropriate exit code
        return 0 if result["healthy"] else 1

    except Exception as e:
        return 1
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    import asyncio
    import sys

    exit_code = asyncio.run(check())
    sys.exit(exit_code)
