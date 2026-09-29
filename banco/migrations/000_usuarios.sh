#!/bin/bash
# INTRODUÇÃO
# Migração 000 (shell): cria os usuários de aplicação com senhas vindas do ambiente.
# Roda antes de qualquer .sql porque o initdb executa os arquivos em ordem alfabética.
# Separação de papéis (defesa em profundidade): cada serviço tem seu próprio usuário
# somente leitura (ou de carga), então uma falha em um serviço não compromete os demais.
# RESUMO: cria app_dashboard, app_agente e app_gerador com as senhas do .env.
set -euo pipefail

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v dashboard="$SENHA_USUARIO_DASHBOARD" -v agente="$SENHA_USUARIO_AGENTE" \
  -v gerador="$SENHA_USUARIO_GERADOR" <<'SQL'
CREATE ROLE app_dashboard LOGIN PASSWORD :'dashboard';
CREATE ROLE app_agente LOGIN PASSWORD :'agente';
CREATE ROLE app_gerador LOGIN PASSWORD :'gerador';
SQL
# RESUMO: senhas são literais SQL escapados pelo psql, inclusive com apóstrofos.
