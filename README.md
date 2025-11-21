# Clean Architecture & DDD in Python

This repository demonstrates a robust implementation of **Clean Architecture** and **Domain-Driven Design (DDD)** principles in Python. It serves as a reference for building scalable, maintainable, and testable backend applications.

## 🏗 Architecture Overview

The project is structured into four strict layers, ensuring separation of concerns and dependency inversion:

1.  **Domain Layer** (`src/domain`):
    *   **Enterprise Business Rules**.
    *   Contains Entities (`Book`), Value Objects (`BookId`, `Title`, `Author`), Domain Events, Exceptions, and **Repository Interfaces** (`BookRepository`).
    *   **Pure Python**: No external dependencies (no frameworks, no ORMs).

2.  **Application Layer** (`src/application`):
    *   **Application Business Rules**.
    *   Orchestrates domain logic using Use Cases (`AddBook`, `ListBooks`, `BorrowBook`) and DTOs.
    *   Depends ONLY on the Domain Layer.

3.  **Infrastructure Layer** (`src/infrastructure`):
    *   **Frameworks & Drivers**.
    *   Implements interfaces defined in the Domain Layer.
    *   Handles persistence (`SQLBookRepository` with SQLAlchemy/aiosqlite), configuration, and external adapters.

4.  **Presentation Layer** (`src/presentation`):
    *   **Interface Adapters**.
    *   Entry points for the application.
    *   **API**: FastAPI application.
    *   **CLI**: Command-line interface using `click`.

> **Note**: In practice, we often group the "Driven" adapters (Repositories) into `infrastructure` and the "Driving" adapters (API/CLI) into `presentation` to keep the project structure clean, even though they both technically live in the "Adapter" ring.

## 🚀 Key Features

*   **Async First**: Built from the ground up with `asyncio`, `aiosqlite`, and async SQLAlchemy.
*   **Dependency Injection**: Uses `dependency-injector` for wiring components.
*   **Strict Typing**: Comprehensive type hinting and `typing.Protocol` for interfaces.
*   **Testing**: Stratified testing suite (Unit, Integration, E2E) with `pytest`.
*   **Load Testing**: Performance testing setup with `locust`.
*   **Configuration**: YAML-based settings management.

## 📂 Directory Structure

```
src/
├── domain/         # Enterprise Business Rules (Entities, VOs, Events, Interfaces)
├── application/    # Application Business Rules (Use Cases, DTOs)
├── infrastructure/ # Frameworks & Drivers (DB, Config, Repositories)
├── presentation/   # Interface Adapters (API, CLI)
└── container.py    # Dependency Injection Container
tests/
├── unit/           # Fast, isolated domain tests
├── integration/    # Database and Use Case integration tests
├── e2e/            # Full system API and CLI tests
└── load/           # Locust load testing scripts
```

## 🛠 Getting Started

### Prerequisites
*   Python 3.10+
*   Virtual environment (recommended)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd clean-architecture-ddd-python

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install .
```

## 🏃‍♂️ Running the Application

### API Server
Start the FastAPI server:
```bash
uvicorn src.presentation.api.main:app --reload
```
Access the API docs at: `http://127.0.0.1:8000/docs`

### CLI
Use the command-line interface:
```bash
# Add a book
python src/presentation/cli/main.py add "Clean Architecture" "Robert C. Martin"

# List books
python src/presentation/cli/main.py list

# Borrow a book
python src/presentation/cli/main.py borrow <book_id>
```

## 🧪 Testing

The project uses a stratified testing strategy:

```bash
# Run all tests
pytest

# Run Unit Tests (Domain Logic)
pytest tests/unit

# Run Integration Tests (Use Cases & DB)
pytest tests/integration

# Run E2E Tests (API & CLI)
pytest tests/e2e
```

### Load Testing
To benchmark performance:
1.  Start the API server.
2.  Run Locust:
    ```bash
    locust -f tests/load/locustfile.py
    ```
3.  Open `http://localhost:8089` in your browser.

## 📝 License
This project is open source and available under the MIT License.
