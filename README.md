# DevDox AI Context

## Overview

The DevDox AI Context service is a crucial component of the DevDox AI platform, responsible for building and maintaining contextual information about code repositories. It processes repositories to understand code structure, patterns, and user preferences, enabling intelligent and personalized code generation and automation.

## Purpose and Functionality

The DevDox AI Context service is designed to:

- Create and maintain comprehensive context for code repositories
- Process user preferences and project requirements
- Build vector embeddings for semantic code understanding
- Manage code quality standards and practices
- Store historical context from previous operations
- Provide relevant context to the DevDox AI Agent
- Queue and process context creation requests asynchronously

## Technology Stack

- **Language**: Python 3.10+
- **Framework**: FastAPI
- **Queue System**: 
  - Initial: Supabase for lightweight queue implementation
  - Future: Redis with Celery for high-volume processing
- **Vector Database**: Supabase with pgvector extension
- **Dependencies**:
  - LangChain/LlamaIndex (Context processing)
  - Pydantic (Data validation)
  - SQLAlchemy (Database ORM)
  - Supabase-py (Database connectivity)
  - Redis (Optional - for advanced queue processing)
  - PyGithub/python-gitlab (Git API integration)

## Queue Processing Architecture

The context service implements a queue-based architecture for processing repository analysis requests:

1. **Queue Producers**:
   - DevDox AI Portal API (when users request repository analysis)
   - DevDox AI Agent (when automation triggers context updates)

2. **Queue Implementation**:
   - **Initial**: Supabase Realtime + database triggers
   - **Future**: Redis + Celery for more robust processing

3. **Queue Consumer**:
   - The Context service listens to the queue and processes analysis jobs
   - Tasks are processed asynchronously to avoid blocking operations
   - Results are stored in the vector database for future use

4. **Processing Flow**:
   ```
   [Portal/Agent] -> [Queue] -> [Context Service Worker] -> [Vector Database]
   ```

## Installation and Setup

### Prerequisites

- Python 3.10+
- Poetry (recommended for dependency management)
- Supabase account and credentials
- Git platform API credentials (GitHub, GitLab, etc.)

### Basic Setup

```bash
# Clone the repository
git clone https://github.com/montymobile1/devdox-ai-context.git
cd devdox-ai-context

# Install dependencies using Poetry
poetry install

# Or using pip
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your credentials

# Start the development server
poetry run uvicorn app.main:app --reload

# Start the worker (in a separate terminal)
poetry run python -m app.worker.main
```

## API Documentation

When running the application, the API documentation is automatically available at:

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

The API provides endpoints for:

- Submitting repositories for context creation
- Setting user preferences for code analysis
- Retrieving context information
- Managing queue tasks
- Monitoring worker status

## Configuration

Configuration is primarily managed through environment variables:

- `SUPABASE_URL`: Supabase instance URL
- `SUPABASE_KEY`: Supabase API key
- `GITHUB_TOKEN`: GitHub API token (if using GitHub integration)
- `GITLAB_TOKEN`: GitLab API token (if using GitLab integration)
- `REDIS_URL`: Redis URL (if using Redis for queue processing)
- `WORKER_CONCURRENCY`: Number of concurrent worker processes
- `LOG_LEVEL`: Logging level (default: INFO)

Additional configuration options can be found in `config.py`.

## Interaction with Other Components

The DevDox AI Context service interacts with:

1. **DevDox AI Portal API**: Receives context creation requests
2. **DevDox AI Agent**: Provides context for intelligent code operations
3. **Git platforms**: Connects to GitHub, GitLab, etc. to analyze repositories
4. **Supabase/Redis**: For queue management and data storage

## Development Guidelines

### Project Structure

```
devdox-ai-context/
├── app/
│   ├── api/           # API endpoints
│   ├── core/          # Core functionality
│   ├── models/        # Data models
│   ├── services/      # Business logic
│   ├── worker/        # Queue worker implementation
│   ├── utils/         # Utility functions
│   └── main.py        # Application entry point
├── tests/             # Test cases
├── .env.example       # Example environment variables
├── pyproject.toml     # Poetry dependencies
└── README.md          # This file
```

### Worker Process

The worker process is responsible for:
1. Monitoring the queue for new tasks
2. Processing repository analysis tasks
3. Generating and storing context embeddings
4. Handling errors and retries

### Testing

Run tests using:

```bash
# Run all tests
poetry run pytest

# Run with coverage report
poetry run pytest --cov=app
```

### Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m 'Add some feature'`
4. Push to the branch: `git push origin feature/your-feature-name`
5. Submit a pull request

## License

[MIT License](LICENSE)

---

*Related Jira Issue: [DAC-1](https://montyholding.atlassian.net/browse/DAC-1)*
