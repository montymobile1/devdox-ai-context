"""
Alternative approach using asyncio signal handling
This is cleaner and more reliable than threading approach
"""
from contextlib import asynccontextmanager

import uvicorn
import asyncio
import signal
from typing import List, Set
from tortoise import Tortoise
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.handlers.queue_worker import QueueWorker
from app.core.container import Container
from app.core.config import settings, TORTOISE_ORM

logger = logging.getLogger(__name__)


class WorkerService:
    """Enhanced WorkerService with proper async signal handling"""

    def __init__(self):
        self.container = Container()
        self.container.config.from_dict(settings.model_dump())
        self.workers: List[QueueWorker] = []
        self.worker_tasks: Set[asyncio.Task] = set()
        self.running = False
        self.initialization_complete = False
        self._shutdown_event = asyncio.Event()
        self._signal_handler_task = None

    def setup_signal_handlers(self):
        """Setup signal handlers and start shutdown monitoring"""
        loop = asyncio.get_running_loop()

        def signal_received():
            logger.info("Signal received, setting shutdown event...")
            self._shutdown_event.set()
            # Store the task to prevent garbage collection
            self._shutdown_task = asyncio.create_task(self.shutdown())

        # Register signal handlers with the event loop
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_received)


    async def _wait_for_shutdown(self):
        """Wait for shutdown signal and handle gracefully"""
        try:
            await self._shutdown_event.wait()
            logger.info("Shutdown signal received, initiating graceful shutdown...")
            await self.shutdown()
        except Exception as e:
            logger.error(f"Error in shutdown handler: {e}", exc_info=True)

    def initialize(self):
        """Initialize database and dependencies"""
        try:

            self.container.wire(
                modules=["app.handlers.message_handler", "app.handlers.queue_worker"]
            )
            logger.info("Dependencies wired successfully")
            self.initialization_complete = True

        except Exception as e:
            logger.error(f"Failed to initialize service: {str(e)}", exc_info=True)
            raise

    def start_workers(self):
        """Start queue worker instances"""
        try:
            worker_count = settings.WORKER_CONCURRENCY
            logger.info(f"Starting {worker_count} worker instances")

            for i in range(worker_count):
                worker = QueueWorker(worker_id=f"worker-{i + 1}")
                self.workers.append(worker)

                # Start worker task
                task = asyncio.create_task(self._run_worker_with_monitoring(worker))
                self.worker_tasks.add(task)

                task.add_done_callback(self.worker_tasks.discard)

                logger.info(f"Started worker {i + 1}/{worker_count}")

            self.running = True
            logger.info("All workers started successfully")

        except Exception as e:
            logger.error(f"Failed to start workers: {str(e)}", exc_info=True)
            raise

    async def _run_worker_with_monitoring(self, worker: QueueWorker):
        """Run worker with monitoring and restart capability"""
        while self.running and not self._shutdown_event.is_set():
            try:
                await worker.start()
                if self.running:
                    logger.warning(f"Worker {worker.worker_id} stopped, restarting...")
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                logger.info(f"Worker {worker.worker_id} cancelled during shutdown")
                raise
            except Exception as e:
                logger.error(f"Worker {worker.worker_id} error: {e}", exc_info=True)
                if self.running:
                    try:
                        await asyncio.sleep(10)
                    except asyncio.CancelledError:
                        logger.info(f"Worker {worker.worker_id} error recovery cancelled")
                        raise

    async def shutdown(self):
        """Graceful shutdown of all workers"""
        if not self.running:
            return

        logger.info("Initiating graceful shutdown...")
        self.running = False

        # Cancel signal handler task
        if self._signal_handler_task:
            self._signal_handler_task.cancel()

        # Stop all workers gracefully
        shutdown_tasks = []
        active_tasks = [task for task in self.worker_tasks if not task.done()]
        logger.info(f"Cancelling {len(active_tasks)} active worker tasks...")

        for worker in self.workers:
            logger.info(f"Stopping worker {worker.worker_id}...")
            shutdown_tasks.append(worker.stop())

        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=30.0
                )
                logger.info("All workers stopped gracefully")
            except asyncio.TimeoutError:
                logger.warning("Worker shutdown timeout")


        logger.info("Shutdown complete")


# Global worker service
worker_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan with proper async signal handling"""
    global worker_service

    # Startup
    logger.info(f"Starting DevDox AI Context Worker Service v{settings.VERSION}")

    try:
        # Initialize database
        if TORTOISE_ORM and not Tortoise._inited:
            await Tortoise.init(config=TORTOISE_ORM)
            logger.info("Database initialized")

        # Initialize worker service
        worker_service = WorkerService()
        worker_service.initialize()
        worker_service.start_workers()

        # Setup async signal handlers - this is the key improvement!
        worker_service.setup_signal_handlers()

        logger.info("Application startup complete")

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Application shutdown initiated")
    if worker_service:
        await worker_service.shutdown()

    if TORTOISE_ORM:
        await Tortoise.close_connections()
        logger.info("Database connections closed")

    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="DevDox AI Context API",
    description="Backend API service with proper async signal handling.",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# The rest of your FastAPI setup...
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health_check", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    global worker_service

    return {
        "status": "healthy",
        "message": "DevDox AI Context API is running!",
        "version": settings.VERSION,
        "workers_running": worker_service.running if worker_service else False,
        "worker_count": len(worker_service.workers) if worker_service else 0
    }

def main():
    uvicorn.run(
        "app.main:app",
        host = settings.HOST,
        port = settings.PORT,
        reload = False,
        log_level = "info"
           )
        
if __name__ == "__main__":

    main()