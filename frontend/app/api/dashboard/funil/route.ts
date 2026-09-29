// INTRODUÇÃO
// GET /api/dashboard/funil — totais do funil comercial (leads, visitas,
// propostas, fechados, perdidos) no recorte dos filtros, para o gráfico de
// funil da página. Fonte: analytics.v_funil_mensal (mesma view do agente).
// RESUMO: uma linha com os 5 totais.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT COALESCE(SUM(leads),0)::INT AS leads,
            COALESCE(SUM(visitas),0)::INT AS visitas,
            COALESCE(SUM(propostas),0)::INT AS propostas,
            COALESCE(SUM(fechados),0)::INT AS fechados,
            COALESCE(SUM(perdidos),0)::INT AS perdidos
     FROM analytics.v_funil_mensal ${where}`,
    valores,
  );
  return NextResponse.json(r.rows[0]);
}
