// INTRODUÇÃO
// GET /api/dashboard/ranking-corretores — negócios fechados e VGV de vendas
// por corretor, para o gráfico de ranking. Fonte: analytics.v_ranking_corretores.
// RESUMO: [{ corretor, equipe, negocios, vgv }] ordenado por negócios.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT corretor, MIN(equipe) AS equipe,
            SUM(negocios_fechados)::INT AS negocios,
            COALESCE(SUM(vgv_vendas), 0)::FLOAT AS vgv
     FROM analytics.v_ranking_corretores ${where}
     GROUP BY corretor ORDER BY negocios DESC, vgv DESC LIMIT 15`,
    valores,
  );
  return NextResponse.json(r.rows);
}
