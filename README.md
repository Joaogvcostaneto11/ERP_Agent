# ERP Agent

An AI-native ERP system: an adaptive conversational UI, an AI-powered business
logic engine, and a database access layer. See [CLAUDE.md](CLAUDE.md) for the
full architecture and design constraints.

## Prerequisites

These are **system-level** requirements that are *not* installed by `pip`. Install
them before setting up the Python environment.

| Requirement | Notes |
|---|---|
| **Python 3.12** | The project targets 3.12 (`requires-python = ">=3.12,<3.14"`). Newer versions (3.14+) often lack prebuilt wheels for dependencies like `jiter` and `pyodbc`, forcing source builds that need Rust/C toolchains. Use 3.12 to match the team. |
| **Microsoft ODBC Driver 18 for SQL Server** | Required for the database connection. `pip install pyodbc` only installs the Python binding — the driver itself is a separate Microsoft component. Without it you get `pyodbc.InterfaceError IM002 ... data source name not found and no default driver specified`. |

### Installing the ODBC driver

- **Windows:** `winget install --id Microsoft.msodbcsql.18` (or download the
  `msodbcsql18` MSI from Microsoft), then restart your terminal.
- **macOS:**
  ```bash
  brew tap microsoft/mssql-release https://github.com/microsoft/homebrew-mssql-release
  brew install msodbcsql18
  ```
- **Linux:** add Microsoft's apt/yum repo, then install `msodbcsql18`
  (see Microsoft's "Install the ODBC driver for SQL Server" docs for your distro).

Verify it's installed — `ODBC Driver 18 for SQL Server` should appear in the list:

```bash
python -c "import pyodbc; print(pyodbc.drivers())"
```

## Setup

```bash
# 1. Create a virtualenv on Python 3.12
py -3.12 -m venv .venv          # Windows
# python3.12 -m venv .venv      # macOS/Linux
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies (pinned) + the project
python -m pip install --upgrade pip
pip install -r requirements.lock
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env            # then fill in the values
```

`.env` requires `ANTHROPIC_API_KEY`, `DATABASE_URL` (a **read-only** SQL Server
login), and — for DevCare write operations — `DEVCARE_WRITE_DATABASE_URL`.

## Running

```bash
# Chat UI (read-only queries/reports) — http://localhost:8000/
uvicorn logic.chat.app:app --reload

# DevCare operations (write CRUD) — http://localhost:8001/
uvicorn logic.devcare.app:app --reload --port 8001
```

## Tests

```bash
pytest tests/
```
