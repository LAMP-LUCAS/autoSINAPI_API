> ⚠️ **DRAFT — PENDENTE DE REVISÃO JURÍDICA.** Campos `[...]` a preencher com dados
> reais da empresa; rever com profissional jurídico antes da publicação.

---
id: legal-reembolso
type: legal
status: draft
date: 2026-07-23
tags: [legal, reembolso, cancelamento, mercadopago, cdc]
links:
  - "[[stories/STORY-LEGAL-01]]"
  - "[[adrs/017-legal-compliance-anti-fraud-policy]]"
---

# Política de Reembolso e Cancelamento — AutoSINAPI

**Última atualização:** {{ company.update_date }}

## 1. Âmbito
Esta política aplica-se a todas as assinaturas do AutoSINAPI contratadas por meio da plataforma de pagamento integrada (Mercado Pago).

## 2. Natureza Digital e Execução Imediata (Art. 49 do CDC)
O AutoSINAPI fornece acesso programático (API) a bases de dados de engenharia civil de entrega e consumo instantâneos.
- **Início do Consumo:** No momento da confirmação do pagamento, a chave de API é gerada e disponibilizada. O primeiro acesso bem-sucedido caracteriza a **prestação e o consumo efetivo do serviço**.
- **Exceção ao Direito de Arrependimento:** Conforme a jurisprudência consolidada para serviços digitais de execução imediata, uma vez iniciado o consumo efetivo da API, **o direito de arrependimento de 7 dias previsto no art. 49 do CDC não se aplica**, pois o conteúdo e a infraestrutura foram integralmente disponibilizados e consumidos.
- **Trial Gratuito:** Para mitigar qualquer barreira de avaliação, os planos com vigência igual ou superior a 30 dias oferecem **7 dias de trial gratuito** (com validação de cartão). O usuário tem a oportunidade completa de testar a ferramenta sem cobrança prévia, esvaziando a necessidade de reembolso posterior.

## 3. Cancelamento da Assinatura
O Assinante pode cancelar a renovação automática da assinatura a qualquer momento através do seu painel no portal do usuário ou diretamente no Mercado Pago.
- O acesso à API permanece ativo até o término do período já pago.
- Não há reembolso proporcional para dias ou requisições não utilizadas em ciclos de faturamento em curso, uma vez que a capacidade computacional foi alocada e o serviço digital foi disponibilizado para consumo imediato.

## 4. Estornos pelo Gateway (Mercado Pago)
Quando aplicável (por exemplo, cancelamentos dentro do período de trial antes da efetivação da cobrança), o estorno é processado **exclusivamente pelo Mercado Pago** no meio de pagamento original. A {{ company.legal_name }} não efetua estornos em dinheiro ou por canais externos ao gateway.

## 5. Indisponibilidade e Suporte Técnico
Em caso de falhas sistêmicas prolongadas comprovadamente atribuíveis aos servidores da {{ company.legal_name }} e fora dos parâmetros de SLA contratados, a empresa poderá avaliar concessão de créditos de API ou estorno proporcional, de forma discricionária e mediante abertura de chamado com evidências técnicas.

## 6. Contato e DPO
Dúvidas sobre pagamentos e cancelamentos devem ser encaminhadas para {{ company.billing_email }} ou ao DPO em {{ company.dpo_email }}.
