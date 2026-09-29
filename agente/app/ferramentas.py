# INTRODUÇÃO
# Ferramentas do agente "Analista de Dados" (Agno). Cada função é registrada
# como tool do Agent e tem docstring em português — é ela que o modelo lê para
# decidir quando e como chamar a ferramenta.
#
# Desenho:
#   * `consultar_metrica` é o CAMINHO PREFERIDO: consulta as views de
#     `analytics` (a camada semântica), com nomes de métrica/dimensão/filtro
#     validados contra listas fechadas — o modelo nunca monta SQL aqui;
#   * `executar_sql_somente_leitura` é o plano B, validado por seguranca.py;
#   * `gerar_grafico` devolve uma especificação ECharts que o frontend desenha
#     dentro do chat; PDF e Excel gravam arquivo e devolvem link de download;
#   * artefatos (gráficos e arquivos) são registrados num contextvar por
#     requisição, que o endpoint de chat drena e envia como eventos SSE —
#     assim o gráfico aparece mesmo se o modelo não repetir o JSON no texto;
#   * toda falha vira uma mensagem de erro legível para o modelo (a regra é:
#     nunca inventar números; se falhou, dizer que falhou).
# RESUMO: 7 ferramentas (catálogo, métrica, dicionário, SQL validado, gráfico,
# PDF, Excel) + registro de artefatos da requisição.

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from decimal import Decimal
from typing import Any

from . import db, relatorios
from .seguranca import SqlRecusado, validar_sql

# Artefatos produzidos pelas ferramentas durante UMA requisição de chat
# (gráficos ECharts e arquivos para download). O endpoint drena ao final.
_artefatos: ContextVar[list[dict]] = ContextVar("artefatos", default=None)


_consultas: ContextVar[dict | None] = ContextVar("consultas", default=None)


def iniciar_contexto():
    """Isola resultados e artefatos antes de iniciar uma pergunta."""
    _consultas.set({})
    _artefatos.set([])


def obter_resultado(resultado_id: str) -> dict:
    """Somente referências produzidas nesta execução podem virar arquivos."""
    resultado = (_consultas.get() or {}).get(resultado_id)
    if resultado is None:
        raise ValueError("Resultado inexistente nesta pergunta. Consulte os dados primeiro.")
    return resultado


def registrar_artefato(artefato: dict) -> None:
    """Registra um gráfico ou arquivo gerado durante a requisição atual."""
    if _artefatos.get() is None:
        _artefatos.set([])
    _artefatos.get().append(artefato)


def drenar_artefatos() -> list[dict]:
    """Devolve e limpa os artefatos da requisição atual."""
    artefatos = list(_artefatos.get() or [])
    _artefatos.set([])
    return artefatos


def _json(valor: Any) -> str:
    """Serializa a resposta da ferramenta (datas e Decimal viram texto)."""
    # Resultados com linhas ficam guardados no servidor (por pergunta) e o
    # modelo recebe só uma prévia de 30 linhas + resultado_id. Gráfico, PDF e
    # Excel usam o resultado completo pelo id: o modelo nunca redigita números.
    if isinstance(valor, dict) and isinstance(valor.get("linhas"), list):
        if _consultas.get() is None:
            _consultas.set({})
        resultado_id = uuid.uuid4().hex[:12]
        _consultas.get()[resultado_id] = valor
        valor = {**valor, "resultado_id": resultado_id, "total_linhas": len(valor["linhas"]),
                 "linhas": valor["linhas"][:30],
                 "orientacao": "Use resultado_id para exportar TODAS as linhas ou "
                               "desenhar gráficos; não copie os valores."}

    def padrao(o: Any) -> str | float:
        if isinstance(o, Decimal):
            return float(o)
        return str(o)
    return json.dumps(valor, ensure_ascii=False, default=padrao)


# ---------------------------------------------------------------------------
# Resolução de filtros por nome -> id (o modelo fala "Serra Clara", não o id)
# ---------------------------------------------------------------------------

# Mapa: filtro externo -> (tabela dim, coluna do nome, coluna do id).
DIMENSOES_FILTRO = {
    "cidade":   ("curated.dim_cidade", "cidade", "cidade_id"),
    "origem":   ("curated.dim_origem", "nome_origem", "origem_id"),
    "equipe":   ("curated.dim_equipe", "nome_equipe", "equipe_id"),
    "corretor": ("curated.dim_corretor", "nome_corretor", "corretor_id"),
    "bairro":   ("curated.dim_bairro", "bairro", "bairro_id"),
}

FINALIDADES = {"venda", "locacao"}
TIPOS = {"apartamento", "casa", "sala_comercial", "terreno"}


def _resolver_id(filtro: str, valor: str) -> int | None:
    """Resolve um nome (ex.: 'Serra Clara') para o id da dimensão (ILIKE)."""
    tabela, coluna_nome, coluna_id = DIMENSOES_FILTRO[filtro]
    linhas = db.consultar(
        f"SELECT {coluna_id} AS id FROM {tabela} "
        f"WHERE {coluna_nome} ILIKE %s LIMIT 1",
        (f"%{valor}%",))
    return linhas[0]["id"] if linhas else None


# ---------------------------------------------------------------------------
# Configuração das métricas (camada semântica)
# ---------------------------------------------------------------------------

# Colunas de filtro existentes em cada view (lista fechada, no código).
# As views de fatos carregam todas as dimensões do Dashboard (migração 006);
# o funil não tem bairro (o lead não tem imóvel) e a meta é só por equipe.
_DIMS = {"cidade_id", "finalidade", "tipo", "origem_id", "equipe_id", "corretor_id"}
FILTROS_POR_VIEW = {
    "analytics.v_funil_mensal": _DIMS,
    "analytics.v_conversao_origem": _DIMS,
    "analytics.v_vgv_mensal": _DIMS | {"bairro_id"},
    "analytics.v_ranking_corretores": _DIMS | {"bairro_id"},
    "analytics.v_motivos_perda": _DIMS | {"bairro_id"},
    "analytics.v_negocios_bairro_tipo": _DIMS | {"bairro_id"},
    "analytics.v_realizado_meta": {"equipe_id"},
}

# Agrupamentos por id são devolvidos com o NOME da dimensão (o modelo e o
# usuário precisam ler "Indicação", não "origem_id = 6").
NOME_POR_ID = {
    "origem_id": ("curated.dim_origem", "nome_origem"),
    "cidade_id": ("curated.dim_cidade", "cidade"),
    "equipe_id": ("curated.dim_equipe", "nome_equipe"),
    "corretor_id": ("curated.dim_corretor", "nome_corretor"),
}

METRICAS: dict[str, dict] = {
    "leads_recebidos": {
        "view": "analytics.v_funil_mensal",
        "medidas": "SUM(leads) AS valor",
        "grupos": {"competencia": "competencia", "origem": "origem_id",
                   "cidade": "cidade_id", "finalidade": "finalidade",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "visitas_realizadas": {
        "view": "analytics.v_funil_mensal",
        "medidas": "SUM(visitas) AS valor",
        "grupos": {"competencia": "competencia", "origem": "origem_id",
                   "cidade": "cidade_id", "finalidade": "finalidade",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "propostas_enviadas": {
        "view": "analytics.v_funil_mensal",
        "medidas": "SUM(propostas) AS valor",
        "grupos": {"competencia": "competencia", "origem": "origem_id",
                   "cidade": "cidade_id", "finalidade": "finalidade",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "negocios_fechados": {
        "view": "analytics.v_funil_mensal",
        "medidas": "SUM(fechados) AS valor",
        "grupos": {"competencia": "competencia", "origem": "origem_id",
                   "cidade": "cidade_id", "finalidade": "finalidade",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "taxa_conversao": {
        "view": "analytics.v_funil_mensal",
        # taxa = fechados / leads no MESMO recorte (definição do catálogo)
        "medidas": "ROUND(SUM(fechados)::NUMERIC / NULLIF(SUM(leads), 0), 4) AS valor",
        "grupos": {"competencia": "competencia", "origem": "origem_id",
                   "cidade": "cidade_id", "finalidade": "finalidade",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "vgv": {
        "view": "analytics.v_vgv_mensal",
        # VGV só conta VENDAS (definição do catálogo); o filtro é forçado.
        "medidas": "SUM(vgv) AS valor",
        "forcar_filtros": {"finalidade": "venda"},
        "grupos": {"competencia": "competencia", "cidade": "cidade_id",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "receita_comissoes": {
        "view": "analytics.v_vgv_mensal",
        "medidas": "SUM(comissao_total) AS valor",
        "grupos": {"competencia": "competencia", "cidade": "cidade_id",
                   "finalidade": "finalidade", "tipo": "tipo",
                   "equipe": "equipe_id", "corretor": "corretor_id"},
    },
    "ticket_medio": {
        "view": "analytics.v_vgv_mensal",
        # ticket médio = VGV / número de vendas (média ponderada correta,
        # diferente de tirar a média das médias do grão da view)
        "medidas": ("SUM(vgv) / NULLIF(SUM(negocios_fechados), 0) AS valor"),
        "forcar_filtros": {"finalidade": "venda"},
        "grupos": {"competencia": "competencia", "cidade": "cidade_id",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "tempo_medio_fechamento": {
        "view": "analytics.v_vgv_mensal",
        "medidas": ("ROUND(SUM(tempo_medio_fechamento_dias * negocios_fechados)"
                    " / NULLIF(SUM(negocios_fechados), 0), 1) AS valor"),
        "grupos": {"competencia": "competencia", "cidade": "cidade_id",
                   "finalidade": "finalidade", "tipo": "tipo",
                   "equipe": "equipe_id", "corretor": "corretor_id"},
    },
    "funil": {
        "view": "analytics.v_funil_mensal",
        "medidas": ("SUM(leads) AS leads, SUM(visitas) AS visitas, "
                    "SUM(propostas) AS propostas, SUM(fechados) AS fechados, "
                    "SUM(perdidos) AS perdidos"),
        "grupos": {"competencia": "competencia", "origem": "origem_id",
                   "cidade": "cidade_id", "finalidade": "finalidade",
                   "tipo": "tipo", "equipe": "equipe_id",
                   "corretor": "corretor_id"},
    },
    "conversao_por_origem": {
        "view": "analytics.v_conversao_origem",
        "medidas": ("SUM(leads) AS leads, SUM(fechados) AS fechados, "
                    "ROUND(SUM(fechados)::NUMERIC / NULLIF(SUM(leads), 0), 4) "
                    "AS taxa_conversao"),
        "grupos": {"origem": "origem", "competencia": "competencia"},
    },
    "ranking_corretores": {
        "view": "analytics.v_ranking_corretores",
        "medidas": ("SUM(negocios_fechados) AS negocios_fechados, "
                    "SUM(vgv_vendas) AS vgv_vendas, "
                    "SUM(comissao_total) AS comissao_total"),
        "grupos": {"corretor": "corretor", "equipe": "equipe",
                   "competencia": "competencia"},
        "ordem": "negocios_fechados DESC",
    },
    "motivos_perda": {
        "view": "analytics.v_motivos_perda",
        "medidas": "SUM(total) AS total",
        "grupos": {"motivo_perda": "motivo_perda", "competencia": "competencia"},
        "ordem": "total DESC",
    },
    "negocios_por_bairro_tipo": {
        "view": "analytics.v_negocios_bairro_tipo",
        "medidas": ("SUM(negocios_fechados) AS negocios_fechados, "
                    "SUM(vgv) AS vgv"),
        "grupos": {"bairro": "bairro", "cidade": "cidade", "tipo": "tipo",
                   "finalidade": "finalidade", "competencia": "competencia"},
        "ordem": "negocios_fechados DESC",
    },
    "realizado_vs_meta": {
        "view": "analytics.v_realizado_meta",
        "medidas": ("SUM(realizado_negocios) AS realizado_negocios, "
                    "SUM(meta_negocios) AS meta_negocios, "
                    "SUM(realizado_vgv) AS realizado_vgv, "
                    "SUM(meta_vgv) AS meta_vgv"),
        "grupos": {"equipe": "equipe", "competencia": "competencia"},
    },
}


# ---------------------------------------------------------------------------
# Ferramentas do agente
# ---------------------------------------------------------------------------

def listar_metricas_e_dimensoes() -> str:
    """Lista o catálogo oficial de métricas (nome, descrição, fórmula, fonte,
    unidade) e as dimensões/filtros disponíveis (cidades, origens, equipes,
    corretores, tipos de imóvel, finalidades e a faixa de meses com dados).
    Use antes de consultar, para escolher a métrica certa."""
    catalogo = db.consultar(
        "SELECT metrica, nome, descricao, formula, fonte, unidade "
        "FROM analytics.catalogo_metricas ORDER BY metrica")
    dims = {
        "cidades": [r["cidade"] for r in db.consultar(
            "SELECT cidade FROM curated.dim_cidade ORDER BY cidade")],
        "origens": [r["nome_origem"] for r in db.consultar(
            "SELECT nome_origem FROM curated.dim_origem ORDER BY nome_origem")],
        "equipes": [r["nome_equipe"] for r in db.consultar(
            "SELECT nome_equipe FROM curated.dim_equipe ORDER BY nome_equipe")],
        "corretores": [r["nome_corretor"] for r in db.consultar(
            "SELECT nome_corretor FROM curated.dim_corretor "
            "WHERE ativo ORDER BY nome_corretor")],
        "bairros": [r["bairro"] for r in db.consultar(
            "SELECT bairro FROM curated.dim_bairro ORDER BY bairro")],
        "tipos_imovel": sorted(TIPOS),
        "finalidades": sorted(FINALIDADES),
        "periodo_dados": db.consultar(
            "SELECT MIN(competencia) AS de, MAX(competencia) AS ate "
            "FROM analytics.v_funil_mensal")[0],
    }
    return _json({"metricas": catalogo, "dimensoes": dims})


def consultar_metrica(metrica: str, data_inicio: str, data_fim: str,
                      agrupar_por: str | None = None,
                      cidade: str | None = None,
                      finalidade: str | None = None,
                      tipo_imovel: str | None = None,
                      origem: str | None = None,
                      equipe: str | None = None,
                      corretor: str | None = None,
                      bairro: str | None = None) -> str:
    """Consulta uma métrica do catálogo nas views da camada semântica.

    CAMINHO PREFERIDO para qualquer número. Parâmetros:
      metrica: identificador do catálogo (ver listar_metricas_e_dimensoes);
      data_inicio / data_fim: datas 'AAAA-MM-DD' do recorte;
      agrupar_por: dimensão opcional ('competencia', 'origem', 'cidade',
        'finalidade', 'tipo', 'equipe', 'corretor', 'bairro', 'motivo_perda');
      cidade, finalidade, tipo_imovel, origem, equipe, corretor, bairro:
        filtros opcionais pelo NOME (ex.: cidade='Serra Clara',
        finalidade='venda', tipo_imovel='apartamento').
    """
    from datetime import date
    try:
        inicio, fim = date.fromisoformat(data_inicio), date.fromisoformat(data_fim)
        if inicio > fim:
            raise ValueError("Período invertido")
    except ValueError:
        return _json({"erro": "Período inválido: informe datas ISO em ordem."})
    cfg = METRICAS.get(metrica)
    if cfg is None:
        return _json({"erro": f"Métrica '{metrica}' não existe.",
                      "metricas_validas": sorted(METRICAS)})

    view = cfg["view"]
    filtros_view = FILTROS_POR_VIEW[view]
    mensal = view == "analytics.v_realizado_meta"
    condicoes = ["competencia BETWEEN %s AND %s" if mensal else "data_ref BETWEEN %s AND %s"]
    valores: list[Any] = [data_inicio[:7], data_fim[:7]] if mensal else [data_inicio, data_fim]
    aplicados: dict[str, str] = {}

    # Filtros forçados pela definição da métrica (ex.: VGV = só vendas).
    for coluna, valor in (cfg.get("forcar_filtros") or {}).items():
        if coluna in filtros_view:
            condicoes.append(f"{coluna} = %s")
            valores.append(valor)
            aplicados[coluna] = valor

    def filtro_nomeado(nome_filtro: str, valor_nome: str) -> None:
        coluna_id = DIMENSOES_FILTRO[nome_filtro][2]
        if coluna_id not in filtros_view:
            raise ValueError(f"Filtro {nome_filtro} indisponível nesta métrica; use SQL validado.")
        id_resolvido = _resolver_id(nome_filtro, valor_nome)
        if id_resolvido is None:
            raise ValueError(f"{nome_filtro} '{valor_nome}' não encontrado.")
        condicoes.append(f"{coluna_id} = %s")
        valores.append(id_resolvido)
        aplicados[nome_filtro] = valor_nome

    try:
        if cidade:
            filtro_nomeado("cidade", cidade)
        if origem:
            filtro_nomeado("origem", origem)
        if equipe:
            filtro_nomeado("equipe", equipe)
        if corretor:
            filtro_nomeado("corretor", corretor)
        if bairro:
            filtro_nomeado("bairro", bairro)
        # Filtros por valor fixo (lista fechada). Filtro que a view não suporta
        # é RECUSADO: ignorá-lo em silêncio geraria um número errado.
        for coluna, valor, validos in (("finalidade", finalidade, FINALIDADES),
                                       ("tipo", tipo_imovel, TIPOS)):
            if not valor:
                continue
            if valor not in validos:
                raise ValueError(f"{coluna} inválido: use {sorted(validos)}.")
            if coluna not in filtros_view:
                raise ValueError(f"A métrica '{metrica}' não aceita filtro por {coluna}.")
            condicoes.append(f"{coluna} = %s")
            valores.append(valor)
            aplicados[coluna] = valor
    except ValueError as exc:
        return _json({"erro": str(exc)})

    group_sql = ""
    select_grupo = ""
    if agrupar_por:
        coluna = cfg["grupos"].get(agrupar_por)
        if coluna is None:
            return _json({
                "erro": f"A métrica '{metrica}' não aceita agrupar por "
                        f"'{agrupar_por}'.",
                "agrupamentos_validos": sorted(cfg["grupos"])})
        group_sql = f"GROUP BY v.{coluna}"
        if coluna in NOME_POR_ID:
            tabela, nome = NOME_POR_ID[coluna]
            select_grupo = (f"(SELECT d.{nome} FROM {tabela} d "
                            f"WHERE d.{coluna} = v.{coluna}) AS {agrupar_por}, ")
        else:
            select_grupo = f"v.{coluna} AS {agrupar_por}, "

    ordem = cfg.get("ordem")
    order_sql = ""
    if ordem and agrupar_por:
        order_sql = f"ORDER BY {ordem}"
    elif agrupar_por == "competencia":
        order_sql = "ORDER BY competencia"

    where = " AND ".join(condicoes)
    sql = (f"SELECT {select_grupo}{cfg['medidas']} FROM {view} v "
           f"WHERE {where} {group_sql} {order_sql} LIMIT 500")
    resultado = {
        "metrica": metrica, "periodo": {"de": data_inicio, "ate": data_fim},
        "filtros_aplicados": aplicados, "agrupamento": agrupar_por,
        "fonte": view, "linhas": db.consultar(sql, valores),
    }
    if agrupar_por:
        # Total do período calculado pelo BANCO com a mesma fórmula: o modelo
        # não deve somar linhas (erra a conta e taxas/médias não se somam).
        resultado["total_do_periodo"] = db.consultar(
            f"SELECT {cfg['medidas']} FROM {view} v WHERE {where}", valores)[0]
    return _json(resultado)


def descrever_tabelas() -> str:
    """Devolve o dicionário de dados (tabela, coluna, tipo, descrição em
    português) das tabelas e views que o agente pode consultar. Use antes de
    escrever SQL livre com executar_sql_somente_leitura."""
    # Os %s dentro do format() são do SQL, não do psycopg2: por isso estão
    # escapados como %%s (o driver converte %% -> % ao montar a query).
    linhas = db.consultar(
        """
        SELECT table_schema AS schema, table_name AS tabela, column_name AS coluna,
               data_type AS tipo, col_description(format('%%s.%%s', table_schema,
               table_name)::regclass, ordinal_position) AS descricao_coluna
        FROM information_schema.columns
        WHERE (table_schema = 'analytics')
           OR (table_schema = 'curated' AND table_name <> 'clientes')
        ORDER BY table_schema, table_name, ordinal_position
        """)
    return _json({"tabelas_permitidas": linhas,
                  "observacao": "curated.clientes existe mas está bloqueada "
                                "(dados pessoais)."})


def executar_sql_somente_leitura(sql: str) -> str:
    """Executa um SELECT escrito pelo modelo para perguntas que o catálogo de
    métricas não cobre. O SQL passa por validação rigorosa antes de rodar:
    um único comando, apenas SELECT, sem funções perigosas, só tabelas da
    lista branca, sem colunas sensíveis e com LIMIT de 1.000 linhas. Se for
    recusado, a ferramenta devolve o motivo."""
    try:
        sql_seguro = validar_sql(sql)
    except SqlRecusado as exc:
        return _json({"erro": f"SQL recusado pela validação: {exc}"})
    try:
        linhas = db.consultar(sql_seguro)
    except Exception as exc:
        return _json({"erro": f"A consulta falhou no banco: {exc}",
                      "sql": sql_seguro})
    return _json({"sql_executado": sql_seguro, "linhas": linhas,
                  "total_linhas": len(linhas)})


def gerar_grafico(tipo: str, titulo: str, resultado_id: str,
                  coluna_rotulo: str, colunas_valores: list[str],
                  limite: int | None = None) -> str:
    """Desenha no chat dados de uma consulta desta pergunta, sem redigitar valores.

    resultado_id: identificador devolvido por consultar_metrica ou executar_sql.
    coluna_rotulo: coluna textual do resultado (por exemplo competencia).
    colunas_valores: colunas numéricas para as séries (por exemplo valor).
    tipo: linha, barra, pizza ou funil.
    limite: desenha só as N primeiras linhas (ex.: 5 para um "top 5"; o
      resultado de ranking já vem ordenado do maior para o menor).
    """
    try:
        linhas = obter_resultado(resultado_id)["linhas"][:limite or None]
        rotulos = [str(linha[coluna_rotulo]) for linha in linhas]
        series = [{"nome": coluna, "dados": [float(linha[coluna] or 0) for linha in linhas]}
                  for coluna in colunas_valores]
    except (ValueError, KeyError, TypeError) as exc:
        return _json({"erro": str(exc)})
    if tipo not in {"linha", "barra", "pizza", "funil"}:
        return _json({"erro": "tipo deve ser linha, barra, pizza ou funil."})
    if not rotulos or not series:
        return _json({"erro": "rotulos e series são obrigatórios."})

    # Monta a especificação ECharts que o frontend desenha no chat.
    # Título em cima e legenda embaixo, para não se sobreporem no chat.
    spec: dict[str, Any] = {"title": {"text": titulo, "textStyle": {"fontSize": 13}},
                            "grid": {"top": 45, "bottom": 60, "containLabel": True}}
    if tipo == "pizza":
        spec["series"] = [{
            "type": "pie", "radius": "60%",
            "data": [{"name": r, "value": v} for r, v in
                     zip(rotulos, series[0]["dados"], strict=True)],
        }]
        spec["tooltip"] = {"trigger": "item"}
    elif tipo == "funil":
        spec["series"] = [{
            "type": "funnel",
            "data": [{"name": r, "value": v} for r, v in
                     zip(rotulos, series[0]["dados"], strict=True)],
        }]
        spec["tooltip"] = {"trigger": "item"}
    else:
        spec["tooltip"] = {"trigger": "axis"}
        spec["legend"] = {"data": [s.get("nome", "") for s in series], "bottom": 0}
        spec["xAxis"] = {"type": "category", "data": rotulos,
                         "axisLabel": {"interval": 0, "rotate": 30 if len(rotulos) > 6 else 0}}
        spec["yAxis"] = {"type": "value"}
        spec["series"] = [
            {"name": s.get("nome", ""), "type": "line" if tipo == "linha"
             else "bar", "data": s.get("dados", []), "smooth": True}
            for s in series
        ]
    registrar_artefato({"tipo": "grafico", "spec": spec})
    return _json({"ok": True, "mensagem": "Gráfico gerado e exibido no chat.",
                  "spec": spec})


def gerar_relatorio_pdf(titulo: str, periodo: str, analise: str,
                        resultado_ids: list[str],
                        tipo_grafico: str = "barra") -> str:
    """Gera um relatório PDF com a SUA análise + tabelas e gráficos dos dados.

    titulo: título do relatório; periodo: período analisado (texto);
    analise: resumo executivo e conclusões em português (parágrafos separados
      por linha em branco). Cite apenas números vindos das consultas.
    resultado_ids: um ou mais resultado_id devolvidos por consultar_metrica ou
      executar_sql_somente_leitura NESTA pergunta. Cada um vira uma seção com
      tabela completa e gráfico — o servidor usa os dados reais, não copie
      linhas nem valores.
    tipo_grafico: 'barra', 'linha' (evolução mensal) ou 'pizza'.
    """
    try:
        secoes = []
        for resultado_id in resultado_ids:
            resultado = obter_resultado(resultado_id)
            linhas = resultado["linhas"]
            if not linhas:
                continue
            colunas = list(linhas[0])
            metrica = resultado.get("metrica")
            subtitulo = (metrica.replace("_", " ").capitalize() if metrica
                         else "Consulta SQL validada")
            filtros = resultado.get("filtros_aplicados") or {}
            fonte = resultado.get("fonte", "SQL validado")
            nota = f"Fonte: {fonte}. Filtros: {filtros or 'nenhum'}."
            if resultado.get("total_do_periodo"):
                nota += " Total do período: " + "; ".join(
                    f"{k} = {relatorios.formatar(v)}"
                    for k, v in resultado["total_do_periodo"].items()) + "."
            secoes.append({"tipo": "tabela", "titulo": subtitulo, "nota": nota,
                           "colunas": colunas,
                           "linhas": [[linha[c] for c in colunas] for linha in linhas]})
            numericas = [c for c in colunas
                         if isinstance(linhas[0][c], (int, float, Decimal))]
            rotulo = next((c for c in colunas if c not in numericas), None)
            if numericas and rotulo and len(linhas) > 1:
                secoes.append({"tipo": "grafico", "grafico": {
                    "tipo": tipo_grafico, "titulo": subtitulo,
                    "rotulos": [str(linha[rotulo]) for linha in linhas[:36]],
                    "valores": [float(linha[numericas[0]] or 0) for linha in linhas[:36]]}})
        if not secoes:
            return _json({"erro": "Nenhum dado nas consultas informadas."})
        nome = relatorios.gerar_pdf(titulo, periodo, analise, secoes)
    except (ValueError, KeyError, TypeError) as exc:
        return _json({"erro": f"Falha ao gerar o PDF: {exc}"})
    return _arquivo(nome, "pdf", titulo)


def _arquivo(nome: str, formato: str, titulo: str) -> str:
    """Publica referência temporária ao arquivo criado pelo servidor."""
    url = f"/arquivos/{nome}"
    registrar_artefato({"tipo": "arquivo", "nome_arquivo": nome, "url": url,
                        "formato": formato, "titulo": titulo})
    # O link vai para o chat como artefato (botão de download); o modelo não
    # recebe a URL interna, para não escrevê-la no texto.
    return _json({"ok": True, "formato": formato, "validade_horas": 24,
                  "mensagem": "Arquivo gerado: o botão de download já aparece no chat."})


def gerar_planilha_excel(nome_planilha: str, resultado_id: str) -> str:
    """Exporta TODAS as linhas de um resultado consultado nesta pergunta.

    Informe resultado_id recebido da consulta, sem copiar linhas ou números.
    Mesmo quando a prévia da consulta tem 30 linhas, exporta até 1000 linhas.
    """
    try:
        linhas = obter_resultado(resultado_id)["linhas"]
        if not linhas:
            return _json({"erro": "Consulta sem dados para exportar."})
        colunas = list(linhas[0])
        nome = relatorios.gerar_excel(nome_planilha, colunas,
                                     [[linha[c] for c in colunas] for linha in linhas])
    except (ValueError, KeyError, TypeError) as exc:
        return _json({"erro": f"Falha ao gerar a planilha: {exc}"})
    return _arquivo(nome, "xlsx", nome_planilha)


# Lista no formato que o Agno espera (funções com docstring).
FERRAMENTAS = [
    listar_metricas_e_dimensoes,
    consultar_metrica,
    descrever_tabelas,
    executar_sql_somente_leitura,
    gerar_grafico,
    gerar_relatorio_pdf,
    gerar_planilha_excel,
]
