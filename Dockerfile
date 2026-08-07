# SylvaNova apworld Discord bot
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1 \
	PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 1000 bot \
	&& useradd --system --uid 1000 --gid bot --home-dir /app --shell /usr/sbin/nologin bot

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

USER bot

CMD ["python", "-m", "sylvanova_apworld_bot"]
