// INTRODUÇÃO
// GET /api/dashboard/ultimos-negocios/exportar — exporta para .xlsx os negócios
// fechados do recorte filtrado (os mesmos dados da tabela, sem paginação,
// limitados a 5.000 linhas). Gera o arquivo em memória com exceljs e devolve
// como download — nada é gravado em disco.
// RESUMO: resposta binária com Content-Disposition attachment (.xlsx).

import { NextRequest, NextResponse } from "next/server";
import ExcelJS from "exceljs";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros } from "@/lib/filtros";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_fechamento");
  const r = await pool.query(
    `SELECT negocio_id AS "Negócio", data_fechamento AS "Fechamento",
            cidade AS "Cidade", bairro AS "Bairro", tipo AS "Tipo",
            finalidade AS "Finalidade", corretor AS "Corretor",
            equipe AS "Equipe", origem AS "Origem",
            valor_negocio AS "Valor do negócio (R$)",
            valor_comissao AS "Comissão (R$)",
            tempo_fechamento_dias AS "Ciclo (dias)"
     FROM analytics.v_negocios_detalhe
     ${where} AND status = 'fechado'
     ORDER BY data_fechamento DESC
     LIMIT 5000`,
    valores,
  );

  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet("Negócios fechados");
  if (r.rows.length > 0) {
    ws.columns = Object.keys(r.rows[0]).map((chave) => ({
      header: chave,
      key: chave,
      width: 18,
    }));
    for (const linha of r.rows) ws.addRow(linha);
    ws.getRow(1).font = { bold: true };
  }
  const buffer = await wb.xlsx.writeBuffer();
  return new NextResponse(Buffer.from(buffer), {
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition":
        'attachment; filename="ultimos-negocios-serra-clara.xlsx"',
    },
  });
}
