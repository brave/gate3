FROM python:3.13

# Install Poetry
RUN pip install poetry

# Set working directory
WORKDIR /code

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy application code
COPY ./app /code/app
COPY ./data /code/data

# Run the application
CMD ["fastapi", "run", "--host", "0.0.0.0", "--port", "80"]