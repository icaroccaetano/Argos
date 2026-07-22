FROM python:3.12-slim

# Criado antes do COPY para que a aplicação seja copiada já com a posse correta.
# O home é necessário: sem ele, pip/ruff/pytest não têm onde escrever seus caches.
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

# WORKDIR cria /app como root; ruff e pytest escrevem seus caches na raiz do projeto.
RUN chown appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
