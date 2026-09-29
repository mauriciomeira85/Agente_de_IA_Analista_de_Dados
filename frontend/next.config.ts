// INTRODUÇÃO
// Configuração do Next.js do frontend da Serra Clara Imóveis.
// `output: 'standalone'` gera um servidor Node autocontido em .next/standalone,
// que é o que o Dockerfile copia para a imagem final (runner enxuto, sem
// node_modules completo). `serverExternalPackages` impede o bundler de tentar
// empacotar o `pg`/`exceljs` (módulos nativos/streaming que devem rodar no Node).
// RESUMO: build standalone para Docker + pg/exceljs externos ao bundle.

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["pg", "exceljs"],
};

export default nextConfig;
