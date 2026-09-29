// INTRODUÇÃO
// Leitura, validação e sanitização dos filtros de query string compartilhados
// por todos os endpoints de /api/dashboard. Regras:
//   * de / ate: datas ISO (AAAA-MM-DD); padrão = últimos 12 meses;
//   * ids (cidade_id, origem_id, equipe_id, corretor_id): inteiros positivos;
//   * finalidade: 'venda' | 'locacao'; tipo: apartamento | casa |
//     sala_comercial | terreno (domínios do CHECK das tabelas curated);
//   * pagina / por_pagina: inteiros com limites (proteção contra abuso).
// Também monta o WHERE dinâmico SEMPRE parametrizado: os nomes de coluna vêm de
// uma lista fechada por view (nunca da requisição) e os valores entram como $n.
// RESUMO: parseFiltros() devolve os filtros válidos; montarWhere() gera SQL
// parametrizado seguro para uma view específica; periodoAnterior() calcula o
// intervalo de comparação das variações percentuais dos cartões.

export interface Filtros {
  de: string; // AAAA-MM-DD
  ate: string; // AAAA-MM-DD
  competenciaDe: string; // AAAA-MM (grão das views)
  competenciaAte: string; // AAAA-MM
  cidadeId?: number;
  finalidade?: string;
  tipo?: string;
  origemId?: number;
  equipeId?: number;
  corretorId?: number;
}

const FINALIDADES = new Set(["venda", "locacao"]);
const TIPOS = new Set(["apartamento", "casa", "sala_comercial", "terreno"]);
const DATA_ISO = /^\d{4}-\d{2}-\d{2}$/;

function dataValida(valor: string): boolean {
  if (!DATA_ISO.test(valor)) return false;
  const d = new Date(`${valor}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === valor;
}

function inteiroPositivo(valor: string | null): number | undefined {
  if (valor === null || valor === "") return undefined;
  if (!/^\d+$/.test(valor)) return undefined;
  const n = Number(valor);
  return n > 0 && Number.isSafeInteger(n) ? n : undefined;
}

function competencia(dataISO: string): string {
  return dataISO.slice(0, 7);
}

export function parseFiltros(params: URLSearchParams): Filtros {
  const hoje = new Date();
  const padraoAte = hoje.toISOString().slice(0, 10);
  const inicioPadrao = new Date(
    Date.UTC(hoje.getUTCFullYear(), hoje.getUTCMonth() - 11, 1),
  );
  const padraoDe = inicioPadrao.toISOString().slice(0, 10);

  let de = params.get("de") ?? padraoDe;
  let ate = params.get("ate") ?? padraoAte;
  if (!dataValida(de)) de = padraoDe;
  if (!dataValida(ate)) ate = padraoAte;
  if (de > ate) [de, ate] = [ate, de];

  const finalidadeBruta = params.get("finalidade") ?? undefined;
  const tipoBruto = params.get("tipo") ?? undefined;

  return {
    de,
    ate,
    competenciaDe: competencia(de),
    competenciaAte: competencia(ate),
    cidadeId: inteiroPositivo(params.get("cidade_id")),
    finalidade:
      finalidadeBruta && FINALIDADES.has(finalidadeBruta)
        ? finalidadeBruta
        : undefined,
    tipo: tipoBruto && TIPOS.has(tipoBruto) ? tipoBruto : undefined,
    origemId: inteiroPositivo(params.get("origem_id")),
    equipeId: inteiroPositivo(params.get("equipe_id")),
    corretorId: inteiroPositivo(params.get("corretor_id")),
  };
}

/** Colunas de filtro disponíveis em cada view (lista fechada, server-side). */
export type ColunasView = {
  cidade?: boolean;
  finalidade?: boolean;
  tipo?: boolean;
  origem?: boolean;
  equipe?: boolean;
  corretor?: boolean;
};

/**
 * Monta "WHERE competencia BETWEEN $1 AND $2 AND ..." com valores
 * parametrizados. Retorna também os valores na ordem dos placeholders.
 */
export function montarWhere(
  filtros: Filtros,
  colunas: ColunasView,
  campoData = "data_ref",
): { where: string; valores: (string | number)[] } {
  const condicoes: string[] = [`${campoData} BETWEEN $1 AND $2`];
  const valores: (string | number)[] = [
    campoData === "competencia" ? filtros.competenciaDe : filtros.de,
    campoData === "competencia" ? filtros.competenciaAte : filtros.ate,
  ];

  const adicionar = (condicao: string, valor: string | number) => {
    valores.push(valor);
    condicoes.push(condicao.replace("?", `$${valores.length}`));
  };

  if (colunas.cidade && filtros.cidadeId !== undefined) {
    adicionar("cidade_id = ?", filtros.cidadeId);
  }
  if (colunas.finalidade && filtros.finalidade !== undefined) {
    adicionar("finalidade = ?", filtros.finalidade);
  }
  if (colunas.tipo && filtros.tipo !== undefined) {
    adicionar("tipo = ?", filtros.tipo);
  }
  if (colunas.origem && filtros.origemId !== undefined) {
    adicionar("origem_id = ?", filtros.origemId);
  }
  if (colunas.equipe && filtros.equipeId !== undefined) {
    adicionar("equipe_id = ?", filtros.equipeId);
  }
  if (colunas.corretor && filtros.corretorId !== undefined) {
    adicionar("corretor_id = ?", filtros.corretorId);
  }

  return { where: `WHERE ${condicoes.join(" AND ")}`, valores };
}

/**
 * Período anterior de mesmo tamanho (usado na variação % dos cartões).
 * Ex.: recorte 2025-09-01..2026-08-31 (365 dias) -> período anterior termina em
 * 2025-08-31 e começa 365 dias antes.
 */
export function periodoAnterior(filtros: Filtros): Filtros {
  const de = new Date(`${filtros.de}T00:00:00Z`);
  const ate = new Date(`${filtros.ate}T00:00:00Z`);
  const duracaoMs = ate.getTime() - de.getTime();
  const anteriorAte = new Date(de.getTime() - 86_400_000);
  const anteriorDe = new Date(anteriorAte.getTime() - duracaoMs);
  const deStr = anteriorDe.toISOString().slice(0, 10);
  const ateStr = anteriorAte.toISOString().slice(0, 10);
  return {
    ...filtros,
    de: deStr,
    ate: ateStr,
    competenciaDe: competencia(deStr),
    competenciaAte: competencia(ateStr),
  };
}

/** Paginação saneada: página >= 1, por_pagina entre 1 e 100 (padrão 10). */
export function parsePaginacao(params: URLSearchParams): {
  pagina: number;
  porPagina: number;
} {
  const pagina = inteiroPositivo(params.get("pagina")) ?? 1;
  const porPaginaBruta = inteiroPositivo(params.get("por_pagina")) ?? 10;
  return { pagina, porPagina: Math.min(porPaginaBruta, 100) };
}
