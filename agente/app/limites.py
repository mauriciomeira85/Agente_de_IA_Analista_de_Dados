# INTRODUÇÃO
# Limites de uso do agente, travados em código (a aplicação é pública, sem
# login). Três barreiras:
#   1. por IP: N perguntas por hora (contador em audit.limite_ip, janela fixa
#      de 1 hora — simples e auditável);
#   2. por pergunta: máximo de passos de ferramenta (tool_call_limit do Agno,
#      configurado em agente.py) e timeout de 10 s por SQL (banco);
#   3. teto diário de custo na DeepSeek: soma o custo estimado em
#      audit.agente_execucoes do dia; ao atingir, o chat desliga com uma
#      mensagem amigável.
# O IP real vem do header CF-Connecting-IP (Cloudflare Tunnel) quando presente.
# RESUMO: verificar_limites(ip) levanta LimiteExcedido; calcular_custo()
# estima o custo de cada execução, gravado em audit.agente_execucoes, cuja
# soma do dia alimenta o teto diário.

from __future__ import annotations

import os

from . import db

LIMITE_PERGUNTAS_POR_HORA = int(os.environ.get("LIMITE_PERGUNTAS_POR_HORA", "20"))
TETO_CUSTO_DIARIO_USD = float(os.environ.get("TETO_CUSTO_DIARIO_USD", "2.00"))

# Preços por MILHÃO de tokens (USD), configuráveis por ambiente porque a
# tabela da DeepSeek muda com o tempo. Valores padrão: referência conservadora.
PRECO_ENTRADA_1M = float(os.environ.get("PRECO_ENTRADA_USD_1M", "0.30"))
PRECO_SAIDA_1M = float(os.environ.get("PRECO_SAIDA_USD_1M", "1.20"))


class LimiteExcedido(Exception):
    """Limite de uso atingido; a mensagem é amigável e vai para o usuário."""


def verificar_limites(ip: str) -> None:
    """Aplica o limite por IP e o teto diário de custo.

    Deve ser chamada ANTES de rodar o agente. O contador por IP já é
    incrementado aqui (mesmo que a pergunta falhe depois, ela consumiu
    processamento).
    """
    # --- teto diário de custo ---
    linha = db.consultar(
        "SELECT COALESCE(SUM(custo_usd), 0) AS custo "
        "FROM audit.agente_execucoes WHERE executada_em::date = CURRENT_DATE")
    custo_hoje = float(linha[0]["custo"]) if linha else 0.0
    if custo_hoje >= TETO_CUSTO_DIARIO_USD:
        raise LimiteExcedido(
            "O assistente atingiu o limite diário de uso. "
            "Ele volta a responder amanhã. Obrigado pela compreensão!")

    # --- limite de perguntas por IP por hora (upsert na janela corrente) ---
    db.gravar(
        """
        INSERT INTO audit.limite_ip (ip, janela_inicio, perguntas)
        VALUES (%s::inet, date_trunc('hour', now()), 1)
        ON CONFLICT (ip, janela_inicio)
        DO UPDATE SET perguntas = audit.limite_ip.perguntas + 1
        """,
        (ip,))
    linha = db.consultar(
        "SELECT perguntas FROM audit.limite_ip "
        "WHERE ip = %s::inet AND janela_inicio = date_trunc('hour', now())",
        (ip,))
    if linha and linha[0]["perguntas"] > LIMITE_PERGUNTAS_POR_HORA:
        raise LimiteExcedido(
            f"Você atingiu o limite de {LIMITE_PERGUNTAS_POR_HORA} perguntas "
            "por hora. Tente novamente em alguns minutos.")


def calcular_custo(tokens_entrada: int, tokens_saida: int) -> float:
    """Custo estimado da execução em USD, a partir dos tokens medidos."""
    return round(tokens_entrada * PRECO_ENTRADA_1M / 1_000_000
                 + tokens_saida * PRECO_SAIDA_1M / 1_000_000, 6)
