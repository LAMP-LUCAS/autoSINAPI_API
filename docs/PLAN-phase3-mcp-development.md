# PLAN: Fase 3.1 — desenvolvimento MCP do AutoSINAPI

> Dono: autosinapi_api. Revisão 2026-09-17. Desenvolvimento e validação pendentes; este guia não trata de implantação.

## Escopo DDD e contratos

O produto é dono do catálogo SINAPI, schemas e adaptação de operações para tools. Reutilizar os casos de uso existentes, sem duplicar cálculos no adaptador. Autoridade comercial: **`saas-gateway/MCP-Admission v1`**, entregável proposto pelo gateway, ainda sujeito a publicação e aprovação. Consumir por nome/versão, sem copiar sua especificação.

Entregável deste produto: **`autosinapi/MCP-Catalog v1`** (proposto). Publicar aqui a definição única do catálogo, schemas, erros, versão MCP negociada, transporte, path, health, configurações suportadas e compatibilidade com o contrato de admissão. Portas e endereços de ambiente não pertencem ao contrato funcional.

## Base e trabalho de desenvolvimento

A contagem de tools citada em revisões anteriores (19 ou 20) não é confiável e não deve ser tratada como contrato. Isso não significa que as ferramentas registradas estejam autorizadas, testadas ou prontas para release. Reconciliar o registro real e a descoberta de tools com o OpenAPI da revisão selecionada; nenhuma quantidade fixa é afirmada.

1. Incorporar o adaptador ao ciclo de desenvolvimento e release deste produto; manter separação entre transporte, aplicação, cliente HTTP e cache. Nenhuma dependência de arquivos externos ao produto.
2. Mapear cada tool ao operationId, método, path e schemas do OpenAPI vigente. Manter busca, preços e BI na autoridade já existente; excluir administração e ETL da superfície pública.
3. Autenticar o caller em cada chamada e consumir a admissão confiável do gateway antes da execução. Sem credencial privilegiada compartilhada de fallback; sem caller válido ou com dependência de autorização indisponível, negar.
4. Não inferir `mcp_access` de header fornecido pelo cliente nem de URL REST. A admissão deve vincular contexto MCP confiável ao caller, tenant e tool conforme `MCP-Admission v1`.
5. Autorizar antes de retornar cache hit; particionar por tenant, escopo, operação e argumentos canônicos, sem armazenar chave secreta bruta. Aplicar revogação e mudança de plano conforme contrato do gateway.
6. Definir timeouts, cancelamento e limites de payload; retry e fan-out obedecem à contabilização do gateway. Não retornar erro de autenticação como sucesso em cache.
7. Confirmar protocolo e lifecycle do SDK da versão selecionada. Nome de path não determina transporte; health HTTP não equivale à negociação MCP.

## Testes e aceite do release

- [ ] Registro e descoberta reconciliados com os schemas publicados; sem quantidade fixa assumida.
- [ ] Testes de contrato OpenAPI e MCP para operações aprovadas, parâmetros inválidos e erros de upstream.
- [ ] Caller ausente, inválido, expirado, revogado ou sem admissão negado; contexto MCP não pode ser autodeclarado pelo cliente.
- [ ] Cache frio/quente, tenants distintos e mudança de plano testados; autorização sempre antecede leitura útil de cache.
- [ ] Falha do gateway nega execução; nenhum fallback privilegiado.
- [ ] Negociação, sessão, cancelamento e transporte testados em ambiente controlado.
- [ ] Release inclui catálogo e configuração versionados, compatibilidade e relatório de testes. Contagem de tools ou imagem construída não comprova prontidão.

Referências locais: [arquitetura](architecture.md), [documentação do core](README.md). Nenhum teste de implementação ou runtime foi executado nesta revisão documental.
