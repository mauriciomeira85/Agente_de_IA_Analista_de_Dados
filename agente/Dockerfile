# INTRODUÇÃO
# Imagem do serviço do agente de IA. Base slim + dependências compiladas via
# wheels (psycopg2-binary, matplotlib) para não precisar de toolchain de build.
# Limite de memória no compose: 384 MB.
# RESUMO: python:3.12-slim, instala requirements, sobe uvicorn na porta 8000.

FROM python:3.12-slim

WORKDIR /app

# Cache de camadas: dependências primeiro, código depois.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY avaliacao ./avaliacao
COPY tests ./tests

# Pasta de arquivos gerados (PDF/Excel); em produção é um volume nomeado.
RUN mkdir -p /app/arquivos_gerados

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
