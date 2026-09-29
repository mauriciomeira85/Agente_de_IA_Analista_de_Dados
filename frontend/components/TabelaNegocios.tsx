// INTRODUÇÃO
// Tabela paginada dos últimos negócios fechados (rodapé do Dashboard), com
// botão de exportação para Excel (sub-rota /exportar da API). Mostra estado de
// carregamento, vazio e erro como o restante da página.
// RESUMO: <TabelaNegocios filtros /> busca /api/dashboard/ultimos-negocios e
// pagina no servidor.

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatarData, formatarMoeda, paraQueryString } from "@/lib/format";
import { rotulo, type EstadoFiltros } from "./BarraFiltros";

interface Linha {
  negocio_id: number;
  data_fechamento: string;
  cidade: string;
  bairro: string;
  tipo: string;
  finalidade: string;
  corretor: string;
  equipe: string;
  origem: string;
  valor_negocio: number;
  valor_comissao: number;
  tempo_fechamento_dias: number;
}

export function TabelaNegocios({ filtros }: { filtros: EstadoFiltros }) {
  const [pagina, setPagina] = useState(1);
  const porPagina = 10;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["ultimos-negocios", filtros, pagina],
    queryFn: async () => {
      const r = await fetch(
        `/api/dashboard/ultimos-negocios${paraQueryString({
          ...filtros, pagina, por_pagina: porPagina,
        })}`,
      );
      if (!r.ok) throw new Error("falha ao carregar negócios");
      return (await r.json()) as {
        linhas: Linha[]; total: number; pagina: number; por_pagina: number;
      };
    },
  });

  if (isLoading) return <Skeleton className="h-72" />;
  if (isError || !data)
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Não foi possível carregar os últimos negócios.
      </p>
    );

  const totalPaginas = Math.max(1, Math.ceil(data.total / porPagina));
  const urlExportar = `/api/dashboard/ultimos-negocios/exportar${paraQueryString({ ...filtros })}`;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-[var(--texto-suave)]">
          {data.total.toLocaleString("pt-BR")} negócios fechados no recorte
        </p>
        <a href={urlExportar} download className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <Download className="h-4 w-4" /> Exportar Excel
        </a>
      </div>
      <div className="overflow-x-auto rounded-lg border border-[var(--borda)]">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              {["Fechamento", "Cidade", "Bairro", "Tipo", "Finalidade",
                "Corretor", "Origem", "Valor", "Comissão", "Ciclo"].map((c) => (
                <th key={c} className="px-3 py-2 font-medium">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.linhas.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-8 text-center text-slate-400">
                  Nenhum negócio fechado no recorte selecionado.
                </td>
              </tr>
            )}
            {data.linhas.map((l) => (
              <tr key={l.negocio_id} className="hover:bg-slate-50">
                <td className="px-3 py-2">{formatarData(l.data_fechamento)}</td>
                <td className="px-3 py-2">{l.cidade}</td>
                <td className="px-3 py-2">{l.bairro}</td>
                <td className="px-3 py-2">{rotulo(l.tipo)}</td>
                <td className="px-3 py-2">{rotulo(l.finalidade)}</td>
                <td className="px-3 py-2">{l.corretor}</td>
                <td className="px-3 py-2">{l.origem}</td>
                <td className="px-3 py-2 font-medium">{formatarMoeda(l.valor_negocio)}</td>
                <td className="px-3 py-2">{formatarMoeda(l.valor_comissao)}</td>
                <td className="px-3 py-2">{l.tempo_fechamento_dias} d</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-end gap-2 text-sm">
        <Button
          variant="outline" size="sm"
          disabled={pagina <= 1}
          onClick={() => setPagina((p) => p - 1)}
        >
          Anterior
        </Button>
        <span className="text-[var(--texto-suave)]">
          página {pagina} de {totalPaginas}
        </span>
        <Button
          variant="outline" size="sm"
          disabled={pagina >= totalPaginas}
          onClick={() => setPagina((p) => p + 1)}
        >
          Próxima
        </Button>
      </div>
    </div>
  );
}
