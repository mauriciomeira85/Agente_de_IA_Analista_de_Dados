// INTRODUÇÃO
// Aba "Agente de IA" (rota /agente): chat com o Analista de Dados.
//   * histórico restaurado do banco (por sessão anônima salva no navegador,
//     em localStorage) e mantido também localmente;
//   * resposta em STREAMING (SSE): o texto aparece token a token;
//   * gráficos gerados pelo agente são desenhados dentro do chat (spec
//     ECharts chega como evento SSE próprio);
//   * PDFs e planilhas gerados viram links de download (/api/agente/arquivo/…);
//   * sugestões de perguntas prontas para clicar.
// RESUMO: componente cliente que consome POST /api/agente/chat (SSE) e renderiza
// mensagens com markdown, gráficos e downloads.

"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm"; // tabelas e listas no padrão GitHub
import { useQuery } from "@tanstack/react-query";
import { FileDown, SendHorizonal } from "lucide-react";
import { GraficoECharts } from "@/components/GraficoECharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const SUGESTOES = [
  "Qual corretor mais vendeu nos últimos 12 meses?",
  "Qual origem de lead converte melhor?",
  "Mostre o funil comercial do último trimestre com gráfico.",
  "Gere um relatório em PDF das vendas de 2025.",
  "Exporte uma planilha Excel dos negócios fechados do último trimestre.",
  "Qual bairro está em alta nos últimos 6 meses?",
];

interface ArtefatoArquivo {
  tipo: "arquivo";
  url: string;
  formato: string;
  titulo?: string;
}
interface ArtefatoGrafico {
  tipo: "grafico";
  spec: Record<string, unknown>;
}
type Artefato = ArtefatoArquivo | ArtefatoGrafico;

interface Mensagem {
  papel: "usuario" | "assistente";
  conteudo: string;
  artefatos?: Artefato[];
}

/** Sessão anônima persistente do navegador (uuid em localStorage). */
function obterSessao(): string {
  const CHAVE = "agente-analista-sessao";
  let sessao = localStorage.getItem(CHAVE);
  if (!sessao) {
    sessao = crypto.randomUUID();
    localStorage.setItem(CHAVE, sessao);
  }
  return sessao;
}

/** Converte a URL interna do agente (/arquivos/x.pdf) na rota pública do site. */
function urlDownload(url: string): string {
  const nome = url.split("/").pop() ?? "";
  return `/api/agente/arquivo/${nome}`;
}

export default function PaginaAgente() {
  const [sessao, setSessao] = useState<string | null>(null);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [entrada, setEntrada] = useState("");
  const [gerando, setGerando] = useState(false);
  const fimRef = useRef<HTMLDivElement>(null);

  // A sessão só existe no navegador: inicializa após a montagem (evita SSR).
  useEffect(() => {
    setSessao(obterSessao());
  }, []);

  // Restaura o histórico salvo no banco para a sessão.
  const { data: historico } = useQuery({
    queryKey: ["historico-agente", sessao],
    enabled: !!sessao,
    queryFn: async () => {
      const r = await fetch(`/api/agente/conversas/${sessao}`);
      if (!r.ok) return { mensagens: [] };
      return (await r.json()) as {
        mensagens: Mensagem[];
      };
    },
    staleTime: Infinity,
  });
  useEffect(() => {
    if (historico && mensagens.length === 0) {
      setMensagens(historico.mensagens.map((m) => ({
        papel: m.papel,
        conteudo: m.conteudo,
        artefatos: m.artefatos,
      })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historico]);

  useEffect(() => {
    if (sessao && mensagens.length) localStorage.setItem(`historico-${sessao}`, JSON.stringify(mensagens));
  }, [sessao, mensagens]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens]);

  /** Envia a pergunta e consome o fluxo SSE token a token. */
  async function perguntar(texto: string) {
    if (!texto.trim() || !sessao || gerando) return;
    setGerando(true);
    setEntrada("");
    setMensagens((m) => [...m,
      { papel: "usuario", conteudo: texto },
      { papel: "assistente", conteudo: "" },
    ]);

    try {
      const resposta = await fetch("/api/agente/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessao, pergunta: texto }),
      });
      if (resposta.status === 429) {
        const dados = await resposta.json().catch(() => ({}));
        throw new Error(dados.erro ?? "limite de uso atingido");
      }
      if (!resposta.ok || !resposta.body) {
        throw new Error("o agente está indisponível no momento");
      }

      const leitor = resposta.body.getReader();
      const decodificador = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await leitor.read();
        if (done) break;
        buffer += decodificador.decode(value, { stream: true });
        // Eventos SSE chegam como "data: {json}\n\n".
        const partes = buffer.split("\n\n");
        buffer = partes.pop() ?? "";
        for (const parte of partes) {
          const linha = parte.replace(/^data: /, "").trim();
          if (!linha) continue;
          let evento: Record<string, never> | Record<string, unknown>;
          try {
            evento = JSON.parse(linha);
          } catch {
            continue;
          }
          if (evento.tipo === "token") {
            const trecho = String(evento.texto ?? "");
            setMensagens((m) => {
              const copia = [...m];
              const ultima = copia[copia.length - 1];
              copia[copia.length - 1] = {
                ...ultima, conteudo: ultima.conteudo + trecho,
              };
              return copia;
            });
          } else if (evento.tipo === "grafico") {
            setMensagens((m) => {
              const copia = [...m];
              const ultima = copia[copia.length - 1];
              copia[copia.length - 1] = {
                ...ultima,
                artefatos: [...(ultima.artefatos ?? []),
                  { tipo: "grafico", spec: evento.spec } as Artefato],
              };
              return copia;
            });
          } else if (evento.tipo === "arquivo") {
            setMensagens((m) => {
              const copia = [...m];
              const ultima = copia[copia.length - 1];
              copia[copia.length - 1] = {
                ...ultima,
                artefatos: [...(ultima.artefatos ?? []), {
                  tipo: "arquivo",
                  url: String(evento.url),
                  formato: String(evento.formato),
                  titulo: String(evento.titulo ?? ""),
                }],
              };
              return copia;
            });
          } else if (evento.tipo === "erro") {
            setMensagens((m) => {
              const copia = [...m];
              copia[copia.length - 1] = {
                papel: "assistente",
                conteudo: `⚠️ ${String(evento.mensagem)}`,
              };
              return copia;
            });
          }
        }
      }
    } catch (erro) {
      setMensagens((m) => {
        const copia = [...m];
        copia[copia.length - 1] = {
          papel: "assistente",
          conteudo: `⚠️ ${erro instanceof Error ? erro.message : "falha inesperada"}`,
        };
        return copia;
      });
    } finally {
      setGerando(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <Card>
        <CardContent className="flex max-h-[62vh] flex-col gap-3 overflow-y-auto p-4">
          {mensagens.length === 0 && (
            <div className="py-6 text-center">
              <p className="font-medium">Olá! Sou o Analista de Dados da Serra
                Clara Imóveis.</p>
              <p className="mt-1 text-sm text-[var(--texto-suave)]">
                Pergunte sobre leads, vendas, locações, corretores, metas e
                origens de lead. Todos os dados são fictícios.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGESTOES.map((s) => (
                  <button
                    key={s}
                    onClick={() => perguntar(s)}
                    className="rounded-full border border-[var(--borda)] bg-white px-3 py-1.5 text-xs text-slate-600 hover:border-amber-600 hover:text-amber-800"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mensagens.map((m, i) => (
            <div
              key={i}
              className={cn(
                "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm",
                m.papel === "usuario"
                  ? "self-end bg-[var(--destaque)] text-white"
                  : "self-start bg-slate-100 text-slate-800",
              )}
            >
              {m.papel === "assistente" ? (
                <>
                  <div className="resposta-agente">
                    {/* Links internos do agente (/arquivos/x.pdf) viram a rota pública de download. */}
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{(m.conteudo || (gerando && i === mensagens.length - 1 ? "…" : ""))
                      .replaceAll("](/arquivos/", "](/api/agente/arquivo/")}</ReactMarkdown>
                  </div>
                  {m.artefatos?.map((a, j) =>
                    a.tipo === "grafico" ? (
                      <div key={j} className="mt-2 rounded-lg bg-white p-2">
                        <GraficoECharts spec={a.spec} altura={280} />
                      </div>
                    ) : (
                      <a
                        key={j}
                        href={urlDownload(a.url)}
                        className="mt-2 inline-flex items-center gap-2 rounded-lg border border-amber-600/40 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100"
                      >
                        <FileDown className="h-4 w-4" />
                        Baixar {(a.titulo || "arquivo").slice(0, 60)} ({a.formato})
                      </a>
                    ),
                  )}
                </>
              ) : (
                m.conteudo
              )}
            </div>
          ))}
          <div ref={fimRef} />
        </CardContent>
      </Card>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          perguntar(entrada);
        }}
      >
        <input
          value={entrada}
          onChange={(e) => setEntrada(e.target.value)}
          placeholder="Pergunte sobre os dados da imobiliária…"
          maxLength={2000}
          disabled={gerando}
          className="h-11 flex-1 rounded-xl border border-[var(--borda)] bg-white px-4 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-600/40"
        />
        <Button type="submit" disabled={gerando || !entrada.trim()} className="h-11 rounded-xl">
          <SendHorizonal className="h-4 w-4" />
          {gerando ? "Gerando…" : "Enviar"}
        </Button>
      </form>
      <p className="text-center text-xs text-[var(--texto-suave)]">
        Assistente público de demonstração: limite de {20} perguntas por hora.
        Arquivos gerados ficam disponíveis por 24 horas.
      </p>
    </div>
  );
}
