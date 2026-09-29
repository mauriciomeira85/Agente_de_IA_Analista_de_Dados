# INTRODUÇÃO
# Imagem do serviço gerador de dados fictícios. É um job de execução única
# (profile "carga" do docker-compose): sobe, gera, publica e encerra.
# Base slim para caber no limite de 256 MB de memória da VM compartilhada.
# RESUMO: python:3.12-slim + requirements + gerar_dados.py; entrypoint roda a carga.

FROM python:3.12-slim

WORKDIR /app

# Instala primeiro para aproveitar o cache de camadas do Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gerar_dados.py .

CMD ["python", "gerar_dados.py"]
