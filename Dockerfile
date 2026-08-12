FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

RUN pip install --no-cache-dir .

# Run as an unprivileged user: the bot needs no write access to its own code,
# and neither it nor the migration job has any reason to be root.
RUN useradd --create-home --uid 10001 htmanager && chown -R htmanager:htmanager /app
USER htmanager

CMD ["python", "-m", "ht_manager.main"]
