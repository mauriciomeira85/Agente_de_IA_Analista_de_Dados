// INTRODUÇÃO
// Pool de conexões PostgreSQL (node-postgres) usado por TODOS os route handlers
// do Dashboard. Fica num módulo único para que o Next.js reutilize o mesmo pool
// entre requisições (evita abrir uma conexão por chamada e estourar o limite do
// banco). As credenciais vêm das variáveis de ambiente injetadas pelo
// docker-compose (PGHOST=db, PGDATABASE=analista_dados, PGUSER=app_dashboard,
// PGPASSWORD). O usuário app_dashboard tem acesso somente de leitura às views
// de analytics e às dims, então este pool nunca escreve no banco.
// RESUMO: exporta um Pool singleton de pg configurado por env, com max baixo
// para caber no limite de memória da VM.

import { Pool } from "pg";

// Em dev (next dev com hot reload) o módulo pode ser reavaliado; guardar o pool
// no globalThis evita vazamento de conexões a cada reload.
const globalParaPool = globalThis as unknown as { __poolDashboard?: Pool };

export const pool =
  globalParaPool.__poolDashboard ??
  new Pool({
    host: process.env.PGHOST ?? "localhost",
    port: Number(process.env.PGPORT ?? 5432),
    database: process.env.PGDATABASE ?? "analista_dados",
    user: process.env.PGUSER ?? "app_dashboard",
    password: process.env.PGPASSWORD,
    max: 5,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });

if (process.env.NODE_ENV !== "production") {
  globalParaPool.__poolDashboard = pool;
}
