# Contributing to Intuno

Thank you for your interest in contributing to Intuno! This guide will help you get started.

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/IntunoAI/intuno.git
   cd intuno
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   uv venv && source .venv/bin/activate
   uv pip install -e ".[dev]"
   ```

3. **Start infrastructure:**
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```

4. **Configure your environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings (see .env.example for documentation)
   ```

5. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Start the dev server:**
   ```bash
   uvicorn src.main:app --reload --port 8000
   ```

## Code Style

- We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting.
- Run `ruff check src/ tests/` and `ruff format src/ tests/` before submitting.
- Follow existing patterns in the codebase.

## Architecture Rules

Intuno follows a strict layered architecture:

```
routes -> services -> repositories -> models
```

- **Routes** handle HTTP concerns (request parsing, response formatting).
- **Services** contain business logic.
- **Repositories** handle database access.
- **Models** define SQLAlchemy ORM models.

Don't skip layers. Routes should not access repositories directly.

All database access must be async (`async with get_session() as session`). Never use synchronous SQLAlchemy sessions.

## Running Tests

```bash
pytest tests/ -v
```

Tests use an in-process test client with a separate test database. Make sure migrations are up-to-date before running tests.

## Database Migrations

After modifying SQLAlchemy models:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Submitting Changes

1. Fork the repository and create a feature branch from `main`.
2. Make your changes with clear, focused commits.
3. Ensure tests pass and linting is clean.
4. Open a pull request with a description of what changed and why.

## Reporting Issues

- Use [GitHub Issues](https://github.com/IntunoAI/intuno/issues) for bug reports and feature requests.
- Include steps to reproduce for bugs.
- Check existing issues before creating a new one.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.
