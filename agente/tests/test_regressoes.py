# INTRODUÇÃO
# Regressões dos defeitos encontrados na revisão: isolamento, PDF e filtros.
import json
from contextvars import Context

import pytest
from openpyxl import load_workbook

from app import ferramentas, main, relatorios
from app.seguranca import SqlRecusado, validar_sql


@pytest.mark.parametrize('sql', [
    'SELECT * FROM public.fato_leads',
    'SELECT * FROM outro.analytics.v_funil_mensal',
    'SELECT * INTO temporaria FROM curated.fato_leads',
    'SELECT * FROM curated.fato_leads FOR UPDATE',
    "SELECT query_to_xml('SELECT * FROM app.agente_mensagens', true, false, '')",
    'SELECT pg_advisory_lock(42)',
])
def test_bloqueia_bypass(sql):
    """Qualificar outra tabela ou executar SQL por função não passa."""
    with pytest.raises(SqlRecusado):
        validar_sql(sql)


def test_conversa_reaberta(monkeypatch):
    """A segunda pergunta reutiliza a conversa sem NameError."""
    monkeypatch.setattr(main.db, 'consultar', lambda *a: [{'conversa_id': 'abc'}])
    assert main._conversa_da_sessao('sessao-teste') == 'abc'


def test_artefatos_isolados():
    """Contextos distintos não compartilham a lista padrão mutável."""
    a, b = Context(), Context()
    a.run(ferramentas.registrar_artefato, {'tipo': 'grafico'})
    assert b.run(ferramentas.drenar_artefatos) == []
    assert a.run(ferramentas.drenar_artefatos) == [{'tipo': 'grafico'}]


def test_pdf_com_grafico(tmp_path, monkeypatch):
    """PNG permanece legível durante a montagem, com XML escapado."""
    monkeypatch.setattr(relatorios, 'ARQUIVOS_DIR', tmp_path)
    nome = relatorios.gerar_pdf('Vendas <teste>', '2025', 'A & B', [
        {'tipo': 'grafico', 'grafico': {'rotulos': ['Jan', 'Fev'], 'valores': [1, 2]}},
        {'tipo': 'tabela', 'colunas': ['Mês', 'VGV'], 'linhas': [['Jan', 100]]},
    ])
    assert (tmp_path / nome).read_bytes().startswith(b'%PDF')
    assert not list(tmp_path.glob('*.png'))


def test_excel_texto_nao_vira_formula(tmp_path, monkeypatch):
    """Dados textuais externos não podem executar fórmulas no Excel."""
    monkeypatch.setattr(relatorios, 'ARQUIVOS_DIR', tmp_path)
    nome = relatorios.gerar_excel('Dados', ['Nome'], [['=1+1']])
    cell = load_workbook(tmp_path / nome).active['A2']
    assert cell.data_type == 's'


def test_filtro_nao_suportado_nao_e_ignorado():
    """Meta sem dimensão de cidade deve recusar o recorte explicitamente."""
    r = json.loads(ferramentas.consultar_metrica('realizado_vs_meta', '2026-01-01', '2026-01-31', cidade='X'))
    assert 'erro' in r


def test_metrica_preserva_dia_e_origem(monkeypatch):
    """Datas não viram meses completos; filtro de origem alcança VGV."""
    consultas = []
    def consultar(sql, params=None):
        consultas.append((sql, params))
        return [{'id': 2}] if 'ILIKE' in sql else [{'valor': 123}]
    monkeypatch.setattr(ferramentas.db, 'consultar', consultar)
    r = json.loads(ferramentas.consultar_metrica('vgv', '2026-01-15', '2026-01-19', origem='Indicação'))
    assert r['linhas'][0]['valor'] == 123
    assert 'data_ref BETWEEN' in consultas[-1][0]
    assert 'origem_id = %s' in consultas[-1][0]
    assert consultas[-1][1][:2] == ['2026-01-15', '2026-01-19']


def test_pdf_com_analise_e_varias_consultas(tmp_path, monkeypatch):
    """O PDF leva a análise do agente e uma seção (tabela+gráfico) por consulta."""
    from decimal import Decimal
    monkeypatch.setattr(relatorios, 'ARQUIVOS_DIR', tmp_path)
    ferramentas.iniciar_contexto()
    ids = [json.loads(ferramentas._json({
        'metrica': m, 'fonte': 'analytics.v_vgv_mensal', 'linhas': [
            {'competencia': '2025-01', 'valor': Decimal('100.5')},
            {'competencia': '2025-02', 'valor': Decimal('200')}]}))['resultado_id']
        for m in ('vgv', 'negocios_fechados')]
    saida = json.loads(ferramentas.gerar_relatorio_pdf(
        'Vendas 2025', '2025', '**Destaque**: alta em fevereiro.\n\nConclusão.', ids, 'linha'))
    assert saida['ok']
    arquivo = [a for a in ferramentas.drenar_artefatos() if a['tipo'] == 'arquivo'][0]
    assert (tmp_path / arquivo['nome_arquivo']).read_bytes().startswith(b'%PDF')


def test_pdf_recusa_resultado_de_outra_pergunta():
    """resultado_id inexistente nesta pergunta não gera arquivo."""
    ferramentas.iniciar_contexto()
    assert 'erro' in json.loads(ferramentas.gerar_relatorio_pdf('X', '2025', 'Y', ['naoexiste']))


def test_agrupamento_devolve_nome_e_total(monkeypatch):
    """Agrupar por origem devolve o nome da origem (não o id) e o total do
    período calculado pelo banco, para o modelo não somar linhas de cabeça."""
    consultas = []

    def consultar(sql, params=None):
        consultas.append(sql)
        return [{'valor': 10}]
    monkeypatch.setattr(ferramentas.db, 'consultar', consultar)
    r = json.loads(ferramentas.consultar_metrica(
        'leads_recebidos', '2026-01-01', '2026-06-30', agrupar_por='origem'))
    assert 'nome_origem' in consultas[0] and 'GROUP BY v.origem_id' in consultas[0]
    assert 'GROUP BY' not in consultas[1] and r['total_do_periodo'] == {'valor': 10}
# RESUMO: testes independentes de API paga para evitar recorrência dos defeitos.
