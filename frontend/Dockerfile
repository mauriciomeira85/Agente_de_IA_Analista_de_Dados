# INTRODUÇÃO
# Dockerfile do frontend Next.js (multi-stage, standalone):
#   1) deps    -> npm ci só com package-lock (cache de camadas);
#   2) builder -> next build com output "standalone" (servidor autocontido);
#   3) runner  -> imagem final enxuta (node alpine + standalone + public),
#                 sem node_modules completo, cabendo no limite de 256 MB da VM.
# RESUMO: build em 3 estágios; produção roda `node server.js` na porta 3000.

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# O build do Next é feito sem variáveis do banco: as credenciais só entram em
# runtime, nos route handlers (nada de segredo no bundle do cliente).
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
