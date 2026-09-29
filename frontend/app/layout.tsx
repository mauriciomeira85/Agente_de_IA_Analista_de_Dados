// INTRODUÇÃO
// Layout raiz do Next.js (App Router): define HTML base, metadados e o menu
// superior com as duas abas da aplicação — "Dashboard" e "Agente de IA".
// Sem tela de login: a aplicação abre direto no Dashboard (decisão do escopo;
// a segurança é feita no backend, não por autenticação).
// RESUMO: <html> + header com navegação entre / e /agente + conteúdo da página.

import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Provedores } from "@/components/Provedores";
import { Navegacao } from "@/components/Navegacao";

export const metadata: Metadata = {
  title: "Agente Analista de Dados — Serra Clara Imóveis",
  description:
    "Dashboard comercial e agente de IA sobre dados fictícios de uma imobiliária (projeto de portfólio).",
};

export default function LayoutRaiz({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen">
        <header className="sticky top-0 z-20 border-b border-[var(--borda)] bg-white/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-2">
              <span className="rounded-md bg-[var(--destaque)] px-2 py-1 text-sm font-bold text-white">
                SC
              </span>
              <span className="font-semibold">
                Serra Clara Imóveis
                <span className="ml-2 hidden text-xs font-normal text-[var(--texto-suave)] sm:inline">
                  dados fictícios — projeto de portfólio
                </span>
              </span>
            </Link>
            <Navegacao />
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">
          <Provedores>{children}</Provedores>
        </main>
      </body>
    </html>
  );
}
