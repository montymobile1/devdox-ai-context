"""
DevDox AI Context Queue Worker Service

This service processes repository analysis requests from queues and generates
contextual embeddings for AI-powered code understanding.
"""

import asyncio
import signal
import sys
from typing import List
from tortoise import Tortoise
import logging

from app.handlers.queue_worker import QueueWorker
from app.core.container import Container
from app.core.config import settings, TORTOISE_ORM


class WorkerService:
    """Main worker service coordinator"""

    def __init__(self):
        self.container = Container()
        self.container.config.from_dict(settings.dict())
        self.workers: List[QueueWorker] = []
        self.running = False

    async def initialize(self):
        """Initialize database and dependencies"""
        try:
            # Initialize database connection
            await Tortoise.init(config=TORTOISE_ORM)
            logging.info("Database connection initialized")

            # Wire dependency injection
            self.container.wire(
                modules=["app.handlers.message_handler", "app.handlers.queue_worker"]
            )
            logging.info("Dependencies wired successfully")

        except Exception as e:
            logging.error(f"Failed to initialize service: {str(e)}", exc_info=True)

            raise

    def start_workers(self):
        """Start queue worker instances"""
        try:
            worker_count = settings.WORKER_CONCURRENCY
            logging.info(f"Starting {worker_count} worker instances")

            for i in range(worker_count):
                worker = QueueWorker(worker_id=f"worker-{i+1}")
                self.workers.append(worker)

                # Start worker in background

                asyncio.create_task(worker.start())
                logging.info(f"Started worker {i+1}/{worker_count}")

            self.running = True

            logging.info("All workers started successfully")

        except Exception as e:
            logging.error(f"Failed to start workers {str(e)}", exc_info=True)
            raise

    async def shutdown(self):
        """Graceful shutdown of all workers"""
        if not self.running:
            return

        logging.info("Initiating graceful shutdown...")
        self.running = False

        # Stop all workers
        shutdown_tasks = []
        for worker in self.workers:
            shutdown_tasks.append(worker.stop())

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            logging.info("All workers stopped")

        # Close database connections
        await Tortoise.close_connections()
        logging.info("Database connections closed")

        logging.info("Shutdown complete")

    async def run(self):
        """Main service run loop"""
        try:
            await self.initialize()
            self.start_workers()

            # Keep service running until shutdown signal
            while self.running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logging.info("Received interrupt signal")
        except Exception as e:
            logging.error(f"Service error: {str(e)}", exc_info=True)

        finally:
            await self.shutdown()


def setup_signal_handlers(service: WorkerService):
    """
        Handles the graceful shutdown of an operation on:
            - Interruption (SIGINT) Sent by pressing `Ctrl+C` in the terminal.
            - Termination (SIGTERM) Sent by `kill` or system shutdowns (common in Docker, systemd, etc.).
        It calls the shutdown operation on any of these operations.
    """

    def signal_handler(signum, frame):
        """
            The Handler called to kick in the graceful shutdown operation
        """
        logging.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(service.shutdown())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main():
    """Main entry point"""
    logging.info("Starting DevDox AI Context Worker Service", version=settings.version)

    service = WorkerService()
    setup_signal_handlers(service)

    try:
        await service.run()
    except Exception as e:
        logging.error(f"Service failed to start: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
