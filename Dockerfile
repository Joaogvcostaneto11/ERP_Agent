# ERP Chat UI — container for Render (free tier).
# Docker is required because pyodbc needs the system-level ODBC Driver 18.
FROM python:3.12-slim

# Install Microsoft ODBC Driver 18 for SQL Server (pulls in unixODBC runtime).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && apt-get purge -y --auto-remove curl gnupg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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
