FROM python:3.14

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Set working directory
WORKDIR /code

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into the system environment (repo is volume-mounted
# over /code at runtime, so the venv must live outside it)
# --require-hashes: uv export pins every package with hashes from uv.lock
RUN uv export --frozen --no-dev --format requirements-txt --no-header -o /tmp/requirements.txt \
    && uv pip install --system --break-system-packages --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy application code
COPY ./app /code/app
COPY ./data /code/data

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]

# Expose the Prometheus port
EXPOSE 8090
