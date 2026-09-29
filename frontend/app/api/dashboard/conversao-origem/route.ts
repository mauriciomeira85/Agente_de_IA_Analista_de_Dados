// INTRODUÇÃO
// GET /api/dashboard/conversao-origem — leads, negócios fechados e taxa de
// conversão por origem do lead, para o gráfico "leads e conversão por origem".
// Fonte: analytics.v_conversao_origem (a taxa é recalculada sobre os somatórios
// do recorte, nunca pela média das taxas mensais).
// RESUMO: [{ origem, leads, fechados, taxa_conversao }] ordenado por leads.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT origem,
            SUM(leads)::INT AS leads,
            SUM(fechados)::INT AS fechados,
            ROUND(SUM(fechados)::NUMERIC / NULLIF(SUM(leads), 0), 4)::FLOAT
              AS taxa_conversao
     FROM analytics.v_conversao_origem ${where}
     GROUP BY origem ORDER BY leads DESC`,
    valores,
  );
  return NextResponse.json(r.rows);
}
