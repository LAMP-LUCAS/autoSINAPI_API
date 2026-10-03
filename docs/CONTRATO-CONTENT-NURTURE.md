# Contrato do conteúdo de nurture — slot, template e variáveis

> **SSOT de copy:** `saas-gateway/emails/registry.yaml` + `emails/bodies/*.liquid`
> **Produtor:** `api/crm_conteudo.py` (`POST /api/v1/admin/crm/conteudo/decidir`)
> **Contrato verificado por:** `tests/test_crm_envelope_slot.py` (este repo) e
> `saas-gateway/tests/test_email_funnel_slots.py` (produtor × registry)
> **Última revisão:** 2026-10-03

Este documento existe porque o contrato **não é óbvio pelo código**. O
produtor monta um payload para o MessageDispatcher renderizar num template que
vive em outro repositório; quando os dois lados divergem, nada quebra — o
e-mail sai com o conteúdo descartado e um link morto, e o sintoma só aparece na
caixa do destinatário.

---

## 1. Slots

O conjunto é **fechado**: `enriquecimento | artigo | winback | promo`
(vêm de `grade.Slot.tipo`). Um slot novo precisa entrar em `SLOTS` nos dois
testes de contrato — de propósito, para falhar.

| Slot | Template (registry) | `template_id` | Tópico MD | Cadência |
|---|---|---|---|---|
| `enriquecimento` | `gateway_report_weekly` | `f5555555-…-555555555555` | `gateway.report_weekly` | semanal (3ª-feira) |
| `artigo` | `gateway_kb_digest` | `f4444444-…-444444444444` | `gateway.kb_digest` | semanal (5ª-feira) |
| `winback` | `gateway_reengagement` | `aaaaaaaa-…-aaaaaaaaaaaa` | `gateway.reengagement` | 30/45 dias sem consumo (4ª) |
| `promo` | `gateway_promo_weekly` | `99999999-…-999999999999` | `gateway.update_incc` | 2ª e 6ª |

`gateway_lead_welcome` (`66666666…`) **não pertence a este mapa**: é
exclusivo da captação (`api/public_leads.py`). `gateway_winback`
(`f3333333…`) está no registry mas não é produzido por ninguém.

**O slot escolhe o template — nunca o tipo do objeto.** `_template_do_slot`
levanta `ValueError` em slot desconhecido, o que faz `/decidir` responder 500
sem enviar nada. Errar em silêncio seria enviar o e-mail errado.

## 2. Variáveis

O `vars` do produtor tem que ser **igual** às `variables` do registry — nem
faltando, nem sobrando. Falta quebra o render (o `{{ x }}` fica vazio);
sobra esconde deriva (o registro/documentação deixa de descrever o que é
enviado).

| Slot | Variáveis |
|---|---|
| `enriquecimento` | `lead_name`, `titulo`, `resumo`, `texto`, `nota`, `metricas`, `grafico_svg`, `serie_rotulo`, `rodape`, `link_relatorio`, `tools_url` |
| `artigo` | `lead_name`, `article_title`, `article_description`, `article_url`, `tools_url` |
| `winback` | `lead_name`, `desconto`, `cupom`, `portal_url`, `agenda_url` |
| `promo` | `lead_name`, `competencia`, `destaque`, `portal_url`, `tools_url` |

Duas regras que valem para todos:

- **`metricas` é a fonte da verdade numérica.** `gateway_report_weekly` monta
  a tabela com `{% for m in metricas %}`, e o `grafico_svg` é uma variável com
  o SVG já pronto. O gráfico é o que o Gmail/Outlook removem; a tabela é o que
  sobrevive. Layout e copy ficam editáveis no `.liquid`; a geometria vem do
  dado.
- **`unsubscribe_url` não entra.** O link de preferências é do rodapé
  compartilhado que o `EmailSmtpAdapter` aplica a todo e-mail, com URL assinada
  por destinatário (`SendOS#unsubscribe_url_for`). Nenhum template o declara e
  nenhum produtor o envia.

## 3. Links

`api/links.py` é a SSOT **em runtime**; o bloco `links:` do registry é a
declaração. `saas-gateway/tests/test_producer_contract.py` compara os dois.

```
portal_url  https://mundoaec.com
tools_url   https://mundoaec.com/tools
agenda_url  https://mundoaec.com/contato
```

O módulo existe porque a mesma classe de defeito apareceu duas vezes, sempre no
produtor que ninguém fiscalizava: `TOOLS_URL` valia `…/ferramentas` (404)
enquanto o registry dizia `…/tools` (200), e `public_leads` repetiu o literal
— com o mesmo path errado — no **primeiro** e-mail que um lead recebe.

### 3.1 `link_relatorio` — o CTA que era 404 em 9 de 9

O relatório **não tem página**: ele é o e-mail. O CTA levava a
`https://mundoaec.com/kb/{rel.chave}`, mas `rel.chave` identifica o
*relatório* (`incc_leitura_mes`, `sinapi_competencia`, `cub_dispersao`…) e não
é slug de KB — `/kb/` só aceita os 109 artigos do catálogo. As 9 chaves da
trilha davam **404**.

O destino é a ferramenta do índice que o relatório mede:

| Prefixo da chave | Destino |
|---|---|
| `incc_` | `https://mundoaec.com/tools/incc` |
| `cub_` | `https://mundoaec.com/tools/cub` |
| `sinapi_` | `https://mundoaec.com/app/sinapi` |
| (qualquer outro) | `https://mundoaec.com/tools` |

Os quatro foram verificados com HTTP 200 em 03/10. O gate de URL do gateway
**não alcança** valores calculados em Python — por isso `test_emails_urls.py`
checou que `catalogo[].url == f"https://mundoaec.com/kb/{slug}/"` e
`test_email_funnel_slots.py` faz o HEAD ao vivo no que o produtor monta.

## 4. Cadência e frequência

| Regra | Onde |
|---|---|
| Teto semanal por segmento — `{"novo":1,"madura":2,"cliente":2}` | `_estado()` |
| Intervalo mínimo entre slots | `_estado()` |
| Win-back em 30/45 dias **sem consumo**, na 4ª | `grade.py` |
| Promoção só para assinantes pagantes, no máximo a cada 15 dias, 2ª ou 6ª | `grade.py` |
| Passo único — `UNIQUE (lead_id, step)` | `_reservar()` + `ON CONFLICT` |

> **Limitação conhecida e medida (03/10):** `SQL_CONSUMO_APP` e
> `SQL_CONSUMO_PORTAL` são **idênticas** (mesmo sha1) porque **não existe
> evento de login** — `leads.last_activity_at` só é movido pela ponte de
> envio de formulário e por ação manual. Nos 32 leads reais a cascata diverge
> do `min(api, portal)` antigo em **zero** casos: é um no-op até o app emitir
> sinal próprio.
>
> O degrau de 45 dias **é** alcançável — `now() - created_at` cresce todo dia.
> Uma versão anterior deste documento afirmava o contrário; a medição refutou.

## 5. Como o contrato é detido

| Gate | O que trava |
|---|---|
| `tests/test_crm_envelope_slot.py` | template/topic/vars por slot; `Relatorio` disfarçado de `dict` não pode cair no ramo do artigo |
| `saas-gateway/tests/test_email_funnel_slots.py` | produtor × registry, `href` sem variável no payload, tabela + SVG presentes |
| `saas-gateway/emails/lint_emails.py` | variável declarada não usada / usada não declarada; render do Liquid |
| `rake emails:lint` (MD) | o mesmo, com o Liquid real do Ruby |
| `saas-gateway/tests/test_emails_registry.py` | o link de preferências não volta para nenhum body |

## 6. Defeitos que este contrato já pegou

| Data | Sintoma | Causa | Pego por |
|---|---|---|---|
| 2026-10-03 | **o artigo não era enviado** — conteúdo descartado, href `/app/sinapi` relativo | slot `artigo` ia para `gateway_lead_welcome`, que declara `lead_name, portal_url, tools_url` | `test_email_funnel_slots.py` (RED antes da correção) |
| 2026-10-03 | relatório saía como "digest de artigo", sem número nenhum | relatório e artigo dividiam o mesmo template | idem |
| 2026-10-03 | CTA "Abrir a análise completa" 404 em 9 de 9 | `rel.chave` não é slug de KB | HEAD ao vivo no contrato |
| 2026-10-03 | `/ferramentas` 404 em 2 produtores | literal hardcoded fora da SSOT | `test_producer_contract.py` |
| 2026-10-03 | link de preferências com host errado | cópia estática sem token no produtor | `test_emails_registry.py` (Fase 2) |