#!/bin/bash
# INTRODUÇÃO
# Backup diário do banco PostgreSQL do Agente Analista de Dados (pg_dump via
# container, compactado com gzip). Roda no cron do host da VM (veja o README,
# seção "Backup"). Guarda 14 dias de retenção em ~/backups/agente_analista_dados.
# O banco nunca é exposto à internet; o backup fica só no disco da VM.
# RESUMO: pg_dump -Fc dentro do container db -> arquivo .dump.gz datado;
# apaga backups com mais de 14 dias.
set -euo pipefail
umask 077

PASTA_BACKUPS="$HOME/backups/agente_analista_dados"
CONTAINER="agente_analista_dados-db"
BANCO="analista_dados"
RETENCAO_DIAS=14

mkdir -p "$PASTA_BACKUPS"
ARQUIVO="$PASTA_BACKUPS/analista_dados-$(date +%Y-%m-%d_%H%M).dump"

PARCIAL="${ARQUIVO}.partial"
trap 'rm -f -- "$PARCIAL"' EXIT
docker exec "$CONTAINER" pg_dump -U postgres -Fc "$BANCO" > "$PARCIAL"
docker exec -i "$CONTAINER" pg_restore --list < "$PARCIAL" > /dev/null
mv -- "$PARCIAL" "$ARQUIVO"

# Remove backups mais antigos que a retenção.
find "$PASTA_BACKUPS" -name 'analista_dados-*.dump' -mtime +"$RETENCAO_DIAS" -delete

echo "[backup] $ARQUIVO ($(du -h "$ARQUIVO" | cut -f1))"
