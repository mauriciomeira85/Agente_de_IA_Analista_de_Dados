// INTRODUÇÃO
// GET /api/dashboard/bairro-tipo — duas agregações de negócios fechados no
// recorte: por bairro (top 10, com VGV) e por tipo de imóvel. Alimenta os
// gráficos "negócios por bairro" e "negócios por tipo". Fonte:
// analytics.v_negocios_bairro_tipo.
// RESUMO: { por_bairro: [...], por_tipo: [...] }.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const [porBairro, porTipo] = await Promise.all([
    pool.query(
      `SELECT bairro, cidade,
              SUM(negocios_fechados)::INT AS negocios,
              COALESCE(SUM(vgv) FILTER (WHERE finalidade = 'venda'), 0)::FLOAT AS vgv
       FROM analytics.v_negocios_bairro_tipo ${where}
       GROUP BY bairro, cidade ORDER BY negocios DESC LIMIT 10`,
      valores,
    ),
    pool.query(
      `SELECT tipo,
              SUM(negocios_fechados)::INT AS negocios,
              COALESCE(SUM(vgv) FILTER (WHERE finalidade = 'venda'), 0)::FLOAT AS vgv
       FROM analytics.v_negocios_bairro_tipo ${where}
       GROUP BY tipo ORDER BY negocios DESC`,
      valores,
    ),
  ]);
  return NextResponse.json({ por_bairro: porBairro.rows, por_tipo: porTipo.rows });
}
