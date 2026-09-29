// INTRODUÇÃO
// GET /api/dashboard/opcoes — devolve as listas de valores dos filtros do topo
// do Dashboard (cidades, origens, equipes, corretores ativos, tipos de imóvel
// e finalidades) e a faixa de meses com dados (para o filtro de período).
// Consulta as dimensões com o usuário somente leitura app_dashboard.
// RESUMO: um JSON com as opções de cada filtro; usado na montagem da página.

import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const [cidades, origens, equipes, corretores, periodo] = await Promise.all([
    pool.query("SELECT cidade_id, cidade FROM curated.dim_cidade ORDER BY cidade"),
    pool.query(
      "SELECT origem_id, nome_origem FROM curated.dim_origem ORDER BY nome_origem"),
    pool.query(
      "SELECT equipe_id, nome_equipe FROM curated.dim_equipe ORDER BY nome_equipe"),
    pool.query(
      `SELECT corretor_id, nome_corretor, equipe_id FROM curated.dim_corretor
       WHERE ativo ORDER BY nome_corretor`),
    pool.query(
      "SELECT MIN(competencia) AS de, MAX(competencia) AS ate FROM analytics.v_funil_mensal"),
  ]);
  return NextResponse.json({
    cidades: cidades.rows,
    origens: origens.rows,
    equipes: equipes.rows,
    corretores: corretores.rows,
    tipos: ["apartamento", "casa", "sala_comercial", "terreno"],
    finalidades: ["venda", "locacao"],
    periodo_dados: periodo.rows[0] ?? null,
  });
}
