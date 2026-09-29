// INTRODUÇÃO
// GET /api/dashboard/ultimos-negocios — tabela paginada dos últimos negócios
// fechados (mais recentes primeiro), com todos os filtros do Dashboard.
// Fonte: analytics.v_negocios_detalhe (uma linha por negócio, já com as
// dimensões). A exportação para Excel fica na sub-rota /exportar.
// RESUMO: { linhas: [...], total, pagina, por_pagina }.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros, parsePaginacao } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { pagina, porPagina } = parsePaginacao(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_fechamento");

  const total = await pool.query(
    `SELECT COUNT(*)::INT AS total FROM analytics.v_negocios_detalhe
     ${where} AND status = 'fechado'`,
    valores,
  );
  const r = await pool.query(
    `SELECT negocio_id, data_fechamento, cidade, bairro, tipo, finalidade,
            corretor, equipe, origem, valor_negocio, valor_comissao,
            tempo_fechamento_dias
     FROM analytics.v_negocios_detalhe
     ${where} AND status = 'fechado'
     ORDER BY data_fechamento DESC, negocio_id DESC
     LIMIT $${valores.length + 1} OFFSET $${valores.length + 2}`,
    [...valores, porPagina, (pagina - 1) * porPagina],
  );
  return NextResponse.json({
    linhas: r.rows,
    total: total.rows[0].total,
    pagina,
    por_pagina: porPagina,
  });
}
