// INTRODUÇÃO
// GET /api/dashboard/realizado-meta — realizado x meta por equipe e mês, para
// o gráfico "realizado × meta do mês por equipe". Devolve todas as competências
// do recorte; o gráfico mostra a mais recente (com seletor de mês na página).
// Fonte: analytics.v_realizado_meta.
// RESUMO: [{ competencia, equipe, realizado_negocios, meta_negocios,
// realizado_vgv, meta_vgv }].

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { equipe: true }, "competencia");
  const r = await pool.query(
    `SELECT competencia, equipe,
            SUM(realizado_negocios)::INT AS realizado_negocios,
            SUM(meta_negocios)::INT AS meta_negocios,
            SUM(realizado_vgv)::FLOAT AS realizado_vgv,
            SUM(meta_vgv)::FLOAT AS meta_vgv
     FROM analytics.v_realizado_meta ${where}
     GROUP BY competencia, equipe
     ORDER BY competencia, equipe`,
    valores,
  );
  return NextResponse.json(r.rows);
}
