> ⚠️ **DRAFT — PENDENTE DE REVISÃO JURÍDICA.** Campos `[...]` a preencher com dados
> reais da empresa; rever com profissional jurídico antes da publicação.

---
id: legal-tos
type: legal
status: draft
date: 2026-07-23
tags: [legal, tos, termos, anti-scraping, cdc]
links:
  - "[[stories/STORY-LEGAL-01]]"
  - "[[adrs/017-legal-compliance-anti-fraud-policy]]"
---

# Termos de Uso — AutoSINAPI

**Última atualização:** {{ company.update_date }}

## 1. Aceitação e Execução Imediata
Ao acessar ou contratar o AutoSINAPI ("Serviço"), o Assinante concorda com estes Termos e reconhece expressamente que, por se tratar de serviço digital com entrega e liberação instantânea de credenciais de acesso (chave de API), **o contrato inicia sua execução imediatamente após a confirmação do pagamento e o primeiro acesso efetivo**, aplicando-se as regras de consumo imediato e renúncia ao direito de arrependimento (Art. 49 do CDC) após o uso inicial. A {{ company.legal_name }} (CNPJ: {{ company.number_id }}) pode atualizar estes Termos periodicamente.

## 2. Objeto
O Serviço disponibiliza, mediante assinatura, acesso programático (API) e portal de consulta a dados de referência de custos da construção civil (SINAPI/Caixa).

## 3. Elegibilidade e Cadastro (KYC)
O Assinante declara ter capacidade jurídica plena e, se pessoa jurídica, poderes de representação. Para fins de segurança, prevenção a fraudes e cumprimento de obrigação legal (Art. 7º, V, LGPD), o cadastro exige CPF ou CNPJ válido e verificação de e-mail ativo. E-mails temporários ou descartáveis são bloqueados pelo sistema.

## 4. Contas e Credenciais
O acesso é autenticado por chave de API (`X-API-KEY`). O Assinante é responsável por manter a confidencialidade da chave, sendo vedado o compartilhamento de credenciais.

## 5. Tabela de Direitos e Deveres por Plano

| **Plano** | **Free** | **Starter** | **Pro** | **Business** |
| :--- | :--- | :--- | :--- | :--- |
| **Rate Limit & Burst** | Conforme SSOT (`plans.yaml`) | Conforme SSOT (`plans.yaml`) | Conforme SSOT (`plans.yaml`) | Conforme SSOT (`plans.yaml`) |
| **Trial de 7 dias** | N/A | N/A | **Sim** (para planos ≥ 30d) | **Sim** (para planos ≥ 30d) |
| **Direito de Arrependimento** | N/A | **Não aplicável** após início do consumo efetivo | **Não aplicável** após início do consumo efetivo | **Não aplicável** após início do consumo efetivo |
| **Uso Permitido** | Avaliação e testes (Rate limit restrito) | Uso profissional e comercial integrado | Uso profissional e comercial integrado | Uso empresarial em larga escala |
| **Proibições Expressas** | **Proibido** *scraping*, mineração massiva, *mirroring* ou treinamento de IA | **Proibido** *scraping*, mineração massiva, *mirroring* ou treinamento de IA | **Proibido** *scraping*, mineração massiva, *mirroring* ou treinamento de IA | **Proibido** *scraping*, mineração massiva, *mirroring* ou treinamento de IA |

## 6. Proibição Expressa de Scraping e Mineração de Dados
É **expressamente proibido** realizar *scraping*, mineração de dados em massa, engenharia reversa, *mirroring* ou qualquer forma de coleta automatizada com o objetivo de replicar a base de dados do SINAPI, criar datasets concorrentes ou treinar modelos de inteligência artificial. A violação gera suspensão imediata e permanente da chave de API, sem direito a reembolso e sem prejuízo de medidas judiciais por perdas e danos.

## 7. Limites de Taxa (Rate Limit) e Proteção contra Picos
O consumo é controlado por chave e IP com suporte a rajadas (*burst*) e limites específicos por endpoint (conforme SSOT em `plans.yaml`). Excedentes resultam em bloqueio temporário (HTTP 429).

## 8. Cancelamento e Reembolso
O cancelamento da assinatura pode ser solicitado a qualquer momento pelo portal do usuário. Conforme a Política de Reembolso, iniciada a utilização efetiva da API, não há reembolso proporcional dos dias não utilizados devido à natureza de entrega e consumo imediato do serviço digital.

## 9. Propriedade de Dados
Os dados SINAPI pertencem à Caixa Econômica Federal; o Serviço atua como ferramenta de consulta e processamento. O código e infraestrutura do AutoSINAPI pertencem à {{ company.legal_name }}.

## 10. Limitação de Responsabilidade
O Serviço é fornecido "no estado em que se encontra". A {{ company.legal_name }} não garante disponibilidade ininterrupta nem a exatidão absoluta de dados fornecidos por terceiros (SINAPI/Caixa).

## 11. Foro e Legislação
Fica eleito o foro da comarca de {{ company.city }}, {{ company.state }}, Brasil. Dúvidas e solicitações ao DPO: {{ company.dpo_email }}.
