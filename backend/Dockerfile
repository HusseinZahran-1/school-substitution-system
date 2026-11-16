FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
COPY --chown=app:app backend/app ./backend/app
COPY --chown=app:app backend/alembic.ini ./backend/alembic.ini
COPY --chown=app:app backend/alembic ./backend/alembic
COPY --chown=app:app frontend ./frontend
WORKDIR /app/backend
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
