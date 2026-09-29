#!/usr/bin/env python3
# INTRODUÇÃO
# Gerador dos dados fictícios da imobiliária "Serra Clara Imóveis" (nome escolhido
# após busca rápida não indicar imobiliária real conhecida com esse nome; o nome
# sugerido no prompt, "Lumina Imóveis", tem homônimos reais, então foi substituído).
#
# Onde se encaixa: é o serviço `gerador` do docker-compose (profile "carga").
# Ele popula o schema `staging` e publica em `curated` dentro de UMA transação
# (tudo ou nada), registrando a carga em `audit.cargas`. Rodar de novo recria os
# mesmos dados sem duplicar: a semente é fixa e a publicação usa TRUNCATE + INSERT.
#
# Por que assim: dados sintéticos com padrões plantados de propósito (sazonalidade,
# origens com conversões diferentes, bairro em alta/queda, corretor destaque,
# equipe abaixo da meta, motivos de perda com tendência, ciclos de venda/locação)
# dão ao agente de IA "o que descobrir" nas análises. Toda pessoa, CPF, telefone,
# e-mail e endereço é gerado e claramente fictício.
#
# RESUMO: gera ~6 mil leads, ~2,3 mil visitas, ~900 propostas, ~600 negócios
# fechados + ~300 perdidos, 500 imóveis, 20 corretores em 4 equipes, 3 cidades
# com 21 bairros, cobrindo 24 meses até o mês atual; grava em staging e publica
# em curated numa transação, com registro em audit.cargas.

from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta

import psycopg2
from faker import Faker

# ---------------------------------------------------------------------------
# Configuração geral
# ---------------------------------------------------------------------------

# Semente fixa: a mesma carga gera exatamente os mesmos dados (reprodutibilidade
# para testes e para a avaliação do agente).
SEMENTE = 20260901

MESES = 24           # janela de dados: 24 meses até o mês atual
QTD_LEADS = 6000
QTD_IMOVEIS = 500
QTD_CLIENTES = 1200

# Conexão vem do ambiente (docker-compose injeta PGHOST/PGDATABASE/PGUSER/...).
def conectar():
    """Abre conexão com o Postgres usando as variáveis de ambiente PG*."""
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        dbname=os.environ.get("PGDATABASE", "analista_dados"),
        user=os.environ.get("PGUSER", "app_gerador"),
        password=os.environ["PGPASSWORD"],
    )


# ---------------------------------------------------------------------------
# Dimensões fixas (nomes fictícios)
# ---------------------------------------------------------------------------

# Cidades fictícias (UFs reais, mas cidades/bairros inventados).
CIDADES = [
    ("Serra Clara", "MG", "Sul de Minas"),
    ("Vila Aurora", "SP", "Interior Paulista"),
    ("Porto das Palmeiras", "PR", "Litoral Paranaense"),
]

# Bairros por cidade (fictícios). "Jardim Horizonte" é o bairro EM ALTA e
# "Vila Operária" o bairro EM QUEDA nos últimos 6 meses (padrão plantado).
BAIRROS = {
    "Serra Clara": [
        "Jardim Horizonte", "Vila Operária", "Alto da Serra", "Bela Vista",
        "Parque das Acácias", "Centro Novo", "Recanto do Lago",
    ],
    "Vila Aurora": [
        "Jardim Aurora", "Vila Rica", "Parque Industrial", "Santa Tereza",
        "Bairro das Flores", "Loteamento Sol Nascente", "Centro",
    ],
    "Porto das Palmeiras": [
        "Beira Mar", "Ponta Verde", "Vila dos Pescadores", "Jardim Atlântico",
        "Centro Histórico", "Morro das Palmeiras", "Barra Nova",
    ],
}
BAIRRO_EM_ALTA = "Jardim Horizonte"
BAIRRO_EM_QUEDA = "Vila Operária"

EQUIPES = ["Equipe Alfa", "Equipe Beta", "Equipe Gama", "Equipe Delta"]
EQUIPE_FRACA = "Equipe Delta"  # plantado: fica abaixo da meta nos últimos 3 meses

# Origens com (peso na geração de leads, fator de conversão).
# Plantado: "Indicação" tem POUCOS leads e ALTA conversão; "Facebook Ads" tem
# MUITOS leads e BAIXA conversão.
ORIGENS = {
    "Facebook Ads":       {"peso": 0.30, "fator": 0.45},
    "Portal Imobiliário": {"peso": 0.18, "fator": 1.30},
    "Google Ads":         {"peso": 0.15, "fator": 0.90},
    "Site Próprio":       {"peso": 0.10, "fator": 1.00},
    "Instagram":          {"peso": 0.10, "fator": 0.80},
    "Plantão de Vendas":  {"peso": 0.07, "fator": 0.90},
    "Placa no Imóvel":    {"peso": 0.06, "fator": 1.20},
    "Indicação":          {"peso": 0.04, "fator": 3.00},
}

# Sazonalidade plantada: picos em março, agosto e dezembro; queda em janeiro.
SAZONALIDADE = {
    1: 0.60, 2: 0.90, 3: 1.40, 4: 1.00, 5: 1.00, 6: 0.95,
    7: 1.00, 8: 1.40, 9: 1.00, 10: 1.05, 11: 1.10, 12: 1.50,
}
# Média dos pesos: usada para normalizar o fator sazonal do mês de fechamento.
MEDIA_SAZONALIDADE = sum(SAZONALIDADE.values()) / 12

TIPOS_IMOVEL = ["apartamento", "casa", "sala_comercial", "terreno"]
PESOS_TIPO = [0.45, 0.35, 0.10, 0.10]

FAIXAS_VENDA = ["até 300k", "300k-600k", "600k-1M", "acima de 1M"]
FAIXAS_LOCACAO = ["até 2k", "2k-4k", "4k-8k", "acima de 8k"]

# Motivos de perda plantados: "Preço / financiamento negado" dominante;
# "Desistência após visita" crescente ao longo do tempo (peso sobe nos meses
# recentes — ver peso_motivo_perda).
MOTIVOS_PERDA = [
    "Preço / financiamento negado",
    "Desistência após visita",
    "Escolheu concorrente",
    "Documentação incompleta",
    "Imóvel saiu do mercado",
    "Mudança de planos do cliente",
]

MOTIVOS_DESCARTE = [
    "Sem perfil de crédito",
    "Fora da faixa de valor",
    "Região não atendida",
    "Contato inválido",
    "Apenas pesquisando",
]

PERC_COMISSAO_VENDA = 5.00      # 5% sobre o valor da venda
PERC_COMISSAO_LOCACAO = 8.33    # ~1 aluguel sobre o valor anual (12x)


# ---------------------------------------------------------------------------
# Utilidades de data
# ---------------------------------------------------------------------------

def intervalo_meses() -> list[tuple[int, int]]:
    """Lista de (ano, mes) dos últimos MESES meses, terminando no mês atual."""
    hoje = date.fromisoformat(os.environ.get("DATA_REFERENCIA", date.today().isoformat()))
    ano, mes = hoje.year, hoje.month
    meses = []
    for _ in range(MESES):
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    return list(reversed(meses))


def peso_mes(indice: int, ano: int, mes: int) -> float:
    """Peso de geração de um mês: sazonalidade x leve crescimento do negócio."""
    crescimento = 0.85 + 0.30 * (indice / (MESES - 1))  # ano inicial mais fraco
    return SAZONALIDADE[mes] * crescimento


def fator_tendencia_bairro(bairro: str, competencia: str, meses: list[str]) -> float:
    """Multiplicador de atratividade do bairro no mês (padrões plantados).

    O bairro em alta ganha peso progressivamente nos últimos 6 meses; o bairro
    em queda perde. Fora desses dois, o fator é 1 (neutro).
    """
    posicao = meses.index(competencia)
    ultimos_6 = posicao >= len(meses) - 6
    if bairro == BAIRRO_EM_ALTA and ultimos_6:
        intensidade = (posicao - (len(meses) - 6) + 1) / 6  # 1/6 .. 1
        return 1 + 3.0 * intensidade                        # até 4x
    if bairro == BAIRRO_EM_QUEDA and ultimos_6:
        intensidade = (posicao - (len(meses) - 6) + 1) / 6
        return 1 - 0.95 * intensidade                       # até 0.05x
    return 1.0


def peso_motivo_perda(motivo: str, competencia: str, meses: list[str]) -> float:
    """Peso do motivo de perda no mês.

    Plantado: "Desistência após visita" cresce ao longo do período (de 5% para
    ~25% relativos); "Preço / financiamento negado" permanece dominante.
    """
    posicao = meses.index(competencia)
    progresso = posicao / (len(meses) - 1)  # 0 no início, 1 no mês atual
    pesos = {
        "Preço / financiamento negado": 4.5,
        "Desistência após visita": 0.5 + 2.5 * progresso,   # crescente
        "Escolheu concorrente": 1.5,
        "Documentação incompleta": 1.0,
        "Imóvel saiu do mercado": 0.8,
        "Mudança de planos do cliente": 1.2,
    }
    return pesos[motivo]


# ---------------------------------------------------------------------------
# Geração das dimensões
# ---------------------------------------------------------------------------

def gerar_dimensoes(rng: random.Random, faker: Faker) -> dict:
    """Gera cidades, bairros, equipes, corretores, origens e campanhas."""
    cidades = [{"cidade_id": i + 1, "cidade": c, "uf": uf, "regiao": r}
               for i, (c, uf, r) in enumerate(CIDADES)]

    bairros = []
    bid = 1
    for cid in cidades:
        for nome in BAIRROS[cid["cidade"]]:
            bairros.append({"bairro_id": bid, "cidade_id": cid["cidade_id"],
                            "bairro": nome})
            bid += 1

    equipes = [{"equipe_id": i + 1, "nome_equipe": n}
               for i, n in enumerate(EQUIPES)]

    # 20 corretores (5 por equipe). O 1º da Equipe Alfa é o "corretor destaque"
    # (padrão plantado: converte bem mais que os demais).
    corretores = []
    nomes_usados = set()
    cid = 1
    for eq in equipes:
        for pos in range(5):
            nome = faker.name()
            while nome in nomes_usados:
                nome = faker.name()
            nomes_usados.add(nome)
            corretores.append({
                "corretor_id": cid,
                "nome_corretor": nome,
                "equipe_id": eq["equipe_id"],
                "data_admissao": date(2023, 1, 1) + timedelta(days=rng.randint(0, 900)),
                "ativo": True,
                "destaque": eq["nome_equipe"] == "Equipe Alfa" and pos == 0,
            })
            cid += 1

    origens = [{"origem_id": i + 1, "nome_origem": n}
               for i, n in enumerate(ORIGENS)]

    # Campanhas associadas às origens pagas (Facebook Ads, Google Ads, Instagram).
    meses = intervalo_meses()
    campanhas = []
    camp_id = 1
    for nome_origem in ("Facebook Ads", "Google Ads", "Instagram"):
        origem_id = next(o["origem_id"] for o in origens
                         if o["nome_origem"] == nome_origem)
        for k in range(3):
            inicio_idx = k * 8
            ano, mes = meses[inicio_idx]
            inicio = date(ano, mes, rng.randint(1, 10))
            fim_idx = inicio_idx + 5
            ano_f, mes_f = meses[min(fim_idx, len(meses) - 1)]
            fim = date(ano_f, mes_f, 28) if fim_idx < len(meses) else None
            campanhas.append({
                "campanha_id": camp_id,
                "nome_campanha": f"{nome_origem} - Campanha {k + 1}",
                "origem_id": origem_id,
                "data_inicio": inicio,
                "data_fim": fim,
                "investimento": round(rng.uniform(3000, 15000), 2),
            })
            camp_id += 1

    return {"cidades": cidades, "bairros": bairros, "equipes": equipes,
            "corretores": corretores, "origens": origens, "campanhas": campanhas}


def gerar_calendario() -> list[dict]:
    """Calendário diário cobrindo todo o período com folga (anos completos)."""
    meses_pt = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    meses = intervalo_meses()
    inicio = date(meses[0][0], 1, 1)
    fim = date(meses[-1][0], 12, 31)
    dias = []
    d = inicio
    while d <= fim:
        dias.append({
            "data": d, "ano": d.year, "mes": d.month,
            "nome_mes": meses_pt[d.month - 1],
            "trimestre": (d.month - 1) // 3 + 1,
            "competencia": f"{d.year:04d}-{d.month:02d}",
        })
        d += timedelta(days=1)
    return dias


def gerar_imoveis(rng: random.Random, bairros: list[dict],
                  meses: list[tuple[int, int]]) -> list[dict]:
    """Gera ~500 imóveis com valores realistas para o mercado brasileiro.

    Faixas de venda: apartamento 250 mil-1,2 mi; casa 350 mil-1,5 mi;
    sala comercial 200-800 mil; terreno 150-600 mil. ~10% acima de R$ 1 mi
    (ciclo de venda plantado como bem mais longo). Aluguel ~= 0,5% do valor/mês.
    """
    prefixo = {"apartamento": "AP", "casa": "CA", "sala_comercial": "SC",
               "terreno": "TE"}
    faixas_valor = {
        "apartamento": (250_000, 1_200_000),
        "casa": (350_000, 1_500_000),
        "sala_comercial": (200_000, 800_000),
        "terreno": (150_000, 600_000),
    }
    hoje = date.fromisoformat(os.environ.get("DATA_REFERENCIA", date.today().isoformat()))
    inicio = date(meses[0][0], meses[0][1], 1)

    imoveis = []
    for i in range(1, QTD_IMOVEIS + 1):
        tipo = rng.choices(TIPOS_IMOVEL, weights=PESOS_TIPO)[0]
        finalidade = "venda" if rng.random() < 0.78 else "locacao"
        bairro = rng.choice(bairros)
        lo, hi = faixas_valor[tipo]
        valor_venda = round(rng.uniform(lo, hi), -3) if finalidade == "venda" else None
        # ~10% dos imóveis de venda acima de R$ 1 milhão (ciclo longo plantado)
        if valor_venda and rng.random() < 0.10:
            valor_venda = round(rng.uniform(1_000_000, 1_800_000), -3)
        valor_base = valor_venda or rng.uniform(lo, hi)
        valor_aluguel = (round(valor_base * 0.005, -1)
                         if finalidade == "locacao" else None)
        captacao = inicio + timedelta(days=rng.randint(0, (hoje - inicio).days))
        imoveis.append({
            "imovel_id": i,
            "codigo": f"{prefixo[tipo]}{i:04d}",
            "tipo": tipo,
            "finalidade": finalidade,
            "bairro_id": bairro["bairro_id"],
            "area_m2": round(rng.uniform(30, 350), 2) if tipo != "terreno"
                       else round(rng.uniform(200, 1000), 2),
            "quartos": rng.randint(1, 4) if tipo in ("apartamento", "casa") else 0,
            "valor_venda": valor_venda,
            "valor_aluguel": valor_aluguel,
            "data_captacao": captacao,
            "status": "disponivel",  # ajustado ao final, conforme os negócios
        })
    return imoveis


def gerar_clientes(faker: Faker, rng: random.Random) -> list[dict]:
    """Gera clientes 100% fictícios.

    CPFs usam marcador FICTICIO de propósito (não são números de documentos
    reais) e e-mails usam o domínio reservado exemplo.com. Essas colunas existem
    para demonstrar as travas de segurança do agente (que não pode lê-las).
    """
    clientes = []
    for i in range(1, QTD_CLIENTES + 1):
        cpf = f"FICTICIO-{i:06d}"
        clientes.append({
            "cliente_id": i,
            "nome": faker.name(),
            "cpf": cpf,
            "telefone": f"(00) 9{rng.randint(6000, 9999)}-{rng.randint(1000, 9999)}",
            "email": f"cliente{i:04d}@example.invalid",
        })
    return clientes


# ---------------------------------------------------------------------------
# Geração do funil comercial (leads -> visitas -> propostas -> negócios)
# ---------------------------------------------------------------------------

def ciclo_fechamento_dias(rng: random.Random, finalidade: str,
                          valor_negocio: float) -> int:
    """Tempo entre abertura e fechamento do negócio.

    Plantado: locação fecha bem mais rápido que venda; imóveis acima de
    R$ 1 milhão têm ciclo muito mais longo.
    """
    if finalidade == "locacao":
        return max(2, int(rng.triangular(3, 30, 10)))
    if valor_negocio > 1_000_000:
        return max(60, int(rng.triangular(90, 300, 160)))
    return max(15, int(rng.triangular(20, 150, 60)))


def gerar_funil(rng: random.Random, dims: dict, imoveis: list[dict],
                clientes: list[dict]) -> dict:
    """Gera leads, visitas, propostas e negócios com coerência de datas.

    Regras de coerência obrigatórias:
      * datas em ordem: lead <= visita <= proposta <= fechamento do negócio;
      * um imóvel de VENDA só fecha uma vez; um imóvel de LOCAÇÃO só fecha de
        novo 30+ dias após o fechamento anterior;
      * comissão sempre calculada sobre o valor do negócio;
      * negócio que fecharia no futuro vira proposta "em_analise".
    """
    meses = intervalo_meses()
    competencias = [f"{a:04d}-{m:02d}" for a, m in meses]
    hoje = date.fromisoformat(os.environ.get("DATA_REFERENCIA", date.today().isoformat()))

    bairro_por_id = {b["bairro_id"]: b for b in dims["bairros"]}
    origem_id_por_nome = {o["nome_origem"]: o["origem_id"] for o in dims["origens"]}
    campanhas_por_origem: dict[int, list[dict]] = {}
    for c in dims["campanhas"]:
        campanhas_por_origem.setdefault(c["origem_id"], []).append(c)

    # Índice de imóveis por (cidade, finalidade) para escolha coerente.
    imoveis_por_chave: dict[tuple[int, str], list[dict]] = {}
    for im in imoveis:
        cidade_id = bairro_por_id[im["bairro_id"]]["cidade_id"]
        imoveis_por_chave.setdefault((cidade_id, im["finalidade"]), []).append(im)

    # Pesos de mês para sorteio da data do lead.
    pesos_mes = [peso_mes(i, a, m) for i, (a, m) in enumerate(meses)]

    # Probabilidades-base de avanço no funil (calibradas para ~2,6 mil visitas,
    # ~900 propostas e ~600 fechados a partir de 6 mil leads).
    p_visita_base = 0.55
    p_proposta_base = 0.44
    p_fechado_base = 0.85

    leads, visitas, propostas, negocios = [], [], [], []
    ultimo_fechamento: dict[int, date] = {}  # imovel_id -> data (controle de status)

    vid = pid = nid = 1
    for lead_id in range(1, QTD_LEADS + 1):
        # --- lead ---
        idx_mes = rng.choices(range(len(meses)), weights=pesos_mes)[0]
        ano, mes = meses[idx_mes]
        ultimo_dia = 28 if mes == 2 else 30 if mes in (4, 6, 9, 11) else 31
        data_lead = date(ano, mes, rng.randint(1, ultimo_dia))
        if data_lead > hoje:
            data_lead = hoje - timedelta(days=rng.randint(0, 5))
        competencia = f"{data_lead.year:04d}-{data_lead.month:02d}"

        nome_origem = rng.choices(list(ORIGENS),
                                  weights=[o["peso"] for o in ORIGENS.values()])[0]
        fator_origem = ORIGENS[nome_origem]["fator"]
        origem_id = origem_id_por_nome[nome_origem]

        campanha_id = None
        for camp in campanhas_por_origem.get(origem_id, []):
            if camp["data_inicio"] <= data_lead and (camp["data_fim"] is None
                                                     or data_lead <= camp["data_fim"]):
                campanha_id = camp["campanha_id"]
                break

        finalidade = "venda" if rng.random() < 0.55 else "locacao"
        tipo_procurado = rng.choices(TIPOS_IMOVEL, weights=PESOS_TIPO)[0]
        faixa = rng.choice(FAIXAS_VENDA if finalidade == "venda" else FAIXAS_LOCACAO)
        cidade_id = rng.choices([c["cidade_id"] for c in dims["cidades"]],
                                weights=[0.50, 0.30, 0.20])[0]
        # O corretor destaque recebe mais leads (2x) — padrão plantado.
        corretor = rng.choices(
            dims["corretores"],
            weights=[2.0 if c["destaque"] else 1.0 for c in dims["corretores"]])[0]
        cliente = rng.choice(clientes)

        # ~25% dos leads são descartados sem avançar (motivo registrado).
        descartado = rng.random() < 0.25
        motivo_descarte = rng.choice(MOTIVOS_DESCARTE) if descartado else None

        leads.append({
            "lead_id": lead_id, "data": data_lead, "origem_id": origem_id,
            "campanha_id": campanha_id, "finalidade": finalidade,
            "tipo_procurado": tipo_procurado, "faixa_valor": faixa,
            "cidade_id": cidade_id, "corretor_id": corretor["corretor_id"],
            "cliente_id": cliente["cliente_id"],
            "qualificado": not descartado, "descartado": descartado,
            "motivo_descarte": motivo_descarte,
        })
        if descartado:
            continue

        # --- visita(s) ---
        p_visita = min(0.95, p_visita_base * (fator_origem ** 0.5))
        if rng.random() >= p_visita:
            continue

        pool = imoveis_por_chave.get((cidade_id, finalidade), [])
        if not pool:
            continue

        def escolher_imovel(comp: str) -> dict:
            """Escolhe imóvel do pool com peso da tendência do bairro no mês."""
            pesos = [fator_tendencia_bairro(
                bairro_por_id[im["bairro_id"]]["bairro"], comp, competencias)
                for im in pool]
            return rng.choices(pool, weights=pesos)[0]

        imovel = escolher_imovel(competencia)
        n_visitas = 1 if rng.random() < 0.85 else 2
        compareceu_alguma = False
        data_ultima_visita = data_lead
        for v in range(n_visitas):
            data_visita = min(data_lead + timedelta(days=rng.randint(1, 10 + v * 7)),
                              hoje)
            compareceu = rng.random() < 0.88
            compareceu_alguma = compareceu_alguma or compareceu
            data_ultima_visita = max(data_ultima_visita, data_visita)
            visitas.append({
                "visita_id": vid, "lead_id": lead_id,
                "imovel_id": imovel["imovel_id"],
                "corretor_id": corretor["corretor_id"],
                "data": data_visita, "compareceu": compareceu,
            })
            vid += 1
        if not compareceu_alguma:
            continue  # cliente não compareceu: funil morre aqui

        # --- proposta ---
        if rng.random() >= p_proposta_base:
            continue
        data_proposta = min(data_ultima_visita + timedelta(days=rng.randint(1, 15)),
                            hoje)
        comp_proposta = f"{data_proposta.year:04d}-{data_proposta.month:02d}"

        # Valor proposto: leve desconto sobre o anúncio.
        if finalidade == "venda":
            valor_ref = imovel["valor_venda"] or rng.uniform(300_000, 900_000)
        else:
            valor_ref = (imovel["valor_aluguel"] or 2500) * 12  # contrato anual
        valor_proposto = round(valor_ref * rng.uniform(0.90, 1.00), 2)

        # Fecha ou não? Fator da origem, corretor destaque, equipe fraca e
        # SAZONALIDADE DO MÊS DE FECHAMENTO (a sazonalidade plantada aparece nos
        # negócios fechados: picos em mar/ago/dez, queda em jan).
        fator_corretor = 2.0 if corretor["destaque"] else 1.0
        if dims["equipes"][corretor["equipe_id"] - 1]["nome_equipe"] == EQUIPE_FRACA:
            fator_corretor *= 0.75

        # --- negócio ---
        data_fechamento = data_proposta + timedelta(
            days=ciclo_fechamento_dias(rng, finalidade, valor_proposto))
        saz = SAZONALIDADE[data_fechamento.month] / MEDIA_SAZONALIDADE
        p_fechado = min(0.95, p_fechado_base * (fator_origem ** 0.5)
                        * fator_corretor * saz)
        fechou = rng.random() < p_fechado

        if fechou:
            # Fechamento não pode cair no futuro nem violar a disponibilidade do
            # imóvel (venda fecha uma única vez; locação só refecha 30+ dias após
            # o fechamento anterior). Antes de desistir do fechamento, tenta
            # trocar por outro imóvel do mesmo pool (recalculando valor e ciclo).
            for _ in range(8):
                if data_fechamento > hoje:
                    fechou = None  # futuro: proposta fica em análise
                    break
                ultima = ultimo_fechamento.get(imovel["imovel_id"])
                disponivel = ultima is None or (
                    finalidade == "locacao"
                    and data_fechamento > ultima + timedelta(days=30))
                if disponivel:
                    break
                imovel = escolher_imovel(comp_proposta)
                if finalidade == "venda":
                    valor_ref = imovel["valor_venda"] or rng.uniform(300_000, 900_000)
                else:
                    valor_ref = (imovel["valor_aluguel"] or 2500) * 12
                valor_proposto = round(valor_ref * rng.uniform(0.90, 1.00), 2)
                data_fechamento = data_proposta + timedelta(
                    days=ciclo_fechamento_dias(rng, finalidade, valor_proposto))
            else:
                fechou = None  # estoque da praça esgotado: fica em análise

        if fechou is True:
            status_proposta = "aceita"
            valor_negocio = valor_proposto
            perc = (PERC_COMISSAO_VENDA if finalidade == "venda"
                    else PERC_COMISSAO_LOCACAO)
            negocios.append({
                "negocio_id": nid, "lead_id": lead_id,
                "imovel_id": imovel["imovel_id"],
                "corretor_id": corretor["corretor_id"],
                "finalidade": finalidade, "data_abertura": data_proposta,
                "data_fechamento": data_fechamento, "status": "fechado",
                "valor_negocio": valor_negocio, "perc_comissao": perc,
                "valor_comissao": round(valor_negocio * perc / 100, 2),
                "motivo_perda": None,
            })
            nid += 1
            ultimo_fechamento[imovel["imovel_id"]] = data_fechamento
        elif fechou is False:
            status_proposta = "recusada"
            comp_fech = f"{data_fechamento.year:04d}-{data_fechamento.month:02d}"
            if data_fechamento > hoje:
                data_fechamento = hoje
                comp_fech = f"{hoje.year:04d}-{hoje.month:02d}"
            motivo = rng.choices(
                MOTIVOS_PERDA,
                weights=[peso_motivo_perda(m, comp_fech, competencias)
                         for m in MOTIVOS_PERDA])[0]
            negocios.append({
                "negocio_id": nid, "lead_id": lead_id,
                "imovel_id": imovel["imovel_id"],
                "corretor_id": corretor["corretor_id"],
                "finalidade": finalidade, "data_abertura": data_proposta,
                "data_fechamento": data_fechamento, "status": "perdido",
                "valor_negocio": valor_proposto, "perc_comissao": 0,
                "valor_comissao": 0, "motivo_perda": motivo,
            })
            nid += 1
        else:
            # Proposta recente ainda sem desfecho.
            status_proposta = ("em_analise"
                               if (hoje - data_proposta).days <= 45 else "recusada")

        propostas.append({
            "proposta_id": pid, "lead_id": lead_id, "imovel_id": imovel["imovel_id"],
            "data": data_proposta, "valor_proposto": valor_proposto,
            "status": status_proposta,
        })
        pid += 1

    # --- status final dos imóveis (coerência com os negócios fechados) ---
    proposta_em_analise = {p["imovel_id"] for p in propostas
                           if p["status"] == "em_analise"}
    for im in imoveis:
        fech = ultimo_fechamento.get(im["imovel_id"])
        if fech is not None:
            im["status"] = "vendido" if im["finalidade"] == "venda" else "alugado"
        elif im["imovel_id"] in proposta_em_analise:
            im["status"] = "reservado"
        else:
            im["status"] = "disponivel"

    return {"leads": leads, "visitas": visitas, "propostas": propostas,
            "negocios": negocios}


def gerar_metas(rng: random.Random, dims: dict, negocios: list[dict]) -> list[dict]:
    """Gera metas mensais por equipe.

    Regra: meta ≈ média realizada da equipe + pequeno desafio. Padrão plantado:
    a Equipe Delta fica ABAIXO da meta nos últimos 3 meses (meta inflada em 30%
    sobre o realizado desse período).
    """
    meses = intervalo_meses()
    competencias = [f"{a:04d}-{m:02d}" for a, m in meses]
    equipe_por_corretor = {c["corretor_id"]: c["equipe_id"]
                           for c in dims["corretores"]}

    # Realizado por equipe e competência.
    realizado: dict[tuple[int, str], dict] = {}
    for n in negocios:
        if n["status"] != "fechado":
            continue
        comp = f"{n['data_fechamento'].year:04d}-{n['data_fechamento'].month:02d}"
        eq = equipe_por_corretor[n["corretor_id"]]
        slot = realizado.setdefault((eq, comp), {"negocios": 0, "vgv": 0.0})
        slot["negocios"] += 1
        if n["finalidade"] == "venda":
            slot["vgv"] += float(n["valor_negocio"])

    equipe_fraca_id = next(e["equipe_id"] for e in dims["equipes"]
                           if e["nome_equipe"] == EQUIPE_FRACA)
    ultimas_3 = competencias[-3:]

    metas = []
    meta_id = 1
    for equipe in dims["equipes"]:
        eq_id = equipe["equipe_id"]
        medias_n = [realizado.get((eq_id, c), {"negocios": 0})["negocios"]
                    for c in competencias]
        medias_v = [realizado.get((eq_id, c), {"vgv": 0.0})["vgv"]
                    for c in competencias]
        media_neg = max(1, round(sum(medias_n) / len(medias_n)))
        media_vgv = max(100_000, sum(medias_v) / len(medias_v))
        for comp in competencias:
            if eq_id == equipe_fraca_id and comp in ultimas_3:
                # Planta "equipe abaixo da meta há 3 meses".
                real = realizado.get((eq_id, comp), {"negocios": 0, "vgv": 0.0})
                meta_neg = max(real["negocios"] + 1, round(real["negocios"] * 1.3))
                meta_vgv = max(real["vgv"] * 1.3, 100_000)
            else:
                meta_neg = media_neg + rng.randint(0, 1)
                meta_vgv = round(media_vgv * rng.uniform(1.0, 1.15), -3)
            metas.append({
                "meta_id": meta_id, "competencia": comp, "equipe_id": eq_id,
                "corretor_id": None, "meta_negocios": meta_neg,
                "meta_vgv": round(meta_vgv, 2),
            })
            meta_id += 1
    return metas


# ---------------------------------------------------------------------------
# Carga: staging -> curated (transação única)
# ---------------------------------------------------------------------------

DDL_STAGING = """
DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA staging;
CREATE TABLE staging.dim_cidade (cidade_id SMALLINT, cidade TEXT, uf CHAR(2), regiao TEXT);
CREATE TABLE staging.dim_bairro (bairro_id SMALLINT, cidade_id SMALLINT, bairro TEXT);
CREATE TABLE staging.dim_equipe (equipe_id SMALLINT, nome_equipe TEXT);
CREATE TABLE staging.dim_corretor (corretor_id SMALLINT, nome_corretor TEXT, equipe_id SMALLINT, data_admissao DATE, ativo BOOLEAN);
CREATE TABLE staging.dim_origem (origem_id SMALLINT, nome_origem TEXT);
CREATE TABLE staging.dim_campanha (campanha_id SMALLINT, nome_campanha TEXT, origem_id SMALLINT, data_inicio DATE, data_fim DATE, investimento NUMERIC(12,2));
CREATE TABLE staging.dim_calendario (data DATE, ano SMALLINT, mes SMALLINT, nome_mes TEXT, trimestre SMALLINT, competencia CHAR(7));
CREATE TABLE staging.imoveis (imovel_id INTEGER, codigo TEXT, tipo TEXT, finalidade TEXT, bairro_id SMALLINT, area_m2 NUMERIC(8,2), quartos SMALLINT, valor_venda NUMERIC(14,2), valor_aluguel NUMERIC(12,2), data_captacao DATE, status TEXT);
CREATE TABLE staging.clientes (cliente_id INTEGER, nome TEXT, cpf TEXT, telefone TEXT, email TEXT);
CREATE TABLE staging.fato_leads (lead_id INTEGER, data DATE, origem_id SMALLINT, campanha_id SMALLINT, finalidade TEXT, tipo_procurado TEXT, faixa_valor TEXT, cidade_id SMALLINT, corretor_id SMALLINT, cliente_id INTEGER, qualificado BOOLEAN, descartado BOOLEAN, motivo_descarte TEXT);
CREATE TABLE staging.fato_visitas (visita_id INTEGER, lead_id INTEGER, imovel_id INTEGER, corretor_id SMALLINT, data DATE, compareceu BOOLEAN);
CREATE TABLE staging.fato_propostas (proposta_id INTEGER, lead_id INTEGER, imovel_id INTEGER, data DATE, valor_proposto NUMERIC(14,2), status TEXT);
CREATE TABLE staging.fato_negocios (negocio_id INTEGER, lead_id INTEGER, imovel_id INTEGER, corretor_id SMALLINT, finalidade TEXT, data_abertura DATE, data_fechamento DATE, status TEXT, valor_negocio NUMERIC(14,2), perc_comissao NUMERIC(5,2), valor_comissao NUMERIC(14,2), motivo_perda TEXT);
CREATE TABLE staging.metas_mensais (meta_id INTEGER, competencia CHAR(7), equipe_id SMALLINT, corretor_id SMALLINT, meta_negocios SMALLINT, meta_vgv NUMERIC(14,2));
"""

# Ordem de publicação respeita as FKs de curated.
TABELAS = [
    "dim_cidade", "dim_bairro", "dim_equipe", "dim_corretor", "dim_origem",
    "dim_campanha", "dim_calendario", "imoveis", "clientes", "fato_leads",
    "fato_visitas", "fato_propostas", "fato_negocios", "metas_mensais",
]

TABELAS_COM_SERIAL = {
    "dim_cidade": "cidade_id", "dim_bairro": "bairro_id",
    "dim_equipe": "equipe_id", "dim_corretor": "corretor_id",
    "dim_origem": "origem_id", "dim_campanha": "campanha_id",
    "imoveis": "imovel_id", "clientes": "cliente_id",
    "fato_leads": "lead_id", "fato_visitas": "visita_id",
    "fato_propostas": "proposta_id", "fato_negocios": "negocio_id",
    "metas_mensais": "meta_id",
}


def inserir_lote(cur, tabela: str, linhas: list[dict]) -> None:
    """Insere uma lista de dicts na tabela staging com execute_values em lotes."""
    if not linhas:
        return
    from psycopg2.extras import execute_values
    colunas = [c for c in linhas[0].keys()]
    valores = [[linha.get(c) for c in colunas] for linha in linhas]
    sql = (f"INSERT INTO staging.{tabela} ({', '.join(colunas)}) VALUES %s")
    execute_values(cur, sql, valores, page_size=2000)


def publicar(conn, dados: dict) -> None:
    """Publica staging em curated numa única transação e registra a carga.

    TRUNCATE ... CASCADE + INSERT SELECT garantem idempotência: rodar de novo
    recria exatamente os mesmos dados, sem duplicar. As sequences são realinhadas
    com os ids explícitos gerados.
    """
    with conn.cursor() as cur:
        # psycopg2 já abre a transação na primeira operação: staging + truncate +
        # insert + auditoria vão todos na mesma transação (tudo ou nada).
        for tabela in TABELAS:
            inserir_lote(cur, tabela, dados[tabela])

        for tabela in TABELAS:
            cur.execute(f"TRUNCATE curated.{tabela} CASCADE")
        for tabela in TABELAS:
            cur.execute(
                f"INSERT INTO curated.{tabela} SELECT * FROM staging.{tabela}")
        # Realinha as sequences dos SERIALs com os ids publicados.
        for tabela, coluna in TABELAS_COM_SERIAL.items():
            cur.execute(
                "SELECT setval(pg_get_serial_sequence(%s, %s), "
                f"(SELECT MAX({coluna}) FROM curated.{tabela}))",
                (f"curated.{tabela}", coluna))
        cur.execute(
            """INSERT INTO audit.cargas
               (semente, qtd_leads, qtd_visitas, qtd_propostas, qtd_negocios,
                qtd_imoveis, observacao)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (SEMENTE, len(dados["fato_leads"]), len(dados["fato_visitas"]),
             len(dados["fato_propostas"]), len(dados["fato_negocios"]),
             len(dados["imoveis"]),
             "Carga fictícia reprodutível (staging -> curated em transação)"))
    conn.commit()


def main() -> None:
    """Ponto de entrada: gera todos os dados e publica no banco."""
    if "--se-vazio" in sys.argv:
        conn = conectar()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT EXISTS (SELECT 1 FROM curated.fato_leads)")
                if cur.fetchone()[0]:
                    print("[gerador] Base já carregada; dados preservados.")
                    return
        finally:
            conn.close()
    rng = random.Random(SEMENTE)
    faker = Faker("pt_BR")
    faker.seed_instance(SEMENTE)

    print("[gerador] Gerando dimensões...")
    dims = gerar_dimensoes(rng, faker)
    calendario = gerar_calendario()
    meses = intervalo_meses()
    imoveis = gerar_imoveis(rng, dims["bairros"], meses)
    clientes = gerar_clientes(faker, rng)

    print("[gerador] Gerando funil comercial...")
    funil = gerar_funil(rng, dims, imoveis, clientes)
    metas = gerar_metas(rng, dims, funil["negocios"])

    dados = {
        "dim_cidade": dims["cidades"], "dim_bairro": dims["bairros"],
        "dim_equipe": dims["equipes"], "dim_corretor": [
            {k: v for k, v in c.items() if k != "destaque"}
            for c in dims["corretores"]],
        "dim_origem": dims["origens"], "dim_campanha": dims["campanhas"],
        "dim_calendario": calendario, "imoveis": imoveis, "clientes": clientes,
        "fato_leads": funil["leads"], "fato_visitas": funil["visitas"],
        "fato_propostas": funil["propostas"], "fato_negocios": funil["negocios"],
        "metas_mensais": metas,
    }

    fechados = [n for n in funil["negocios"] if n["status"] == "fechado"]
    vendas = [n for n in fechados if n["finalidade"] == "venda"]
    locacoes = [n for n in fechados if n["finalidade"] == "locacao"]
    print(f"[gerador] Volumes: {len(dados['fato_leads'])} leads, "
          f"{len(dados['fato_visitas'])} visitas, {len(dados['fato_propostas'])} "
          f"propostas, {len(vendas)} vendas + {len(locacoes)} locações fechadas, "
          f"{len(funil['negocios']) - len(fechados)} negócios perdidos.")

    print("[gerador] Publicando no banco (staging -> curated)...")
    conn = conectar()
    try:
        with conn:  # staging é área de trabalho: recriada a cada carga
            with conn.cursor() as cur:
                cur.execute(DDL_STAGING)
        publicar(conn, dados)
    finally:
        conn.close()
    print("[gerador] Carga concluída e registrada em audit.cargas.")


if __name__ == "__main__":
    main()
