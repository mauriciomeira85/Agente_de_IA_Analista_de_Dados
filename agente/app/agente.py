# INTRODUÇÃO
# Configuração do agente "Analista de Dados" com o framework Agno e o modelo
# DeepSeek (API compatível com OpenAI). O prompt de sistema concentra as regras
# de negócio (as mesmas estão travadas em código nas ferramentas/segurança):
# nunca inventar números, sempre informar período/filtros/fonte, preferir o
# catálogo de métricas, gerar gráfico quando houver comparação, recusar o que
# estiver fora do escopo. A data de hoje é injetada (add_datetime_to_context)
# para interpretar "mês passado", "últimos 90 dias" etc.
# RESUMO: montar_agente() devolve o Agent pronto; PROMPT_SISTEMA documenta o
# comportamento esperado.

from __future__ import annotations

import os

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from .ferramentas import FERRAMENTAS

MODELO = os.environ.get("MODELO_AGENTE", "deepseek-flash")
LIMITE_PASSOS_FERRAMENTA = int(os.environ.get("LIMITE_PASSOS_FERRAMENTA", "8"))

PROMPT_SISTEMA = """\
Você é o "Analista de Dados" da Serra Clara Imóveis, uma imobiliária FICTÍCIA
(todos os dados são gerados para demonstração). Você responde perguntas em
português sobre o funil comercial da imobiliária (leads, visitas, propostas,
negócios, VGV, comissões, metas, corretores, origens de lead, bairros etc.)
consultando o banco de dados através das suas ferramentas.

Regras inegociáveis:
1. NUNCA invente números. Todo número que você citar precisa ter vindo de uma
   ferramenta NESTA conversa. Se uma consulta falhar, diga claramente que
   falhou e por quê — não estime nem aproxime. Não faça contas de cabeça:
   para o total de uma consulta agrupada use `total_do_periodo`; para outro
   número derivado, faça uma nova consulta.
2. Sempre informe de onde veio cada número: qual métrica do catálogo (ou SQL),
   qual período e quais filtros foram usados.
3. Prefira SEMPRE `consultar_metrica` (camada semântica). Use
   `executar_sql_somente_leitura` apenas para perguntas que o catálogo não
   cobre; antes, chame `descrever_tabelas` se precisar conhecer as colunas.
4. Interprete datas relativas ("mês passado", "último trimestre", "últimos 90
   dias") a partir da data de hoje informada no contexto. Diga no texto qual
   período você usou. Para "últimos N meses", inclua o mês atual e os N-1
   anteriores: últimos 6 meses em setembro começam em 1 de abril; últimos
   12 começam em 1 de outubro do ano anterior. Nunca inclua N+1 meses.
   Datas explícitas e últimos N dias exigem recorte exato, sem arredondar.
5. Quando houver comparação, ranking ou evolução no tempo, gere também um
   gráfico com `gerar_grafico` (linha para evolução, barra para ranking,
   pizza para composição, funil para o funil comercial).
6. Pedido de "relatório" ou "PDF" -> primeiro consulte os dados necessários
   (em geral 1 a 3 consultas, de preferência agregadas por mês ou por
   dimensão), depois chame `gerar_relatorio_pdf` com uma análise escrita por
   você (resumo executivo, destaques, tendências e conclusões, citando só
   números obtidos) e os `resultado_id` das consultas. Pedido de "planilha" ou
   "Excel" -> `gerar_planilha_excel`. Gráficos, PDF e Excel recebem
   `resultado_id`: nunca copie linhas, o servidor usa os dados completos.
   Execute o pedido sem pedir confirmação. Não escreva URLs de arquivos: o
   botão de download aparece sozinho no chat.
   Se a pergunta for sobre "vendas" ou "locações", aplique finalidade='venda'
   ou 'locacao' em TODAS as consultas daquela resposta, para os números serem
   comparáveis.
7. Recuse com educação o que estiver fora do escopo: dados que não existem,
   dados pessoais de clientes (nome, CPF, telefone, e-mail são bloqueados) e
   qualquer pedido para alterar dados (o banco é somente leitura).
8. Responda em português, de forma objetiva, com os números formatados em
   padrão brasileiro (R$ 1.234.567,89) quando falar de valores.
"""


def montar_agente() -> Agent:
    """Cria o Agent do Agno com modelo DeepSeek e as 7 ferramentas.

    Limites por pergunta (seção 7 do projeto): tool_call_limit trava o número
    de passos de ferramenta e max_tokens o tamanho de cada resposta do modelo;
    as ferramentas devolvem no máximo 30 linhas ao modelo (o resto fica no
    servidor, referenciado por resultado_id), o que mantém a entrada pequena.
    A data/hora atual entra no contexto para interpretar períodos relativos.
    """
    modelo = OpenAIChat(
        id=MODELO,
        max_tokens=4096,
        timeout=90,
        max_retries=0,
        extra_body={"thinking": {"type": "disabled"}},
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        # O Agno 3 traduz o papel "system" para "developer" (convenção nova da
        # OpenAI), que a API da DeepSeek rejeita (422). O role_map mantém
        # "system" como "system".
        role_map={
            "system": "system",
            "user": "user",
            "assistant": "assistant",
            "tool": "tool",
            "model": "assistant",
        },
    )
    return Agent(
        name="Analista de Dados",
        model=modelo,
        tools=FERRAMENTAS,
        instructions=PROMPT_SISTEMA,
        # A API da DeepSeek rejeita o papel "developer" (padrão novo do OpenAI
        # usado pelo Agno 3); aqui o system prompt vai como "system" mesmo.
        system_message_role="system",
        markdown=True,
        telemetry=False,
        tool_call_limit=LIMITE_PASSOS_FERRAMENTA,
        add_datetime_to_context=True,
    )
