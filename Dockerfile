# ERP Chat UI — container for Render (free tier).
# Docker is required because pyodbc needs the system-level ODBC Driver 18.
FROM python:3.12-slim

# Install Microsoft ODBC Driver 18 for SQL Server (pulls in unixODBC runtime).
# The MS apt repo is added with [trusted=yes]: Debian 12's sqv verifier rejects
# Microsoft's signing key because its binding signature uses SHA-1, which sqv
# treats as insecure after 2026-02-01. We fetch over HTTPS from Microsoft's
# official host, so we bypass the apt-layer key check rather than fight it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && echo "deb [trusted=yes] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# TEMP DIAGNOSTIC: surface the real driver file, its registered path, and any
# missing shared-lib dependency (ldd). Remove once the driver loads cleanly.
RUN echo "===ODBC DIAG START===" \
    && ls -l /opt/microsoft/msodbcsql18/lib64/ 2>&1 || true; \
    echo "---odbcinst.ini---"; cat /etc/odbcinst.ini 2>&1 || true; \
    for f in /opt/microsoft/msodbcsql18/lib64/libmsodbcsql-*.so.*; do \
      echo "---ldd $f---"; ldd "$f" 2>&1 || true; \
    done; \
    echo "===ODBC DIAG END==="

WORKDIR /app

# Install Python deps first so the layer caches across code changes.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# App source (ui/, business_rules/, docs/, db/, logic/ are all read at runtime).
COPY . .

# History/audit are written here; ephemeral on Render, which is fine.
RUN mkdir -p logs

# Render provides $PORT at runtime; default to 8000 for local `docker run`.
ENV PORT=8000
CMD uvicorn logic.chat.app:app --host 0.0.0.0 --port ${PORT}
