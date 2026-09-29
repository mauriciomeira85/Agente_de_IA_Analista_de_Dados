-- INTRODUÇÃO
-- Migração 002: tabelas do schema `curated` (modelo estrela simplificado da
-- imobiliária fictícia "Serra Clara Imóveis"): dimensões, imóveis, clientes,
-- fatos do funil comercial (leads -> visitas -> propostas -> negócios) e metas.
-- Todas as tabelas e colunas têm COMMENT ON em português, pois o dicionário de
-- dados é exposto ao agente de IA (ferramenta `descrever_tabelas`).
-- Atenção: `clientes` contém colunas sensíveis FICTÍCIAS (nome, CPF, telefone,
-- e-mail) que existem só para demonstrar as travas de segurança do agente.
-- RESUMO: estrutura física dos dados; as métricas ficam nas views de `analytics`.

-- ---------------------------------------------------------------------------
-- Dimensões
-- ---------------------------------------------------------------------------

CREATE TABLE curated.dim_cidade (
    cidade_id  SMALLSERIAL PRIMARY KEY,
    cidade     TEXT NOT NULL,
    uf         CHAR(2) NOT NULL,
    regiao     TEXT NOT NULL
);
COMMENT ON TABLE  curated.dim_cidade IS 'Cidades fictícias onde a imobiliária atua.';
COMMENT ON COLUMN curated.dim_cidade.cidade_id IS 'Identificador da cidade.';
COMMENT ON COLUMN curated.dim_cidade.cidade    IS 'Nome da cidade (fictício).';
COMMENT ON COLUMN curated.dim_cidade.uf        IS 'Unidade federativa (fictícia).';
COMMENT ON COLUMN curated.dim_cidade.regiao    IS 'Região administrativa da cidade (fictícia).';

CREATE TABLE curated.dim_bairro (
    bairro_id  SMALLSERIAL PRIMARY KEY,
    cidade_id  SMALLINT NOT NULL REFERENCES curated.dim_cidade(cidade_id),
    bairro     TEXT NOT NULL
);
COMMENT ON TABLE  curated.dim_bairro IS 'Bairros fictícios, ligados a uma cidade.';
COMMENT ON COLUMN curated.dim_bairro.bairro_id IS 'Identificador do bairro.';
COMMENT ON COLUMN curated.dim_bairro.cidade_id IS 'Cidade à qual o bairro pertence.';
COMMENT ON COLUMN curated.dim_bairro.bairro    IS 'Nome do bairro (fictício).';

CREATE TABLE curated.dim_equipe (
    equipe_id   SMALLSERIAL PRIMARY KEY,
    nome_equipe TEXT NOT NULL
);
COMMENT ON TABLE  curated.dim_equipe IS 'Equipes comerciais da imobiliária.';
COMMENT ON COLUMN curated.dim_equipe.equipe_id   IS 'Identificador da equipe.';
COMMENT ON COLUMN curated.dim_equipe.nome_equipe IS 'Nome da equipe (fictício).';

CREATE TABLE curated.dim_corretor (
    corretor_id    SMALLSERIAL PRIMARY KEY,
    nome_corretor  TEXT NOT NULL,
    equipe_id      SMALLINT NOT NULL REFERENCES curated.dim_equipe(equipe_id),
    data_admissao  DATE NOT NULL,
    ativo          BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE  curated.dim_corretor IS 'Corretores fictícios e sua equipe.';
COMMENT ON COLUMN curated.dim_corretor.corretor_id   IS 'Identificador do corretor.';
COMMENT ON COLUMN curated.dim_corretor.nome_corretor IS 'Nome fictício do corretor (gerado, não é pessoa real).';
COMMENT ON COLUMN curated.dim_corretor.equipe_id     IS 'Equipe do corretor.';
COMMENT ON COLUMN curated.dim_corretor.data_admissao IS 'Data de admissão (fictícia).';
COMMENT ON COLUMN curated.dim_corretor.ativo         IS 'Se o corretor está ativo.';

CREATE TABLE curated.dim_origem (
    origem_id   SMALLSERIAL PRIMARY KEY,
    nome_origem TEXT NOT NULL UNIQUE
);
COMMENT ON TABLE  curated.dim_origem IS 'Origens de lead: portal imobiliário, site, Instagram, Facebook Ads, Google Ads, indicação, placa no imóvel, plantão de vendas.';
COMMENT ON COLUMN curated.dim_origem.origem_id   IS 'Identificador da origem.';
COMMENT ON COLUMN curated.dim_origem.nome_origem IS 'Nome da origem do lead.';

CREATE TABLE curated.dim_campanha (
    campanha_id   SMALLSERIAL PRIMARY KEY,
    nome_campanha TEXT NOT NULL,
    origem_id     SMALLINT NOT NULL REFERENCES curated.dim_origem(origem_id),
    data_inicio   DATE NOT NULL,
    data_fim      DATE,
    investimento  NUMERIC(12,2) NOT NULL DEFAULT 0
);
COMMENT ON TABLE  curated.dim_campanha IS 'Campanhas de marketing fictícias associadas a uma origem.';
COMMENT ON COLUMN curated.dim_campanha.campanha_id   IS 'Identificador da campanha.';
COMMENT ON COLUMN curated.dim_campanha.nome_campanha IS 'Nome da campanha (fictício).';
COMMENT ON COLUMN curated.dim_campanha.origem_id     IS 'Origem/canal da campanha.';
COMMENT ON COLUMN curated.dim_campanha.data_inicio   IS 'Início da campanha.';
COMMENT ON COLUMN curated.dim_campanha.data_fim      IS 'Fim da campanha (nulo se contínua).';
COMMENT ON COLUMN curated.dim_campanha.investimento  IS 'Valor investido em R$ (fictício).';

CREATE TABLE curated.dim_calendario (
    data        DATE PRIMARY KEY,
    ano         SMALLINT NOT NULL,
    mes         SMALLINT NOT NULL,
    nome_mes    TEXT NOT NULL,
    trimestre   SMALLINT NOT NULL,
    competencia CHAR(7) NOT NULL  -- formato 'AAAA-MM'
);
COMMENT ON TABLE  curated.dim_calendario IS 'Calendário diário para análises por período.';
COMMENT ON COLUMN curated.dim_calendario.data        IS 'Data (chave).';
COMMENT ON COLUMN curated.dim_calendario.ano         IS 'Ano.';
COMMENT ON COLUMN curated.dim_calendario.mes         IS 'Mês (1-12).';
COMMENT ON COLUMN curated.dim_calendario.nome_mes    IS 'Nome do mês em português.';
COMMENT ON COLUMN curated.dim_calendario.trimestre   IS 'Trimestre (1-4).';
COMMENT ON COLUMN curated.dim_calendario.competencia IS 'Competência no formato AAAA-MM.';

-- ---------------------------------------------------------------------------
-- Imóveis e clientes
-- ---------------------------------------------------------------------------

CREATE TABLE curated.imoveis (
    imovel_id      SERIAL PRIMARY KEY,
    codigo         TEXT NOT NULL UNIQUE,
    tipo           TEXT NOT NULL CHECK (tipo IN ('apartamento','casa','sala_comercial','terreno')),
    finalidade     TEXT NOT NULL CHECK (finalidade IN ('venda','locacao')),
    bairro_id      SMALLINT NOT NULL REFERENCES curated.dim_bairro(bairro_id),
    area_m2        NUMERIC(8,2) NOT NULL,
    quartos        SMALLINT NOT NULL DEFAULT 0,
    valor_venda    NUMERIC(14,2),
    valor_aluguel  NUMERIC(12,2),
    data_captacao  DATE NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('disponivel','reservado','vendido','alugado'))
);
COMMENT ON TABLE  curated.imoveis IS 'Imóveis fictícios captados pela imobiliária.';
COMMENT ON COLUMN curated.imoveis.imovel_id     IS 'Identificador do imóvel.';
COMMENT ON COLUMN curated.imoveis.codigo        IS 'Código público do imóvel (ex.: AP0001).';
COMMENT ON COLUMN curated.imoveis.tipo          IS 'Tipo: apartamento, casa, sala_comercial ou terreno.';
COMMENT ON COLUMN curated.imoveis.finalidade    IS 'Finalidade: venda ou locacao.';
COMMENT ON COLUMN curated.imoveis.bairro_id     IS 'Bairro do imóvel.';
COMMENT ON COLUMN curated.imoveis.area_m2       IS 'Área em metros quadrados.';
COMMENT ON COLUMN curated.imoveis.quartos       IS 'Número de quartos (0 para terreno/sala).';
COMMENT ON COLUMN curated.imoveis.valor_venda   IS 'Preço de venda em R$ (quando finalidade venda).';
COMMENT ON COLUMN curated.imoveis.valor_aluguel IS 'Aluguel mensal em R$ (quando finalidade locacao).';
COMMENT ON COLUMN curated.imoveis.data_captacao IS 'Data em que o imóvel foi captado.';
COMMENT ON COLUMN curated.imoveis.status        IS 'Status: disponivel, reservado, vendido ou alugado.';

CREATE TABLE curated.clientes (
    cliente_id SERIAL PRIMARY KEY,
    nome       TEXT NOT NULL,
    cpf        TEXT NOT NULL,
    telefone   TEXT,
    email      TEXT
);
COMMENT ON TABLE  curated.clientes IS 'Clientes fictícios. ATENÇÃO: nome, CPF, telefone e e-mail são gerados e o agente de IA NÃO pode consultar essas colunas (trava de segurança).';
COMMENT ON COLUMN curated.clientes.cliente_id IS 'Identificador do cliente.';
COMMENT ON COLUMN curated.clientes.nome       IS 'Nome fictício (SENSÍVEL: bloqueado para o agente).';
COMMENT ON COLUMN curated.clientes.cpf        IS 'CPF fictício gerado (SENSÍVEL: bloqueado para o agente).';
COMMENT ON COLUMN curated.clientes.telefone   IS 'Telefone fictício (SENSÍVEL: bloqueado para o agente).';
COMMENT ON COLUMN curated.clientes.email      IS 'E-mail fictício (SENSÍVEL: bloqueado para o agente).';

-- ---------------------------------------------------------------------------
-- Fatos do funil comercial
-- ---------------------------------------------------------------------------

CREATE TABLE curated.fato_leads (
    lead_id          SERIAL PRIMARY KEY,
    data             DATE NOT NULL,
    origem_id        SMALLINT NOT NULL REFERENCES curated.dim_origem(origem_id),
    campanha_id      SMALLINT REFERENCES curated.dim_campanha(campanha_id),
    finalidade       TEXT NOT NULL CHECK (finalidade IN ('venda','locacao')),
    tipo_procurado   TEXT NOT NULL CHECK (tipo_procurado IN ('apartamento','casa','sala_comercial','terreno')),
    faixa_valor      TEXT NOT NULL,
    cidade_id        SMALLINT NOT NULL REFERENCES curated.dim_cidade(cidade_id),
    corretor_id      SMALLINT NOT NULL REFERENCES curated.dim_corretor(corretor_id),
    cliente_id       INTEGER REFERENCES curated.clientes(cliente_id),
    qualificado      BOOLEAN NOT NULL DEFAULT FALSE,
    descartado       BOOLEAN NOT NULL DEFAULT FALSE,
    motivo_descarte  TEXT
);
COMMENT ON TABLE  curated.fato_leads IS 'Leads recebidos: primeiro estágio do funil comercial.';
COMMENT ON COLUMN curated.fato_leads.lead_id         IS 'Identificador do lead.';
COMMENT ON COLUMN curated.fato_leads.data            IS 'Data de entrada do lead.';
COMMENT ON COLUMN curated.fato_leads.origem_id       IS 'Origem do lead.';
COMMENT ON COLUMN curated.fato_leads.campanha_id     IS 'Campanha que gerou o lead (pode ser nula).';
COMMENT ON COLUMN curated.fato_leads.finalidade      IS 'Interesse: venda ou locacao.';
COMMENT ON COLUMN curated.fato_leads.tipo_procurado  IS 'Tipo de imóvel procurado.';
COMMENT ON COLUMN curated.fato_leads.faixa_valor     IS 'Faixa de valor procurada (ex.: 300k-600k).';
COMMENT ON COLUMN curated.fato_leads.cidade_id       IS 'Cidade de interesse.';
COMMENT ON COLUMN curated.fato_leads.corretor_id     IS 'Corretor que recebeu o lead.';
COMMENT ON COLUMN curated.fato_leads.cliente_id      IS 'Cliente vinculado (dados pessoais bloqueados ao agente).';
COMMENT ON COLUMN curated.fato_leads.qualificado     IS 'Se o lead foi qualificado (perfil compatível).';
COMMENT ON COLUMN curated.fato_leads.descartado      IS 'Se o lead foi descartado sem avançar.';
COMMENT ON COLUMN curated.fato_leads.motivo_descarte IS 'Motivo do descarte, quando houver.';

CREATE TABLE curated.fato_visitas (
    visita_id   SERIAL PRIMARY KEY,
    lead_id     INTEGER NOT NULL REFERENCES curated.fato_leads(lead_id),
    imovel_id   INTEGER NOT NULL REFERENCES curated.imoveis(imovel_id),
    corretor_id SMALLINT NOT NULL REFERENCES curated.dim_corretor(corretor_id),
    data        DATE NOT NULL,
    compareceu  BOOLEAN NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE  curated.fato_visitas IS 'Visitas a imóveis: segundo estágio do funil.';
COMMENT ON COLUMN curated.fato_visitas.visita_id   IS 'Identificador da visita.';
COMMENT ON COLUMN curated.fato_visitas.lead_id     IS 'Lead que gerou a visita.';
COMMENT ON COLUMN curated.fato_visitas.imovel_id   IS 'Imóvel visitado.';
COMMENT ON COLUMN curated.fato_visitas.corretor_id IS 'Corretor que acompanhou.';
COMMENT ON COLUMN curated.fato_visitas.data        IS 'Data da visita (sempre após o lead).';
COMMENT ON COLUMN curated.fato_visitas.compareceu  IS 'Se o cliente compareceu.';

CREATE TABLE curated.fato_propostas (
    proposta_id     SERIAL PRIMARY KEY,
    lead_id         INTEGER NOT NULL REFERENCES curated.fato_leads(lead_id),
    imovel_id       INTEGER NOT NULL REFERENCES curated.imoveis(imovel_id),
    data            DATE NOT NULL,
    valor_proposto  NUMERIC(14,2) NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('aceita','recusada','em_analise'))
);
COMMENT ON TABLE  curated.fato_propostas IS 'Propostas enviadas: terceiro estágio do funil.';
COMMENT ON COLUMN curated.fato_propostas.proposta_id    IS 'Identificador da proposta.';
COMMENT ON COLUMN curated.fato_propostas.lead_id        IS 'Lead que originou a proposta.';
COMMENT ON COLUMN curated.fato_propostas.imovel_id      IS 'Imóvel da proposta.';
COMMENT ON COLUMN curated.fato_propostas.data           IS 'Data da proposta (após a visita).';
COMMENT ON COLUMN curated.fato_propostas.valor_proposto IS 'Valor proposto em R$.';
COMMENT ON COLUMN curated.fato_propostas.status         IS 'Status: aceita, recusada ou em_analise.';

CREATE TABLE curated.fato_negocios (
    negocio_id      SERIAL PRIMARY KEY,
    lead_id         INTEGER NOT NULL REFERENCES curated.fato_leads(lead_id),
    imovel_id       INTEGER NOT NULL REFERENCES curated.imoveis(imovel_id),
    corretor_id     SMALLINT NOT NULL REFERENCES curated.dim_corretor(corretor_id),
    finalidade      TEXT NOT NULL CHECK (finalidade IN ('venda','locacao')),
    data_abertura   DATE NOT NULL,
    data_fechamento DATE,
    status          TEXT NOT NULL CHECK (status IN ('fechado','perdido')),
    valor_negocio   NUMERIC(14,2) NOT NULL,
    perc_comissao   NUMERIC(5,2) NOT NULL,
    valor_comissao  NUMERIC(14,2) NOT NULL,
    motivo_perda    TEXT
);
COMMENT ON TABLE  curated.fato_negocios IS 'Negócios (ganhos ou perdidos): último estágio do funil.';
COMMENT ON COLUMN curated.fato_negocios.negocio_id      IS 'Identificador do negócio.';
COMMENT ON COLUMN curated.fato_negocios.lead_id         IS 'Lead de origem.';
COMMENT ON COLUMN curated.fato_negocios.imovel_id       IS 'Imóvel negociado.';
COMMENT ON COLUMN curated.fato_negocios.corretor_id     IS 'Corretor responsável.';
COMMENT ON COLUMN curated.fato_negocios.finalidade      IS 'Venda ou locacao.';
COMMENT ON COLUMN curated.fato_negocios.data_abertura   IS 'Data de abertura do negócio.';
COMMENT ON COLUMN curated.fato_negocios.data_fechamento IS 'Data de fechamento/perda.';
COMMENT ON COLUMN curated.fato_negocios.status          IS 'fechado ou perdido.';
COMMENT ON COLUMN curated.fato_negocios.valor_negocio   IS 'Valor do negócio em R$ (venda: preço; locacao: 12x aluguel).';
COMMENT ON COLUMN curated.fato_negocios.perc_comissao   IS 'Percentual de comissão aplicado.';
COMMENT ON COLUMN curated.fato_negocios.valor_comissao  IS 'Comissão em R$ (= valor * perc).';
COMMENT ON COLUMN curated.fato_negocios.motivo_perda    IS 'Motivo da perda, quando status = perdido.';

CREATE TABLE curated.metas_mensais (
    meta_id        SERIAL PRIMARY KEY,
    competencia    CHAR(7) NOT NULL,
    equipe_id      SMALLINT NOT NULL REFERENCES curated.dim_equipe(equipe_id),
    corretor_id    SMALLINT REFERENCES curated.dim_corretor(corretor_id),
    meta_negocios  SMALLINT NOT NULL,
    meta_vgv       NUMERIC(14,2) NOT NULL
);
COMMENT ON TABLE  curated.metas_mensais IS 'Metas mensais por equipe (corretor_id nulo = meta da equipe toda).';
COMMENT ON COLUMN curated.metas_mensais.meta_id       IS 'Identificador da meta.';
COMMENT ON COLUMN curated.metas_mensais.competencia   IS 'Competência no formato AAAA-MM.';
COMMENT ON COLUMN curated.metas_mensais.equipe_id     IS 'Equipe da meta.';
COMMENT ON COLUMN curated.metas_mensais.corretor_id   IS 'Corretor (nulo quando a meta é da equipe).';
COMMENT ON COLUMN curated.metas_mensais.meta_negocios IS 'Meta de quantidade de negócios fechados.';
COMMENT ON COLUMN curated.metas_mensais.meta_vgv      IS 'Meta de VGV em R$.';

-- Índices para os filtros do Dashboard (período, cidade, finalidade, tipo, origem, corretor).
CREATE INDEX idx_leads_data        ON curated.fato_leads(data);
CREATE INDEX idx_leads_origem      ON curated.fato_leads(origem_id);
CREATE INDEX idx_leads_cidade      ON curated.fato_leads(cidade_id);
CREATE INDEX idx_leads_corretor    ON curated.fato_leads(corretor_id);
CREATE INDEX idx_visitas_data      ON curated.fato_visitas(data);
CREATE INDEX idx_propostas_data    ON curated.fato_propostas(data);
CREATE INDEX idx_negocios_fech     ON curated.fato_negocios(data_fechamento);
CREATE INDEX idx_negocios_corretor ON curated.fato_negocios(corretor_id);
CREATE INDEX idx_imoveis_bairro    ON curated.imoveis(bairro_id);
