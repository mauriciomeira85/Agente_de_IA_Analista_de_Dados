// INTRODUÇÃO
// GET /api/dashboard/vgv-mensal — série mensal de VGV (só vendas, pela definição
// do catálogo) e número de negócios fechados (venda + locação), para o gráfico
// "VGV e negócios por mês". Fonte: analytics.v_vgv_mensal.
// RESUMO: [{ competencia, vgv, negocios }] ordenado por competencia.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT competencia,
            COALESCE(SUM(vgv) FILTER (WHERE finalidade = 'venda'), 0)::FLOAT AS vgv,
            COALESCE(SUM(negocios_fechados), 0)::INT AS negocios
     FROM analytics.v_vgv_mensal ${where}
     GROUP BY competencia ORDER BY competencia`,
    valores,
  );
  return NextResponse.json(r.rows);
}
