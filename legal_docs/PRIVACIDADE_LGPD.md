> ⚠️ **DRAFT — PENDENTE DE REVISÃO JURÍDICA.** Este documento é um rascunho gerado
> para fechar a lacuna de conformidade LGPD. Os campos `[...]` ou variáveis `{{ company.* }}`
> devem ser conferidos com profissional jurídico antes da publicação.

---
id: legal-privacidade-lgpd
type: legal
status: draft
date: 2026-07-23
tags: [legal, lgpd, privacidade, compliance, anti-fraud]
links:
  - "[[stories/STORY-LEGAL-01]]"
  - "[[adrs/017-legal-compliance-anti-fraud-policy]]"
---

# Política de Privacidade — AutoSINAPI (LGPD)

**Última atualização:** {{ company.update_date }}

## 1. Identidade do Controlador
- **Razão Social:** {{ company.legal_name }}
- **CNPJ:** {{ company.number_id }}
- **Endereço:** {{ company.address }}, CEP {{ company.postal }}
- **E-mail de Contato:** {{ company.billing_email }}
- **Encarregado de Dados (DPO):** {{ company.dpo_email }}

## 2. Âmbito
Esta Política descreve como o AutoSINAPI ("Plataforma", "nós"), operado por {{ company.legal_name }}, coleta, utiliza, armazena e protege os dados pessoais dos usuários ("Titular"), em conformidade com a Lei nº 13.709/2018 (Lei Geral de Proteção de Dados - LGPD).

## 3. Dados Pessoais Coletados
- **Identificação e Cadastro:** Nome, e-mail, empresa, CPF ou CNPJ (coletados para faturamento e identificação unívoca).
- **Dados de Conta e Assinatura:** Plano contratado, status da assinatura, chaves de API (armazenadas com hash em repouso).
- **Dados de Uso e Comportamentais:** Logs de requisições à API (timestamp, endpoint, IP, user-agent, quota consumida) tratados para segurança e prevenção a fraudes (*scraping*).
- **Dados de Pagamento:** Processados de forma segura pelo Mercado Pago (não armazenamos dados completos de cartão de crédito).

## 4. Bases Legais, Finalidades e Retenção (LGPD Art. 7º)
| Categoria de Dado | Base Legal (LGPD) | Finalidade do Tratamento | Prazo de Retenção |
|-------------------|-------------------|--------------------------|-------------------|
| Nome, e-mail, CPF/CNPJ | Art. 7º, V (Execução de contrato) e II (Obrigação legal/fiscal) | Provisionar conta, validar KYC e faturamento | Vigência do contrato + 5 anos (obrigação fiscal) |
| E-mail (validação anti-fraude) | Art. 7º, IX (Legítimo interesse) | Bloqueio de domínios descartáveis e prevenção a abuso de contas | Durante o processo de cadastro |
| Logs de IP, API & Usage | Art. 7º, IX (Legítimo interesse) | Segurança da API, rate limiting, mitigação de *scraping* e auditoria probatória | 12 meses |
| Dados de Pagamento | Art. 7º, V (Execução de contrato) | Processamento de recorrência via Mercado Pago | Conforme políticas do gateway |

## 5. Compartilhamento com Terceiros
- **Mercado Pago:** Processamento de pagamentos e assinaturas.
- **Hostinger (SMTP):** Envio de e-mails transacionais e alertas de cota.
- **Caixa Econômica Federal:** Fonte pública dos dados SINAPI (não há compartilhamento de dados pessoais de usuários com a Caixa).
Não comercializamos nem repassamos dados pessoais a terceiros para fins de marketing.

## 6. Segurança e Armazenamento
Adotamos medidas técnicas e administrativas robustas, incluindo criptografia em trânsito (TLS 1.3), chaves de API hasheadas, isolamento de rede via Docker e controles de acesso por tier.

## 7. Direitos do Titular (LGPD Art. 18)
O Titular pode exercer seus direitos de confirmação, acesso, correção, anonimização, portabilidade ou eliminação de dados enviando uma solicitação ao nosso DPO através do e-mail **{{ company.dpo_email }}**.

## 8. Alterações nesta Política
Atualizações futuras serão publicadas nesta página com a respectiva data de revisão.
