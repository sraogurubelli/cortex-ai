# Contributing to Cortex-AI

Thank you for your interest in contributing to Cortex-AI! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Testing Guidelines](#testing-guidelines)
- [Commit Message Guidelines](#commit-message-guidelines)
- [Pull Request Process](#pull-request-process)
- [Common Tasks](#common-tasks)

## Code of Conduct

We expect all contributors to follow our Code of Conduct. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **Docker Desktop** - [Download](https://www.docker.com/products/docker-desktop)
- **Task** (go-task) - [Installation guide](https://taskfile.dev/installation/)
  ```bash
  # macOS
  brew install go-task

  # Linux
  sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d

  # Windows (PowerShell)
  choco install go-task
  ```
- **Git** - [Download](https://git-scm.com/downloads)

### Quick Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/cortex-ai.git
   cd cortex-ai
   ```

2. **Set up the development environment:**
   ```bash
   task setup
   ```

   This command will:
   - Install Python dependencies
   - Set up pre-commit hooks
   - Start Docker services (PostgreSQL, Redis, Qdrant, Neo4j)
   - Initialize the database

3. **Verify the setup:**
   ```bash
   task test
   ```

4. **Start the development server:**
   ```bash
   task dev
   ```

   The API will be available at http://localhost:8000

## Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Your Changes

- Write clear, concise code
- Add tests for new functionality
- Update documentation as needed
- Follow the code style guidelines

### 3. Run Tests and Linting

```bash
# Format code
task format

# Run linting
task lint

# Run tests
task test
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "feat: add new feature"
```

Pre-commit hooks will automatically:
- Format your code
- Run linters
- Check for common issues

### 5. Push and Create a Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Code Style

### General Guidelines

- **Line Length:** Maximum 100 characters
- **Indentation:** 4 spaces (no tabs)
- **Formatting:** We use [Black](https://black.readthedocs.io/) for code formatting
- **Linting:** We use [Ruff](https://docs.astral.sh/ruff/) for linting
- **Type Hints:** Use type hints for function parameters and return values

### Formatting

Run the formatter before committing:

```bash
task format
```

This runs:
- Black (code formatter)
- Ruff (import sorting and auto-fixes)

### Linting

Check for linting issues:

```bash
task lint
```

This runs:
- Ruff (linting)
- Mypy (type checking)
- Bandit (security scanning)

### Type Hints

Always use type hints:

```python
def create_user(name: str, email: str, age: int) -> User:
    """Create a new user."""
    return User(name=name, email=email, age=age)
```

### Docstrings

Use Google-style docstrings:

```python
def process_data(data: list[dict], threshold: float = 0.5) -> list[dict]:
    """
    Process data with given threshold.

    Args:
        data: List of data dictionaries to process
        threshold: Threshold value for filtering (default: 0.5)

    Returns:
        Processed list of dictionaries

    Raises:
        ValueError: If threshold is not between 0 and 1
    """
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between 0 and 1")
    return [item for item in data if item.get("score", 0) >= threshold]
```

## Testing Guidelines

### Test Organization

Tests are organized into two categories:

- **Unit Tests** (`tests/unit/`) - Fast, isolated tests for individual functions/classes
- **Integration Tests** (`tests/integration/`) - Tests that require database, network, or multiple components

### Writing Tests

1. **Use pytest** for all tests
2. **Name test files** with `test_` prefix: `test_auth.py`
3. **Name test functions** with `test_` prefix: `test_create_user()`
4. **Use fixtures** for common setup
5. **Use markers** for test categorization:
   ```python
   @pytest.mark.asyncio
   async def test_async_function():
       result = await async_operation()
       assert result == expected
   ```

### Running Tests

```bash
# Run all tests
task test

# Run unit tests only
task test:unit

# Run integration tests
task test:integration

# Run with coverage
task test:coverage

# Run tests in watch mode
task test:watch
```

### Coverage Requirements

- Aim for >80% code coverage
- All new features must include tests
- Critical paths should have 100% coverage

## Commit Message Guidelines

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring (no functional changes)
- `test`: Adding or updating tests
- `chore`: Maintenance tasks (dependencies, build, etc.)
- `perf`: Performance improvements
- `ci`: CI/CD changes

### Examples

```bash
# Feature
git commit -m "feat(auth): add JWT token refresh endpoint"

# Bug fix
git commit -m "fix(database): resolve connection pool exhaustion"

# Documentation
git commit -m "docs(readme): update installation instructions"

# Refactor
git commit -m "refactor(api): simplify error handling middleware"

# Test
git commit -m "test(auth): add tests for password reset flow"
```

### Scope Examples

- `auth` - Authentication/authorization
- `database` - Database layer
- `api` - API routes/endpoints
- `orchestration` - Agent orchestration
- `rag` - RAG/search functionality
- `platform` - Platform features (RBAC, accounts, etc.)
- `ci` - CI/CD workflows
- `docker` - Docker configuration

## Pull Request Process

### Before Creating a PR

1. **Update your branch** with the latest main:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks**:
   ```bash
   task format
   task lint
   task test
   ```

3. **Update documentation** if needed

### Creating a PR

1. **Use the PR template** (auto-filled when creating a PR)
2. **Write a clear title** following commit message guidelines
3. **Describe your changes** in detail
4. **Link related issues** using keywords: `Fixes #123`, `Relates to #456`
5. **Add screenshots/demos** for UI changes

### PR Checklist

- [ ] Code follows the project's code style
- [ ] Tests added for new features/fixes
- [ ] All tests pass locally (`task test`)
- [ ] Linting passes (`task lint`)
- [ ] Documentation updated (if needed)
- [ ] Commit messages follow guidelines
- [ ] PR title follows commit message guidelines
- [ ] No merge conflicts with main branch

### CI Checks

All PRs must pass these automated checks:

- ✅ **Tests** - All tests pass on Python 3.11 and 3.12
- ✅ **Linting** - Ruff, Black, Mypy, Bandit
- ✅ **Pre-commit** - All pre-commit hooks pass
- ✅ **Security** - Dependency scanning passes

### Code Review

- Be patient - reviewers are volunteers
- Address feedback constructively
- Make requested changes in new commits (don't force push)
- Respond to all review comments

### Merging

- PRs are merged using **squash and merge** by maintainers
- Your commits will be squashed into a single commit
- The PR title becomes the commit message

## Common Tasks

### Development

```bash
# Install dependencies
task install

# Complete setup (install + docker + database)
task setup

# Start development server
task dev

# Start with debugging enabled
task dev:debug

# Clean build artifacts
task clean
```

### Code Quality

```bash
# Format code (Black + Ruff auto-fix)
task format

# Run linters
task lint

# Type checking only
task type-check

# Run all quality checks
task check

# Run pre-commit hooks
task pre-commit
```

### Testing

```bash
# Run all tests
task test

# Run unit tests only
task test:unit

# Run integration tests
task test:integration

# Run with coverage report
task test:coverage

# Run quick unit tests (excludes slow tests)
task test:quick

# Watch mode (runs tests on file changes)
task test:watch
```

### Docker

```bash
# Start Docker services
task docker:up

# Stop Docker services
task docker:down

# View logs
task docker:logs

# Show running services
task docker:ps

# Reset volumes (destroys data)
task docker:reset

# Pull latest images
task docker:pull
```

### Database

```bash
# Run migrations (create tables)
task db:migrate

# Open PostgreSQL shell
task db:shell

# Dump database to file
task db:dump

# Restore database from dump
task db:restore

# Reset database (drop and recreate)
task db:reset
```

### Demos

```bash
# Run platform demo (signup, create org, chat)
task demo

# Run GraphRAG demo
task demo:graphrag
```

### CI/CD

```bash
# Run CI test suite locally
task ci:test

# Run CI lint checks locally
task ci:lint

# Run all CI checks
task ci:all
```

### Help

```bash
# List all available tasks
task --list

# Show help information
task help
```

## Getting Help

- **Documentation:** See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed development guide
- **Issues:** Check existing [GitHub Issues](https://github.com/your-org/cortex-ai/issues)
- **Discussions:** Join [GitHub Discussions](https://github.com/your-org/cortex-ai/discussions)

## License

By contributing to Cortex-AI, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to Cortex-AI! 🎉
