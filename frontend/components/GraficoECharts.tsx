// INTRODUÇÃO
// Wrapper único do Apache ECharts (echarts-for-react) usado por TODOS os
// gráficos do Dashboard e do chat. Centraliza: import dinâmico (o ECharts é
// pesado e não roda no SSR), tamanho padrão e estado de "sem dados".
// RESUMO: <GraficoECharts spec={...} altura={300} /> desenha o gráfico ou um
// aviso de vazio.

"use client";

import dynamic from "next/dynamic";
import type { EChartsOption } from "echarts";

// SSR desligado: o ECharts precisa do DOM. O loading mantém o espaço do layout.
const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center text-xs text-slate-400">
      carregando gráfico…
    </div>
  ),
});

export function GraficoECharts({
  spec,
  altura = 300,
}: {
  spec: EChartsOption;
  altura?: number;
}) {
  return (
    <ReactECharts
      option={spec}
      style={{ height: altura, width: "100%" }}
      notMerge
      lazyUpdate
    />
  );
}
