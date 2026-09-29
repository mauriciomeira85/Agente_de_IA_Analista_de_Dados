-- INTRODUÇÃO
-- Migração 004: tabelas dos schemas `app` (histórico do agente de IA) e `audit`
-- (rastreabilidade de cargas e de execuções do agente). Guardar conversas no banco
-- permite retomar o histórico por sessão anônima e auditar custos da DeepSeek.
-- RESUMO: app.agente_conversas, app.agente_mensagens, audit.cargas,
-- audit.agente_execucoes e audit.limite_ip (controle de uso por IP).

CREATE TABLE app.agente_conversas (
    conversa_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sessao      TEXT NOT NULL,
    criada_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE  app.agente_conversas IS 'Conversas do agente de IA, identificadas por sessão anônima do navegador.';
COMMENT ON COLUMN app.agente_conversas.conversa_id IS 'Identificador da conversa.';
COMMENT ON COLUMN app.agente_conversas.sessao      IS 'Identificador anônimo da sessão (gerado no navegador).';
COMMENT ON COLUMN app.agente_conversas.criada_em   IS 'Data/hora de criação.';

CREATE TABLE app.agente_mensagens (
    mensagem_id BIGSERIAL PRIMARY KEY,
    conversa_id UUID NOT NULL REFERENCES app.agente_conversas(conversa_id),
    papel       TEXT NOT NULL CHECK (papel IN ('usuario','assistente')),
    conteudo    TEXT NOT NULL,
    criada_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE  app.agente_mensagens IS 'Mensagens trocadas em cada conversa do agente.';
COMMENT ON COLUMN app.agente_mensagens.mensagem_id IS 'Identificador da mensagem.';
COMMENT ON COLUMN app.agente_mensagens.conversa_id IS 'Conversa à qual a mensagem pertence.';
COMMENT ON COLUMN app.agente_mensagens.papel       IS 'usuario ou assistente.';
COMMENT ON COLUMN app.agente_mensagens.conteudo    IS 'Texto da mensagem.';
COMMENT ON COLUMN app.agente_mensagens.criada_em   IS 'Data/hora da mensagem.';

CREATE TABLE audit.cargas (
    carga_id       SERIAL PRIMARY KEY,
    executada_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    semente        INTEGER NOT NULL,
    qtd_leads      INTEGER NOT NULL,
    qtd_visitas    INTEGER NOT NULL,
    qtd_propostas  INTEGER NOT NULL,
    qtd_negocios   INTEGER NOT NULL,
    qtd_imoveis    INTEGER NOT NULL,
    observacao     TEXT
);
COMMENT ON TABLE  audit.cargas IS 'Registro de cada carga de dados fictícios (o rodapé "Dados atualizados em" lê daqui).';
COMMENT ON COLUMN audit.cargas.carga_id      IS 'Identificador da carga.';
COMMENT ON COLUMN audit.cargas.executada_em  IS 'Data/hora da carga.';
COMMENT ON COLUMN audit.cargas.semente       IS 'Semente aleatória usada (reprodutibilidade).';
COMMENT ON COLUMN audit.cargas.qtd_leads     IS 'Quantidade de leads gerados.';
COMMENT ON COLUMN audit.cargas.qtd_visitas   IS 'Quantidade de visitas geradas.';
COMMENT ON COLUMN audit.cargas.qtd_propostas IS 'Quantidade de propostas geradas.';
COMMENT ON COLUMN audit.cargas.qtd_negocios  IS 'Quantidade de negócios gerados.';
COMMENT ON COLUMN audit.cargas.qtd_imoveis   IS 'Quantidade de imóveis gerados.';
COMMENT ON COLUMN audit.cargas.observacao    IS 'Observações da carga.';

CREATE TABLE audit.agente_execucoes (
    execucao_id     BIGSERIAL PRIMARY KEY,
    conversa_id     UUID,
    executada_em    TIMESTAMPTZ NOT NULL DEFAULT now(),
    pergunta        TEXT NOT NULL,
    ferramentas     JSONB NOT NULL DEFAULT '[]',
    sql_executado   TEXT,
    duracao_ms      INTEGER,
    tokens_entrada  INTEGER,
    tokens_saida    INTEGER,
    custo_usd       NUMERIC(10,6),
    ip              INET
);
COMMENT ON TABLE  audit.agente_execucoes IS 'Auditoria de cada pergunta ao agente: ferramentas usadas, SQL, duração, tokens e custo.';
COMMENT ON COLUMN audit.agente_execucoes.execucao_id    IS 'Identificador da execução.';
COMMENT ON COLUMN audit.agente_execucoes.conversa_id    IS 'Conversa relacionada.';
COMMENT ON COLUMN audit.agente_execucoes.executada_em   IS 'Data/hora da execução.';
COMMENT ON COLUMN audit.agente_execucoes.pergunta       IS 'Pergunta do usuário.';
COMMENT ON COLUMN audit.agente_execucoes.ferramentas    IS 'Lista JSON das ferramentas chamadas.';
COMMENT ON COLUMN audit.agente_execucoes.sql_executado  IS 'SQL executado (quando houver).';
COMMENT ON COLUMN audit.agente_execucoes.duracao_ms     IS 'Duração total em milissegundos.';
COMMENT ON COLUMN audit.agente_execucoes.tokens_entrada IS 'Tokens de entrada consumidos.';
COMMENT ON COLUMN audit.agente_execucoes.tokens_saida   IS 'Tokens de saída consumidos.';
COMMENT ON COLUMN audit.agente_execucoes.custo_usd      IS 'Custo estimado em USD.';
COMMENT ON COLUMN audit.agente_execucoes.ip             IS 'IP do usuário (controle de limite de uso).';

CREATE TABLE audit.limite_ip (
    ip             INET NOT NULL,
    janela_inicio  TIMESTAMPTZ NOT NULL,
    perguntas      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ip, janela_inicio)
);
COMMENT ON TABLE  audit.limite_ip IS 'Contador de perguntas por IP por janela de 1 hora (limite de uso do agente, que é público).';
COMMENT ON COLUMN audit.limite_ip.ip            IS 'IP do usuário.';
COMMENT ON COLUMN audit.limite_ip.janela_inicio IS 'Início da janela de 1 hora.';
COMMENT ON COLUMN audit.limite_ip.perguntas     IS 'Quantidade de perguntas feitas na janela.';
