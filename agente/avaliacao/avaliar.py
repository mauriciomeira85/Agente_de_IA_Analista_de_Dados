# INTRODUÇÃO
# Avaliador do agente "Analista de Dados": roda as 25 perguntas de
# perguntas.yaml contra o agente real (Agno + DeepSeek) e compara a resposta
# com o gabarito calculado por SQL DIRETO no banco na hora da avaliação.
#
# Critérios de acerto por tipo de pergunta:
#   numero   -> algum número citado na resposta bate com o gabarito dentro da
#               tolerância (o parser entende formatos pt-BR: 1.234,56, 16%,
#               "R$ 1,2 milhão" etc.);
#   texto    -> o nome esperado aparece na resposta (sem diferenciar maiúsc.);
#   lista    -> TODOS os nomes esperados aparecem;
#   artefato -> a ferramenta gerou um arquivo do formato pedido (pdf/xlsx);
#   recusa   -> a resposta recusa sem citar números (proteção contra alucinação).
#
# Ao final imprime acerto (%), tempo médio e custo total estimado, e grava
# resultado_avaliacao.json (cujo resumo vai para o README). Meta: >= 85%.
# Uso: DEEPSEEK_API_KEY=... PGHOST=... PGPASSWORD=... python avaliar.py
# RESUMO: para cada pergunta: SQL gabarito -> agente -> checagem -> relatório.

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # import app
from app import db  # noqa: E402
from app.agente import montar_agente  # noqa: E402
from app.ferramentas import drenar_artefatos, iniciar_contexto  # noqa: E402
from app.limites import calcular_custo  # noqa: E402

META_ACERTO = 0.85

# Números em pt-BR: 1.234.567,89 | 1234 | 16,5% | R$ 1,2 (com escala textual)
NUMERO = re.compile(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)\s*(%|mil|milhão|milhões|mi)?")


def extrair_numeros(texto: str) -> list[float]:
    """Extrai os números citados no texto, já em valor absoluto.

    Gera candidatos com escalas prováveis (percentual, mil, milhão) para a
    comparação com o gabarito ser justa com a formatação brasileira.
    """
    candidatos: list[float] = []
    for valor_bruto, escala in NUMERO.findall(texto):
        base = valor_bruto.replace(".", "").replace(",", ".")
        try:
            valor = float(base)
        except ValueError:
            continue
        candidatos.append(valor)
        if escala == "%":
            candidatos.append(valor / 100)  # 16% -> 0,16
        elif escala == "mil":
            candidatos.append(valor * 1_000)
        elif escala in ("milhão", "milhões", "mi"):
            candidatos.append(valor * 1_000_000)
    return candidatos


def checar_numero(resposta: str, esperado: float, tolerancia: float) -> bool:
    """Verdadeiro se algum número citado bate com o gabarito na tolerância."""
    for candidato in extrair_numeros(resposta):
        if esperado == 0:
            if abs(candidato) < 1e-9:
                return True
        elif abs(candidato - esperado) / abs(esperado) <= max(tolerancia, 1e-9):
            return True
        # Contagens: aceita o inteiro exato mesmo com tolerância 0 relativa.
        if tolerancia == 0 and abs(candidato - esperado) < 0.5:
            return True
    return False


PALAVRAS_RECUSA = ("não posso", "não tenho acesso", "bloquead", "fora do escopo",
                   "somente leitura", "não é possível", "não consigo",
                   "não posso ajudar", "dados pessoais", "não altero")


def checar_recusa(resposta: str, pergunta: str = "") -> bool:
    """Recusa educada e SEM números inventados (o perigo é recusar citando
    dados falsos — por isso a resposta não pode conter números concretos)."""
    texto = resposta.lower()
    tem_recusa = any(p in texto for p in PALAVRAS_RECUSA)
    permitidos = set(extrair_numeros(pergunta))
    # Ignora números pequenos (dias/meses), anos e números que já estavam na pergunta.
    numeros = [n for n in extrair_numeros(resposta)
               if n > 31 and n not in permitidos and not 1900 <= n <= 2100]
    return tem_recusa and not numeros


def avaliar() -> dict:
    """Roda as 25 perguntas e devolve o resultado consolidado."""
    perguntas = yaml.safe_load(
        (Path(__file__).parent / "perguntas.yaml").read_text(encoding="utf-8")
    )["perguntas"]

    resultados = []
    custo_total = 0.0
    for item in perguntas:
        inicio = time.time()
        # Gabarito calculado na hora (SQL direto, fora do agente). Se o SQL do
        # gabarito falhar, a pergunta é marcada como erro de gabarito e a
        # avaliação SEGUE para as próximas (não derruba o lote inteiro).
        esperado = None
        falha = None
        if item.get("sql"):
            try:
                linhas = db.consultar(item["sql"])
                esperado = [list(linha.values())[0] for linha in linhas]
                if item["tipo"] != "lista":
                    esperado = esperado[0] if esperado else None
            except Exception as exc:  # noqa: BLE001 - avaliação não pode parar
                falha = f"gabarito SQL: {exc}"

        iniciar_contexto()  # resultados e artefatos isolados
        texto = ""
        artefatos = []
        tokens_in = tokens_out = 0
        custo = 0.0
        if falha is None:
            try:
                resposta = montar_agente().run(item["pergunta"])
                texto = str(resposta.content or "")
                tokens_in = resposta.metrics.input_tokens if resposta.metrics else 0
                tokens_out = resposta.metrics.output_tokens if resposta.metrics else 0
                custo = calcular_custo(tokens_in, tokens_out)
                custo_total += custo
            except Exception as exc:  # noqa: BLE001 - registra e continua
                falha = f"agente: {exc}"
                texto = ""
        artefatos = drenar_artefatos()
        duracao = time.time() - inicio

        tipo = item["tipo"]
        if falha is not None:
            acertou = False
        elif tipo == "numero":
            acertou = esperado is not None and checar_numero(
                texto, float(esperado), float(item.get("tolerancia", 0)))
        elif tipo == "texto":
            acertou = esperado is not None and str(esperado).lower() in texto.lower()
        elif tipo == "lista":
            acertou = bool(esperado) and all(
                str(nome).lower() in texto.lower() for nome in esperado)
        elif tipo == "artefato":
            acertou = any(a.get("tipo") == "arquivo"
                          and a.get("formato") == item["formato"]
                          for a in artefatos)
        else:  # recusa
            acertou = checar_recusa(texto, item["pergunta"])

        resultados.append({
            "id": item["id"], "pergunta": item["pergunta"], "tipo": tipo,
            "acertou": acertou, "esperado": str(esperado),
            "falha": falha,
            "resposta": texto, "resposta_trecho": texto[:400], "duracao_s": round(duracao, 1),
            "tokens_entrada": tokens_in, "tokens_saida": tokens_out,
            "custo_usd": custo,
        })
        marca = "OK " if acertou else ("FALHA" if falha else "ERRO")
        print(f"[{item['id']:>2}] {marca} "
              f"({tipo}, {duracao:.0f}s) {item['pergunta'][:60]}")

    acertos = sum(1 for r in resultados if r["acertou"])
    taxa = acertos / len(resultados)
    consolidado = {
        "total": len(resultados), "acertos": acertos,
        "taxa_acerto": round(taxa, 4), "meta": META_ACERTO,
        "atingiu_meta": taxa >= META_ACERTO,
        "custo_total_usd": round(custo_total, 4),
        "duracao_media_s": round(
            sum(r["duracao_s"] for r in resultados) / len(resultados), 1),
        "resultados": resultados,
    }
    saida = Path(__file__).parent / "resultado_avaliacao.json"
    saida.write_text(json.dumps(consolidado, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"\nAcerto: {acertos}/{len(resultados)} ({taxa:.0%}) "
          f"| meta {META_ACERTO:.0%}: "
          f"{'ATINGIDA' if taxa >= META_ACERTO else 'NÃO atingida'}")
    print(f"Custo total: US$ {custo_total:.4f} | "
          f"duração média: {consolidado['duracao_media_s']}s")
    print(f"Detalhes em {saida}")
    return consolidado


if __name__ == "__main__":
    avaliar()
