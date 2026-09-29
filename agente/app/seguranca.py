# INTRODUÇÃO
# Trava de segurança do SQL livre escrito pelo modelo (ferramenta
# `executar_sql_somente_leitura`). A aplicação não tem login — é pública —,
# então a validação é feita EM CÓDIGO, não só no prompt do agente.
#
# O SQL só é executado se passar por TODAS as checagens:
#   1. um único comando (sem ";" empilhando comandos);
#   2. apenas SELECT (nem WITH ... INSERT/UPDATE/DELETE escondido);
#   3. sem funções perigosas (pg_sleep, pg_read_file, dblink, copy etc.);
#   4. apenas as tabelas da lista branca (views de analytics + tabelas de
#      curated sem dados pessoais);
#   5. colunas sensíveis bloqueadas (nome/CPF/telefone/e-mail de clientes);
#   6. LIMIT automático de 1.000 linhas.
#
# Recusou -> devolve o motivo ao modelo (que informa o usuário). Isso é
# cumulativo com as travas do banco (usuário somente leitura, read-only,
# statement_timeout de 10 s): defesa em profundidade.
# RESUMO: validar_sql() -> (sql_seguro, None) ou (None, motivo_recusa).

from __future__ import annotations

import sqlglot
from sqlglot import exp

DIALETO = "postgres"
LIMITE_LINHAS = 1000

# Lista branca de tabelas/views que o SQL do modelo pode consultar.
# curated.clientes NÃO está aqui: os dados pessoais fictícios ficam inacessíveis.
TABELAS_PERMITIDAS = {
    # Camada semântica (caminho preferido do agente)
    "analytics.v_negocios_detalhe",
    "analytics.v_funil_mensal",
    "analytics.v_vgv_mensal",
    "analytics.v_conversao_origem",
    "analytics.v_ranking_corretores",
    "analytics.v_motivos_perda",
    "analytics.v_negocios_bairro_tipo",
    "analytics.v_realizado_meta",
    "analytics.catalogo_metricas",
    # Dimensões e fatos de curated (sem clientes)
    "curated.dim_cidade",
    "curated.dim_bairro",
    "curated.dim_equipe",
    "curated.dim_corretor",
    "curated.dim_origem",
    "curated.dim_campanha",
    "curated.dim_calendario",
    "curated.imoveis",
    "curated.fato_leads",
    "curated.fato_visitas",
    "curated.fato_propostas",
    "curated.fato_negocios",
    "curated.metas_mensais",
}

# Colunas sensíveis bloqueadas em qualquer tabela (mesmo as permitidas).
COLUNAS_BLOQUEADAS = {"cpf", "telefone", "email", "nome"}

# Funções perigosas: negação de serviço, leitura de arquivos do servidor,
# acesso a outros bancos e escrita em disco.
FUNCOES_PROIBIDAS = {
    "pg_sleep", "pg_read_file", "pg_read_binary_file", "pg_write_file",
    "pg_ls_dir", "pg_stat_file", "dblink", "dblink_connect", "copy",
    "set_config", "pg_terminate_backend", "pg_cancel_backend",
    "lo_import", "lo_export", "current_setting",
    # Executam SQL arbitrário passado como texto (driblariam a lista branca).
    "query_to_xml", "query_to_xmlschema", "database_to_xml", "table_to_xml",
}

# Tipos de nó sqlglot que indicam escrita ou comando administrativo.
NOS_PROIBIDOS = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create,
    exp.TruncateTable, exp.Command, exp.Copy, exp.Merge, exp.Grant,
    exp.Commit, exp.Rollback, exp.Into, exp.Lock,
)


class SqlRecusado(ValueError):
    """SQL recusado pela trava de segurança; a mensagem vai para o modelo."""


def _validar_unico_comando(arvores: list) -> exp.Expression:
    """Garante exatamente um comando (bloqueia 'SELECT 1; DROP TABLE x')."""
    arvores = [a for a in arvores if a is not None]
    if len(arvores) != 1:
        raise SqlRecusado("Só é permitido um único comando SQL por consulta.")
    return arvores[0]


def _validar_somente_select(arvore: exp.Expression) -> None:
    """Aceita apenas SELECT puro (com ou sem CTEs de leitura)."""
    for no in arvore.walk():
        if isinstance(no, NOS_PROIBIDOS):
            raise SqlRecusado(
                f"Comando não permitido ({type(no).__name__}): apenas SELECT.")
    if not isinstance(arvore, (exp.Select, exp.Union, exp.Subquery, exp.With)):
        # WITH ... SELECT chega como exp.With; qualquer outra raiz é recusada.
        if not (isinstance(arvore, exp.With) and isinstance(
                arvore.this, (exp.Select, exp.Union))):
            raise SqlRecusado("Apenas consultas SELECT são permitidas.")


def _validar_tabelas(arvore: exp.Expression) -> None:
    """Toda tabela referenciada precisa estar na lista branca.

    Aliases de CTE (WITH x AS ...) não são tabelas: são excluídos da checagem.
    """
    aliases_cte = {str(cte.alias).lower() for cte in arvore.find_all(exp.CTE)}
    for tabela in arvore.find_all(exp.Table):
        nome = tabela.name.lower()
        if not tabela.db and nome in aliases_cte:
            continue
        schema = (tabela.db or "").lower() or "public"
        chave = f"{schema}.{nome}"
        if tabela.catalog or chave not in TABELAS_PERMITIDAS:
            raise SqlRecusado(
                f"Tabela '{chave}' não permitida. Use as views de analytics "
                "ou as tabelas de curated listadas em descrever_tabelas().")


def _validar_colunas(arvore: exp.Expression) -> None:
    """Bloqueia referência a colunas sensíveis (nome, CPF, telefone, e-mail)."""
    for coluna in arvore.find_all(exp.Column):
        if coluna.name.lower() in COLUNAS_BLOQUEADAS:
            raise SqlRecusado(
                f"Coluna '{coluna.name}' contém dado pessoal e está bloqueada "
                "para o agente.")


def _validar_funcoes(arvore: exp.Expression) -> None:
    """Bloqueia funções perigosas (pg_sleep, pg_read_file, dblink, etc.).

    Funções desconhecidas chegam como exp.Anonymous (sql_name() devolve
    'ANONYMOUS'), então o nome é lido de `this` nesse caso.
    """
    for funcao in arvore.find_all(exp.Func):
        if isinstance(funcao, exp.Anonymous):
            nome = str(funcao.this).lower()
        else:
            nome = funcao.sql_name().lower()
        # Além da lista, qualquer função administrativa pg_*, dblink* ou lo_*.
        if nome in FUNCOES_PROIBIDAS or nome.startswith(("pg_", "dblink", "lo_")):
            raise SqlRecusado(f"Função '{nome}' não é permitida.")


def _aplicar_limite(arvore: exp.Expression) -> exp.Expression:
    """Garante LIMIT <= 1.000 (adiciona ou reduz o LIMIT do modelo)."""
    limite = arvore.args.get("limit")
    if limite is None and isinstance(arvore, (exp.Select, exp.Union)):
        arvore.set("limit", exp.Limit(expression=exp.Literal.number(LIMITE_LINHAS)))
    elif limite is not None:
        try:
            valor = int(limite.expression.name)
            if valor > LIMITE_LINHAS:
                limite.set("expression", exp.Literal.number(LIMITE_LINHAS))
        except (ValueError, AttributeError):
            # LIMIT não literal (expressão): substitui pelo teto fixo.
            limite.set("expression", exp.Literal.number(LIMITE_LINHAS))
    return arvore


def validar_sql(sql: str) -> str:
    """Valida o SQL do modelo e devolve a versão segura para execução.

    Levanta SqlRecusado com o motivo (em linguagem que o modelo repassa ao
    usuário) quando qualquer trava é acionada.
    """
    if not sql or not sql.strip():
        raise SqlRecusado("SQL vazio.")
    try:
        arvores = sqlglot.parse(sql, read=DIALETO)
    except Exception as exc:
        raise SqlRecusado(f"SQL inválido: {exc}") from exc

    arvore = _validar_unico_comando(arvores)
    _validar_somente_select(arvore)
    _validar_tabelas(arvore)
    _validar_colunas(arvore)
    _validar_funcoes(arvore)
    if isinstance(arvore, exp.Subquery):
        arvore = exp.select("*").from_(arvore.subquery("consulta"))
    arvore = _aplicar_limite(arvore)
    return arvore.sql(dialect=DIALETO)
