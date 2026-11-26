FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/api

# Dependencies first (cached layer). The project is not packaged: code runs from /srv/api.
COPY pyproject.toml ./
RUN python - <<'PY' > requirements.txt
import tomllib
p = tomllib.load(open("pyproject.toml", "rb"))["project"]
print("\n".join(p["dependencies"] + p["optional-dependencies"]["dev"]))
PY
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --system --no-create-home app && chown -R app /srv/api
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
