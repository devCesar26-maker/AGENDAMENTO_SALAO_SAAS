# Éclat Studio — backend (Python 3.12)
# D1/D2: o usuário é criado ANTES do COPY para permitir --chown no COPY,
# evitando a camada extra de chown -R que duplicava a árvore do app (~265 MB).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# Usuário sem privilégios criado antes do COPY (permite --chown sem camada extra)
RUN addgroup --system app && adduser --system --ingroup app app

# Instala dependências de produção antes de copiar o código (melhor cache)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copia apenas o código-fonte (venv/, .git/ e outros excluídos pelo .dockerignore)
COPY --chown=app:app . .

# collectstatic roda no start como usuário app; garante que /app/staticfiles
# seja gravável sem um chown -R recursivo (que duplicaria a camada do app).
RUN mkdir -p /app/staticfiles && chown app:app /app /app/staticfiles

USER app

EXPOSE 8000

CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 --access-logfile - --error-logfile -"]
