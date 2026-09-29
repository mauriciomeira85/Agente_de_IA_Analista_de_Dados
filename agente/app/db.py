# INTRODUÇÃO
# Camada de acesso ao banco do serviço do agente de IA. Usa um pool pequeno de
# conexões (psycopg2) com o usuário `app_agente`, que tem:
#   * SELECT somente nas views de `analytics` e nas tabelas permitidas de
#     `curated` (sem a tabela `clientes`);
#   * INSERT apenas nas tabelas de histórico/auditoria (app.*, audit.*);
#   * default_transaction_read_only = on e statement_timeout = 10s (migração 005).
# Por isso este módulo separa dois caminhos: `consultar()` (leitura, qualquer
# SQL validado) e `gravar()` (escrita restrita a histórico/auditoria, que
# desliga o read-only só naquela transação com SET LOCAL).
# RESUMO: pool singleton + consultar() + gravar(); toda query usa parâmetros.

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

# Pool pequeno de propósito: o agente roda num container de 384 MB e o banco é
# compartilhado; 4 conexões são suficientes para o tráfego esperado.
_pool: ThreadedConnectionPool | None = None
_vagas = threading.BoundedSemaphore(4)
_criacao_pool = threading.Lock()


def pool() -> ThreadedConnectionPool:
    """Devolve o pool singleton de conexões (criado sob demanda)."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=4,
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5432")),
            dbname=os.environ.get("PGDATABASE", "analista_dados"),
            user=os.environ.get("PGUSER", "app_agente"),
            password=os.environ.get("PGPASSWORD", ""),
            # Cada conexão já nasce somente leitura (camada extra além do role).
            options="-c default_transaction_read_only=on -c statement_timeout=10000",
        )
    return _pool


@contextmanager
def _conexao() -> Iterator[Any]:
    """Pega uma conexão do pool e devolve ao final (fecha a transação)."""
    _vagas.acquire()
    try:
        with _criacao_pool:
            conn = pool().getconn()
    except Exception:
        _vagas.release()
        raise
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool().putconn(conn)
        _vagas.release()


def consultar(sql: str, params: tuple | list | None = None) -> list[dict]:
    """Executa um SELECT e devolve as linhas como lista de dicts.

    O SQL aqui já passou pela validação da segurança (ou é SQL interno fixo);
    os valores SEMPRE entram como parâmetros (%s), nunca interpolados.
    """
    with _conexao() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            return [dict(linha) for linha in cur.fetchall()]


def gravar(sql: str, params: tuple | list | None = None) -> None:
    """Executa um INSERT/UPDATE restrito às tabelas app.* e audit.*.

    O role app_agente nasce com default_transaction_read_only=on; aqui a
    transação volta para leitura+escrita com SET TRANSACTION READ WRITE (que
    precisa ser o primeiro comando da transação). SET LOCAL não funcionaria
    aqui: o modo read-only é fixado no BEGIN, antes do SET LOCAL valer.
    As únicas tabelas graváveis por este usuário são app.* e audit.* (GRANT).
    """
    with _conexao() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ WRITE")
            cur.execute(sql, params or ())
