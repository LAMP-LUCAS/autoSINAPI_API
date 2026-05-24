# 🗺️ autoSINAPI ROADMAP — Visão de Evolução Técnica

Este documento define os próximos horizontes técnicos para o projeto **autoSINAPI**, mantendo o compromisso com a filosofia Open Source (GPL-v3) e a capacidade de auto-hospedagem (self-hosting). O objetivo é evoluir de uma ferramenta de consulta para uma plataforma de inteligência em custos de construção.

---

## 🏗️ Fase 2: Automação e Inteligência de Dados

### 1. Zero-Touch ETL (Carga Autônoma)
Atualmente, o processo de população do banco depende de intervenção manual.
- [ ] **Monitoramento Ativo:** Implementar um crawler (Agente Watcher) que monitora o portal de downloads da Caixa Econômica Federal.
- [ ] **Carga Automatizada:** Ao detectar um novo arquivo, disparar o pipeline de extração e inserção via Celery de forma totalmente automática.
- [ ] **Webhooks de Status:** Notificar o administrador via Webhook (Discord/Telegram/Email) sobre o sucesso ou falha da atualização mensal.

### 2. Forecasting com IA (Análise Preditiva)
Aproveitar a massa de dados histórica sanitizada para gerar valor prospectivo.
- [ ] **Integração LLM/Ollama:** Utilizar agentes de IA locais para analisar séries históricas e identificar anomalias ou sazonalidade.
- [ ] **Previsão de Preços:** Implementar modelos de regressão para projetar a variação de preços (Inflação Setorial) para os próximos 3 a 6 meses.
- [ ] **Dashboard de Risco:** Alertas sobre materiais com tendência de alta acentuada, auxiliando na antecipação de compras.

---

## 🔗 Fase 3: Ecossistema e Integrações

### 3. Integração BIM 5D & Plugins
Conectar a API diretamente ao fluxo de projeto.
- [ ] **API Headless para BIM:** Expandir endpoints para facilitar o mapeamento de objetos BIM com códigos SINAPI.
- [ ] **Plugin Revit/AutoCAD:** Protótipo de integração para leitura de custos em tempo real dentro de ferramentas de projeto.
- [ ] **Exportação para ERPs:** Formatos de saída compatíveis com sistemas de gestão de obras open source.

### 4. Custom Personal Databases (Multi-tenancy Técnico)
Permitir que o usuário combine dados oficiais com seus próprios custos.
- [ ] **Composições Próprias:** Criar endpoints `POST` para que usuários cadastrem tabelas de custos locais sem sobrescrever os dados oficiais do SINAPI.
- [ ] **Mix de Preços:** Funcionalidade para calcular orçamentos usando o "SINAPI Oficial" como base, mas substituindo itens específicos por cotações de mercado do usuário.

---

## 🛠️ Fase 4: Excelência Operacional e UX

- [ ] **API v2 (GraphQL):** Implementar suporte a GraphQL para permitir consultas complexas e explosões de BOM em uma única requisição customizada.
- [ ] **Dashboard Pro (Open Source):** Evoluir a interface Demo para um dashboard de gestão completo, com persistência de orçamentos no navegador (LocalStorage/IndexedDB).
- [ ] **Internationalization (i18n):** Preparar a interface para suporte a múltiplos idiomas e moedas, expandindo o uso para outros países que utilizam tabelas de referência similares.

---

**Nota:** Este roteiro é uma declaração de intenções técnica. Com a nova arquitetura modular:
- A **Fase 2 (Inteligência de Dados e ETL)** será desenvolvida prioritariamente no repositório [AutoSINAPI (Toolkit)](https://github.com/LAMP-LUCAS/AutoSINAPI).
- As **Fases 3 e 4 (Integrações e UX)** serão o foco deste repositório da API.

Contribuições da comunidade são bem-vindas via Pull Requests seguindo a licença GPL-v3.
