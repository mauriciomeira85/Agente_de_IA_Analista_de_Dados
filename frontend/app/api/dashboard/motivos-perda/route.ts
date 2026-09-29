// INTRODUÇÃO
// GET /api/dashboard/motivos-perda — negócios perdidos por motivo, já em
// formato de Pareto (ordenado do maior para o menor, com percentual acumulado
// calculado aqui para o gráfico só desenhar). Fonte: analytics.v_motivos_perda.
// A view não tem dimensões de filtro além de competência, então os filtros de
// cidade/tipo/etc. não se aplicam (documentado no card do gráfico).
// RESUMO: [{ motivo_perda, total, perc_acumulado }].

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT motivo_perda, SUM(total)::INT AS total
     FROM analytics.v_motivos_perda ${where}
     GROUP BY motivo_perda ORDER BY total DESC`,
    valores,
  );
  const total = r.rows.reduce((acc, l) => acc + l.total, 0);
  let acumulado = 0;
  const linhas = r.rows.map((l) => {
    acumulado += l.total;
    return {
      ...l,
      perc_acumulado: total > 0 ? acumulado / total : 0,
    };
  });
  return NextResponse.json(linhas);
}
