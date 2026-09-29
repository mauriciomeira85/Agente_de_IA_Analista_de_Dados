// INTRODUÇÃO
// ESLint usa os exports flat nativos do Next.js 16, compatíveis com ESLint 10.
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";
const config = [
  ...nextVitals,
  ...nextTypescript,
  { ignores: [".next/**", "node_modules/**", "out/**", "next-env.d.ts"] },
];
// RESUMO: regras oficiais sem conversão do formato legado.

export default config;
