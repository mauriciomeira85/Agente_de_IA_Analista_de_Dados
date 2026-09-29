// INTRODUÇÃO
// Formatadores de exibição pt-BR usados nos cartões, gráficos e tabela do
// Dashboard (valores monetários, inteiros, percentuais e datas) e um helper
// para montar a query string dos filtros nas chamadas fetch do cliente.
// Centralizar aqui garante formatação idêntica em todos os blocos da página.
// RESUMO: formatarMoeda / formatarNumero / formatarPercentual / formatarData /
// formatarCompetencia / paraQueryString.

export function formatarMoeda(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: valor >= 1000 ? 0 : 2,
  }).format(valor);
}

export function formatarNumero(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(
    valor,
  );
}

export function formatarPercentual(
  valor: number | null | undefined,
  casas = 1,
): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return `${new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(valor)}%`;
}

/** Variação percentual entre período atual e anterior; null se base zero. */
export function calcularVariacao(
  atual: number,
  anterior: number,
): number | null {
  if (!anterior || anterior === 0) return null;
  return ((atual - anterior) / anterior) * 100;
}

export function formatarData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR", { timeZone: "UTC" });
}

const MESES_ABREV = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

/** '2026-03' -> 'mar/26' (rótulo curto dos eixos dos gráficos). */
export function formatarCompetencia(competencia: string): string {
  const [ano, mes] = competencia.split("-");
  const indice = Number(mes) - 1;
  if (indice < 0 || indice > 11) return competencia;
  return `${MESES_ABREV[indice]}/${ano.slice(2)}`;
}

/** Formata timestamp do rodapé "Dados atualizados em ...". */
export function formatarDataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Monta "?de=...&ate=...&cidade_id=..." ignorando filtros vazios. */
export function paraQueryString(
  filtros: Record<string, string | number | undefined>,
): string {
  const params = new URLSearchParams();
  for (const [chave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "") params.set(chave, String(valor));
  }
  const texto = params.toString();
  return texto ? `?${texto}` : "";
}
