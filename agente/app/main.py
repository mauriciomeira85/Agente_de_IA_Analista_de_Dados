# INTRODUÇÃO
# API do serviço do agente de IA (FastAPI). Endpoints:
#   POST /chat              -> resposta em STREAMING (SSE): tokens de texto,
#                              eventos de gráfico (spec ECharts) e de arquivo
#                              (link de download), e evento final com métricas;
#   GET  /conversas/{sessao}-> histórico da sessão anônima (vem do banco);
#   GET  /arquivos/{nome}   -> download de PDF/Excel gerado (máx. 24 h);
#   GET  /saude             -> healthcheck.
# O frontend (Next.js) faz proxy destes endpoints, então o navegador nunca fala
# direto com este serviço. Limites de uso (IP, custo diário) são aplicados em
# código antes de cada pergunta; histórico e auditoria vão para app.* e audit.*.
# RESUMO: orquestra limites -> histórico -> Agno (streaming) -> artefatos ->
# persistência (mensagens + execução com tokens e custo).

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db, limites
from .agente import montar_agente
from .ferramentas import drenar_artefatos, iniciar_contexto
from .relatorios import ARQUIVOS_DIR, VALIDADE_SEGUNDOS, limpar_antigos


@asynccontextmanager
async def lifespan(app):
    """Remove artefatos vencidos mesmo quando não há novas perguntas."""
    async def limpar():
        while True:
            limpar_antigos()
            await asyncio.sleep(300)
    tarefa = asyncio.create_task(limpar())
    yield
    tarefa.cancel()
    with suppress(asyncio.CancelledError):
        await tarefa

app = FastAPI(title="Agente Analista de Dados", version="1.1.0", lifespan=lifespan)


class PerguntaChat(BaseModel):
    """Corpo do POST /chat: sessão anônima (uuid do navegador) + pergunta."""
    sessao: str = Field(min_length=8, max_length=64)
    pergunta: str = Field(min_length=1, max_length=2000)


def _ip_real(request: Request) -> str:
    """IP do visitante: atrás do Cloudflare Tunnel vem em CF-Connecting-IP."""
    return (request.headers.get("cf-connecting-ip")
            or (request.client.host if request.client else "0.0.0.0"))


def _conversa_da_sessao(sessao: str) -> str:
    """Devolve o conversa_id da sessão, criando a conversa se necessário."""
    linhas = db.consultar(
        "SELECT conversa_id FROM app.agente_conversas WHERE sessao = %s "
        "ORDER BY criada_em DESC LIMIT 1",
        (sessao,))
    if linhas:
        return str(linhas[0]["conversa_id"])
    conversa_id = str(uuid.uuid4())
    db.gravar(
        "INSERT INTO app.agente_conversas (conversa_id, sessao) VALUES (%s, %s)",
        (conversa_id, sessao))
    return conversa_id


def _historico(conversa_id: str, limite: int = 10) -> list[dict]:
    """Últimas mensagens da conversa (contexto curto para o modelo)."""
    linhas = db.consultar(
        "SELECT papel, conteudo FROM app.agente_mensagens "
        "WHERE conversa_id = %s ORDER BY mensagem_id DESC LIMIT %s",
        (conversa_id, limite))
    return list(reversed(linhas))


def _montar_entrada(pergunta: str, historico: list[dict]) -> str:
    """Monta a entrada do modelo: histórico recente + pergunta atual.

    Optamos por histórico manual (em vez do storage do Agno) para manter o
    histórico no NOSSO schema app.*, que já é auditado e compartilhado com o
    navegador.
    """
    if not historico:
        return pergunta
    linhas = ["Histórico da conversa até aqui:"]
    for msg in historico:
        papel = "Usuário" if msg["papel"] == "usuario" else "Assistente"
        linhas.append(f"{papel}: {msg['conteudo'][:800]}")
    linhas.append(f"\nPergunta atual do usuário: {pergunta}")
    return "\n".join(linhas)


def _sse(payload: dict) -> str:
    """Formata um evento SSE (data: <json>\\n\\n)."""
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@app.post("/chat")
async def chat(pergunta_chat: PerguntaChat, request: Request):
    """Responde uma pergunta em streaming (Server-Sent Events)."""
    ip = _ip_real(request)
    try:
        limites.verificar_limites(ip)
    except limites.LimiteExcedido as exc:
        return JSONResponse(status_code=429, content={"erro": str(exc)})

    conversa_id = _conversa_da_sessao(pergunta_chat.sessao)
    historico = _historico(conversa_id)
    db.gravar(
        "INSERT INTO app.agente_mensagens (conversa_id, papel, conteudo) "
        "VALUES (%s, 'usuario', %s)",
        (conversa_id, pergunta_chat.pergunta))

    entrada = _montar_entrada(pergunta_chat.pergunta, historico)

    async def gerar_eventos():
        """Gerador SSE: roda o Agno e emite tokens, artefatos e o resumo."""
        from agno.run.agent import RunContentEvent, ToolCallCompletedEvent

        iniciar_contexto()
        inicio = time.time()
        texto_final: list[str] = []
        ferramentas_usadas: list[str] = []
        sql_executado: str | None = None
        tokens_entrada = tokens_saida = 0
        try:
            async for evento in montar_agente().arun(entrada, stream=True, stream_events=True):
                if isinstance(evento, RunContentEvent) and evento.content:
                    texto_final.append(evento.content)
                    yield _sse({"tipo": "token", "texto": evento.content})
                elif isinstance(evento, ToolCallCompletedEvent) and evento.tool:
                    nome_tool = evento.tool.tool_name
                    ferramentas_usadas.append(nome_tool)
                    if nome_tool == "executar_sql_somente_leitura":
                        sql_executado = str(evento.tool.tool_args)
                # Métricas de tokens chegam no evento final do run.
                if getattr(evento, "metrics", None):
                    tokens_entrada = evento.metrics.input_tokens or tokens_entrada
                    tokens_saida = evento.metrics.output_tokens or tokens_saida

            # Artefatos (gráficos e arquivos) gerados pelas ferramentas.
            artefatos = drenar_artefatos()
            for artefato in artefatos:
                yield _sse(artefato)
            db.gravar(
                "INSERT INTO app.agente_mensagens (conversa_id, papel, conteudo, artefatos) "
                "VALUES (%s, 'assistente', %s, %s::jsonb)",
                (conversa_id, "".join(texto_final),
                 json.dumps(artefatos, ensure_ascii=False)))
            yield _sse({"tipo": "fim", "conversa_id": conversa_id,
                        "duracao_ms": int((time.time() - inicio) * 1000)})
        except Exception as exc:  # falha do modelo/ferramenta: informar, nunca inventar
            yield _sse({"tipo": "erro",
                        "mensagem": "A consulta falhou. Tente uma pergunta mais específica."})
            logging.getLogger(__name__).warning("Falha na execução: %r", exc)
        finally:
            # Auditoria SEMPRE (inclusive em falha): o custo consumido entra no
            # teto diário mesmo quando a resposta não chega ao fim.
            drenar_artefatos()
            db.gravar(
                """INSERT INTO audit.agente_execucoes
                   (conversa_id, pergunta, ferramentas, sql_executado,
                    duracao_ms, tokens_entrada, tokens_saida, custo_usd, ip)
                   VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s::inet)""",
                (conversa_id, pergunta_chat.pergunta,
                 json.dumps(ferramentas_usadas), sql_executado,
                 int((time.time() - inicio) * 1000), tokens_entrada, tokens_saida,
                 limites.calcular_custo(tokens_entrada, tokens_saida), ip))

    return StreamingResponse(gerar_eventos(), media_type="text/event-stream")


@app.get("/conversas/{sessao}")
def conversas(sessao: str):
    """Histórico da sessão anônima (para o chat reabrir de onde parou)."""
    linhas = db.consultar(
        """SELECT m.papel, m.conteudo, m.artefatos, m.criada_em
           FROM app.agente_mensagens m
           JOIN app.agente_conversas c ON c.conversa_id = m.conversa_id
           WHERE c.sessao = %s
           ORDER BY m.mensagem_id DESC LIMIT 50""",
        (sessao,))
    return {"mensagens": list(reversed(linhas))}


# Nome de arquivo gerado: 32 hex + extensão (nunca vem caminho do usuário).
NOME_ARQUIVO = re.compile(r"^[a-f0-9]{32}\.(pdf|xlsx)$")


@app.get("/arquivos/{nome}")
def arquivos(nome: str):
    """Download de PDF/Excel gerado pelo agente (válido por 24 h)."""
    if not NOME_ARQUIVO.match(nome):
        return JSONResponse(status_code=404, content={"erro": "não encontrado"})
    caminho = Path(ARQUIVOS_DIR) / nome
    if not caminho.exists():
        return JSONResponse(status_code=404,
                            content={"erro": "arquivo expirado ou inexistente"})
    if time.time() - caminho.stat().st_mtime > VALIDADE_SEGUNDOS:
        caminho.unlink(missing_ok=True)
        return JSONResponse(status_code=410, content={"erro": "arquivo expirado"})
    tipo = ("application/pdf" if nome.endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return FileResponse(str(caminho), media_type=tipo, filename=nome)


@app.get("/saude")
def saude():
    """Healthcheck simples (usado pelo compose e pelo monitoramento)."""
    db.consultar("SELECT 1 AS ok")
    return {"status": "ok"}
