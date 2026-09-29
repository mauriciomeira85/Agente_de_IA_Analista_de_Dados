# INTRODUÇÃO
# Testes que PROVAM as travas de segurança do SQL livre do agente
# (agente/app/seguranca.py). São testes de unidade puros: não precisam de banco,
# porque a validação acontece antes de qualquer execução (sqlglot).
# Cada teste tenta um ataque ou violação e exige a recusa com motivo claro:
# DELETE, DROP, dois comandos empilhados, coluna sensível, tabela fora da lista
# branca, função perigosa e injeção clássica (' OR 1=1 --).
# RESUMO: pytest -q agente/tests/test_seguranca.py — tudo deve ser recusado,
# e os SELECTs legítimos devem passar com LIMIT automático.

from __future__ import annotations

import pytest

from app.seguranca import SqlRecusado, validar_sql


def test_select_simples_passa_e_ganha_limite():
    """SELECT legítimo na lista branca passa e recebe LIMIT 1000 automático."""
    sql = validar_sql(
        "SELECT competencia, SUM(vgv) FROM analytics.v_vgv_mensal "
        "GROUP BY competencia")
    assert "LIMIT 1000" in sql.upper()


def test_select_com_limit_maior_e_reduzido():
    """LIMIT acima de 1.000 é reduzido para o teto."""
    sql = validar_sql("SELECT * FROM curated.fato_leads LIMIT 5000")
    assert "LIMIT 1000" in sql.upper()
    assert "5000" not in sql


def test_delete_e_recusado():
    with pytest.raises(SqlRecusado):
        validar_sql("DELETE FROM curated.fato_leads")


def test_drop_e_recusado():
    with pytest.raises(SqlRecusado):
        validar_sql("DROP TABLE curated.fato_leads")


def test_dois_comandos_sao_recusados():
    """Dois comandos empilhados (SELECT; DROP) não passam."""
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT 1; DROP TABLE curated.fato_leads")


def test_coluna_sensivel_e_recusada():
    """CPF (coluna sensível) não pode ser lido nem por subterfúgio."""
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT cpf FROM curated.clientes")


def test_tabela_fora_da_lista_e_recusada():
    """A tabela clientes (dados pessoais) está fora da lista branca."""
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT cliente_id FROM curated.clientes")


def test_tabela_de_outro_schema_e_recusada():
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT * FROM audit.agente_execucoes")


def test_funcao_perigosa_e_recusada():
    """pg_sleep (negação de serviço) é bloqueada."""
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT pg_sleep(10)")


def test_pg_read_file_e_recusado():
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT pg_read_file('/etc/passwd')")


def test_injecao_union_sobre_tabela_bloqueada_e_recusada():
    """Injeção clássica tentando alcançar clientes via UNION é recusada."""
    with pytest.raises(SqlRecusado):
        validar_sql(
            "SELECT lead_id FROM curated.fato_leads "
            "UNION SELECT cliente_id FROM curated.clientes")


def test_injecao_com_comentario_e_recusada():
    """' OR 1=1 -- não altera o resultado da validação (comando único SELECT
    continua valendo, mas a tentativa de empilhar comando após o comentário
    falha no parse de comando único)."""
    with pytest.raises(SqlRecusado):
        validar_sql("SELECT 1 FROM curated.fato_leads WHERE 1=1; "
                    "DELETE FROM curated.fato_leads --")


def test_cte_de_leitura_passa():
    """CTE de leitura sobre tabela permitida é aceita."""
    sql = validar_sql(
        "WITH x AS (SELECT lead_id, data FROM curated.fato_leads) "
        "SELECT COUNT(*) FROM x")
    assert "LIMIT 1000" in sql.upper()


def test_update_disfarcado_em_cte_e_recusado():
    """WITH ... DELETE (escrita escondida em CTE) é recusada."""
    with pytest.raises(SqlRecusado):
        validar_sql(
            "WITH x AS (DELETE FROM curated.fato_leads RETURNING lead_id) "
            "SELECT * FROM x")
