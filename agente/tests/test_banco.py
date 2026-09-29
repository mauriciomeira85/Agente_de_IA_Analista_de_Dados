# INTRODUÇÃO
# Testes de COERÊNCIA da carga fictícia e de RECONCILIAÇÃO da camada semântica.
# Precisam de banco com dados (rodam na VM ou em qualquer Postgres do projeto):
#   * coerência: datas em ordem (lead <= visita <= proposta <= negócio),
#     comissão = valor * perc, negócio fechado muda status do imóvel, sem
#     imóvel vendido duas vezes, perdidos têm motivo e fechados não têm;
#   * reconciliação: cada view de analytics deve bater com o SQL direto
#     equivalente em curated (é o que garante que Dashboard e agente mostram
#     os mesmos números).
# Pulam automaticamente se não houver PGHOST/PGPASSWORD configurados.
# RESUMO: pytest -q agente/tests/test_banco.py (com banco disponível).

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("PGPASSWORD"),
    reason="precisa de banco (PGHOST/PGPASSWORD) — roda na VM ou no compose")

from app import db  # noqa: E402


def escalar(sql: str):
    """Executa um SELECT de um único valor."""
    return list(db.consultar(sql)[0].values())[0]


# ---------------------------------------------------------------------------
# Coerência da carga
# ---------------------------------------------------------------------------

def test_datas_em_ordem_no_funil():
    """lead <= visita <= proposta <= fechamento, para todo o funil."""
    assert escalar("""
        SELECT COUNT(*) FROM curated.fato_visitas v
        JOIN curated.fato_leads l ON l.lead_id = v.lead_id
        WHERE v.data < l.data""") == 0
    assert escalar("""
        SELECT COUNT(*) FROM curated.fato_propostas p
        WHERE NOT EXISTS (SELECT 1 FROM curated.fato_visitas v
                          WHERE v.lead_id = p.lead_id
                            AND v.data <= p.data)""") == 0
    assert escalar("""
        SELECT COUNT(*) FROM curated.fato_negocios n
        WHERE n.data_fechamento < n.data_abertura""") == 0


def test_comissao_igual_valor_vezes_percentual():
    """valor_comissao = valor_negocio * perc_comissao / 100 (fechados)."""
    assert escalar("""
        SELECT COUNT(*) FROM curated.fato_negocios
        WHERE status = 'fechado'
          AND ABS(valor_comissao - ROUND(valor_negocio * perc_comissao / 100, 2))
              > 0.01""") == 0


def test_imovel_vendido_uma_unica_vez():
    """Um imóvel de venda aparece no máximo uma vez como fechado."""
    assert escalar("""
        SELECT COUNT(*) FROM (
            SELECT imovel_id FROM curated.fato_negocios
            WHERE status = 'fechado' AND finalidade = 'venda'
            GROUP BY imovel_id HAVING COUNT(*) > 1) t""") == 0


def test_status_do_imovel_coerente_com_negocio():
    """Todo imóvel com negócio fechado está vendido/alugado."""
    assert escalar("""
        SELECT COUNT(*) FROM curated.fato_negocios n
        JOIN curated.imoveis i ON i.imovel_id = n.imovel_id
        WHERE n.status = 'fechado'
          AND i.status <> CASE WHEN n.finalidade = 'venda'
                               THEN 'vendido' ELSE 'alugado' END""") == 0


def test_motivo_perda_preenchido_so_nos_perdidos():
    assert escalar("""
        SELECT COUNT(*) FROM curated.fato_negocios
        WHERE (status = 'perdido' AND motivo_perda IS NULL)
           OR (status = 'fechado' AND motivo_perda IS NOT NULL)""") == 0


def test_volumes_na_faixa_esperada():
    """Volumes aproximados do spec (com margem): evita carga quebrada."""
    leads = escalar("SELECT COUNT(*) FROM curated.fato_leads")
    fechados = escalar(
        "SELECT COUNT(*) FROM curated.fato_negocios WHERE status = 'fechado'")
    assert 5500 <= leads <= 6500
    assert 400 <= fechados <= 800


# ---------------------------------------------------------------------------
# Reconciliação: view de analytics x SQL direto em curated
# ---------------------------------------------------------------------------

def test_reconcilia_vgv_mensal():
    """SUM(vgv) da view = soma direta das vendas fechadas."""
    via_view = escalar(
        "SELECT COALESCE(SUM(vgv),0) FROM analytics.v_vgv_mensal "
        "WHERE finalidade = 'venda'")
    direto = escalar("""
        SELECT COALESCE(SUM(valor_negocio),0) FROM curated.fato_negocios
        WHERE status = 'fechado' AND finalidade = 'venda'""")
    assert abs(float(via_view) - float(direto)) < 0.01


def test_reconcilia_funil_totais():
    """Totais do funil na view = contagens diretas das tabelas fato."""
    linha = db.consultar("""
        SELECT SUM(leads) AS leads, SUM(visitas) AS visitas,
               SUM(propostas) AS propostas, SUM(fechados) AS fechados
        FROM analytics.v_funil_mensal""")[0]
    assert int(linha["leads"]) == escalar("SELECT COUNT(*) FROM curated.fato_leads")
    assert int(linha["visitas"]) == escalar(
        "SELECT COUNT(*) FROM curated.fato_visitas WHERE compareceu")
    assert int(linha["propostas"]) == escalar(
        "SELECT COUNT(*) FROM curated.fato_propostas")
    assert int(linha["fechados"]) == escalar(
        "SELECT COUNT(*) FROM curated.fato_negocios WHERE status = 'fechado'")


def test_reconcilia_ticket_medio():
    """Ticket médio da view (ponderado) = AVG direto das vendas fechadas."""
    via_view = escalar("""
        SELECT SUM(ticket_medio * negocios_fechados) / SUM(negocios_fechados)
        FROM analytics.v_vgv_mensal WHERE finalidade = 'venda'""")
    direto = escalar("""
        SELECT AVG(valor_negocio) FROM curated.fato_negocios
        WHERE status = 'fechado' AND finalidade = 'venda'""")
    assert abs(float(via_view) - float(direto)) < 0.01


def test_reconcilia_conversao_por_origem():
    """Taxa de conversão por origem: view = fechados/leads direto."""
    linhas = db.consultar("""
        SELECT o.nome_origem,
               (SELECT COUNT(*) FROM curated.fato_leads l
                 WHERE l.origem_id = o.origem_id) AS leads,
               (SELECT COUNT(*) FROM curated.fato_negocios n
                 JOIN curated.fato_leads l2 ON l2.lead_id = n.lead_id
                 WHERE l2.origem_id = o.origem_id AND n.status = 'fechado')
                 AS fechados
        FROM curated.dim_origem o""")
    via_view = {r["origem"]: (r["leads"], r["fechados"]) for r in db.consultar(
        "SELECT origem, SUM(leads) AS leads, SUM(fechados) AS fechados "
        "FROM analytics.v_conversao_origem GROUP BY origem")}
    for linha in linhas:
        assert via_view[linha["nome_origem"]][0] == linha["leads"]
        assert via_view[linha["nome_origem"]][1] == linha["fechados"]


def test_reconcilia_realizado_meta():
    """Realizado da view de metas = negócios fechados direto por equipe/mês."""
    divergencias = escalar("""
        SELECT COUNT(*) FROM analytics.v_realizado_meta v
        WHERE v.realizado_negocios <> (
            SELECT COUNT(*) FROM curated.fato_negocios n
            JOIN curated.dim_corretor c ON c.corretor_id = n.corretor_id
            WHERE c.equipe_id = v.equipe_id AND n.status = 'fechado'
              AND to_char(n.data_fechamento, 'YYYY-MM') = v.competencia)""")
    assert divergencias == 0
