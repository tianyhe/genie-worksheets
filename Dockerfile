FROM python:3.11-slim-bookworm

# Install build tools and runtime dependencies required for common Python packages (e.g. psycopg2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user to run the application inside the container
RUN useradd --create-home --shell /bin/bash genie
WORKDIR /app

# Copy project metadata and source code necessary for installing dependencies & the local package
COPY uv.lock pyproject.toml README.md /app/
COPY src /app/src

# Install dependencies using uv (fast, reproducible) then clean up cache
RUN pip install --no-cache-dir uv \
    && uv sync \
    && rm -rf ~/.cache/pip

# Copy the rest of the project (experiments, docs, etc.)
COPY . /app

# Install the project in editable mode so that Python picks up local changes
RUN uv pip install --no-cache-dir -e .

# Switch to the non-root user for day-to-day commands
USER genie

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# By default start an interactive shell; override with `docker run` or compose command.
CMD ["bash"] 