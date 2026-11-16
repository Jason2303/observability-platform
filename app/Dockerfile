FROM python:3.12-slim AS build
WORKDIR /src
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
RUN useradd --uid 10001 --no-create-home shop
WORKDIR /srv
COPY --from=build /venv /venv
COPY app.py .
COPY entrypoint.sh .
USER 10001
EXPOSE 8080
ENTRYPOINT ["sh", "/srv/entrypoint.sh"]
