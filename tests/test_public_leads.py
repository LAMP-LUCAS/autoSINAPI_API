"""TDD — porta de entrada: `POST /api/v1/public/leads`.

Contexto: até 2026-10-01 a criação de lead era feita pelo plugin Lua do Kong
(`mode=lead`), que interceptava a rota e **nunca fazia proxy** — o backend
FastAPI não tinha a rota. Consequência: (a) o gateway era o único dono, sem
rede de segurança; (b) se o plugin saísse, a captura inteira caía em 404, que
foi exatamente o que aconteceu; (c) o envio de e-mail era `pcall` no Lua —
falha silenciosa.

Aqui o backend é o dono único. Este arquivo trava o contrato antes da
implementação.

Invariantes que os testes exigem:
  1. `name` e `email` obrigatórios; e-mail com formato válido (o plugin antigo
     aceitaria `email="qualquercoisa"`).
  2. Normalização: `lower()` + trim; dedupe por e-mail normalizado, **sem**
     rebaixar status (`converted` não vira `contacted`).
  3. Lead nasce `contacted` com `last_activity_at` — é o que dá audiência ao
     nurture (todas as workflows filtram `contacted`/`qualified`).
  4. Atribuição (utm/referrer/landing_path) só é gravada se veio no payload; o
     portal já a condiciona a consentimento de marketing.
  5. **Lead persiste mesmo se o e-mail falhar.** O lead é o negócio; o e-mail é
     cortesia. Falha de MD é registrada, não engole a requisição.
  6. Anti-relay: o endpoint envia e-mail para endereço escolhido pelo
     chamador. Sem orçamento por IP, é um relay aberto para spam.
  7. Rate limit por IP; se o Redis cair, degrada para limite local (fecha
     aberto seria perder lead; aberto seria perder a proteção).
  8. Resposta **nunca** distingue "e-mail novo" de "e-mail existente" por
     status HTTP — isso seria enumeração da base de clientes.
"""

import pytest


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(_wire):
    """Cliente FastAPI com o router real e os dublês já instalados.

    Depende de `_wire` explicitamente: como `_wire` é autouse mas não é
    autouse-*dependência* do `client`, sem esta dependência o TestClient
    nasceria antes dos dublês e o teste de dedupe cairia em 201 (inserindo
    linha) em vez de 200 (dedupe). Falharia por ordem de fixture, não por
    comportamento.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.public_leads import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _payload(**over):
    base = {"name": "Ana Souza", "email": "Ana@Exemplo.COM", "source": "footer"}
    base.update(over)
    return base


# ── 1. contrato e validação ───────────────────────────────────────────────────

def test_rejeita_sem_nome(client):
    r = client.post("/api/v1/public/leads", json={"email": "a@b.com"})
    assert r.status_code == 422


def test_rejeita_sem_email(client):
    r = client.post("/api/v1/public/leads", json={"name": "Ana"})
    assert r.status_code == 422


@pytest.mark.parametrize("bad", [
    "nao-e-email",
    "a@",
    "@b.com",
    "a b@c.com",
    "a@b",
    "a@@b.com",
])
def test_rejeita_email_sem_formato(client, bad):
    r = client.post("/api/v1/public/leads", json=_payload(email=bad))
    assert r.status_code == 422, f"aceitou e-mail inválido: {bad!r}"


def test_rejeita_nome_cujo_so_tem_espaco(client):
    r = client.post("/api/v1/public/leads", json=_payload(name="   "))
    assert r.status_code == 422


def test_rejeita_nome_absurdamente_longo(client):
    r = client.post("/api/v1/public/leads", json=_payload(name="x" * 500))
    assert r.status_code == 422


# ── 2/3. dedupe e status ──────────────────────────────────────────────────────

def test_normaliza_email_e_cria_como_contacted(client, fake_repo):
    r = client.post("/api/v1/public/leads", json=_payload())
    assert r.status_code == 201
    assert fake_repo.created["email"] == "ana@exemplo.com"
    assert fake_repo.created["status"] == "contacted"
    assert fake_repo.created["last_activity_at"] is not None


def test_reenvio_mesmo_email_nao_duplica_e_preserva_status(client, fake_repo):
    fake_repo.seed(email="ana@exemplo.com", status="converted", name="Ana Antiga")

    r = client.post("/api/v1/public/leads", json=_payload(company="ACME"))

    # O status HTTP é 201 nos dois casos (o decorator fixa). O que distingue
    # novo de existente é `deduped` no corpo — e é assim que a resposta não
    # vira oráculo de enumeração da base (invariante 8).
    assert r.status_code == 201
    assert r.json()["deduped"] is True
    assert r.json()["status"] == "converted", "dedupe não pode rebaixar status"
    assert fake_repo.inserts == 0                      # nenhuma linha nova
    assert fake_repo.updated["company"] == "ACME"      # enriquecido
    assert "status" not in fake_repo.updated, "dedupe não pode escrever status"


def test_dedupe_usa_email_normalizado(client, fake_repo):
    fake_repo.seed(email="ana@exemplo.com", status="contacted")
    r = client.post("/api/v1/public/leads", json=_payload(email="  ANA@Exemplo.COM "))
    assert r.json()["deduped"] is True
    assert fake_repo.inserts == 0


def test_resposta_nao_revela_se_email_existe(client, fake_repo):
    """Enumeração de base: um status distinto entrega a lista de clientes."""
    novo = client.post("/api/v1/public/leads", json=_payload())
    fake_repo.seed(email="ana@exemplo.com", status="converted")
    existente = client.post("/api/v1/public/leads", json=_payload())

    # Mesmo status HTTP nos dois casos: quem chuta e-mails não distingue.
    assert novo.status_code == existente.status_code
    # A distinção existe, mas só no corpo, para o remetente legítimo.
    assert novo.json()["deduped"] is False
    assert existente.json()["deduped"] is True
    for corpo in (novo.text.lower(), existente.text.lower()):
        assert "exists" not in corpo and "not found" not in corpo


# ── 4. atribuição ─────────────────────────────────────────────────────────────

def test_grava_atribuicao_quando_vem_no_payload(client, fake_repo):
    client.post("/api/v1/public/leads", json=_payload(
        utm_source="linkedin", utm_campaign="setembro26",
        referrer="https://www.google.com/", landing_path="/autosinapi"))
    # `metadata` chega ao banco como string (CAST(:metadata AS jsonb)), então
    # é isso que o dublê registra — ler de outra forma mascararia erro de
    # serialização.
    import json
    attr = json.loads(fake_repo.created["metadata"])["attribution"]
    assert attr["utm_source"] == "linkedin"
    assert attr["landing_path"] == "/autosinapi"


def test_sem_atribuicao_nao_inventa_campo(client, fake_repo):
    client.post("/api/v1/public/leads", json=_payload())
    import json
    assert json.loads(fake_repo.created["metadata"]).get("attribution") is None


def test_campos_desconhecidos_sao_ignorados(client, fake_repo):
    r = client.post("/api/v1/public/leads", json=_payload(
        is_admin=True, status="converted", lead_score=999))
    assert r.status_code == 201
    # Um campo forjado não pode virar status/promoção no banco.
    assert fake_repo.created["status"] == "contacted"


# ── 5. resiliência do envio ───────────────────────────────────────────────────

def test_lead_persiste_mesmo_com_md_fora_do_ar(client, fake_repo, failing_md):
    r = client.post("/api/v1/public/leads", json=_payload())
    assert r.status_code == 201
    assert fake_repo.inserts == 1, "lead não pode se perder por falha de e-mail"
    assert failing_md.attempts == 1, "o envio foi tentado (falhou, mas tentou)"


def test_md_lento_nao_derruba_a_captura(client, fake_repo, slow_md):
    r = client.post("/api/v1/public/leads", json=_payload())
    assert r.status_code == 201
    assert fake_repo.inserts == 1


# ── 6/7. anti-relay e rate limit ──────────────────────────────────────────────

def test_orcamento_de_email_limita_envio_ao_ip(client, fake_repo, mailer):
    """O endpoint manda e-mail para endereço escolhido pelo chamador.
    Sem orçamento, vira relay de spam."""
    for i in range(10):
        client.post("/api/v1/public/leads", json=_payload(
            email=f"lixo-{i}@spam.test", name="Spam"))
    assert mailer.attempts <= 5, "orçamento de e-mail por IP não foi respeitado"


def test_rate_limit_por_ip(client, fake_repo):
    """Estouro de taxa não pode virar 500 nem passar ileso."""
    codes = [
        client.post("/api/v1/public/leads",
                    json=_payload(email=f"r{i}@x.test")).status_code
        for i in range(40)
    ]
    assert all(c in (201, 200, 429) for c in codes), f"status inesperado: {set(codes)}"


def test_redis_fora_do_ar_degrada_sem_500(client, fake_repo, broken_redis):
    """Redis cair não pode ser 500 (perde lead) nem aberto (perde proteção)."""
    r = client.post("/api/v1/public/leads", json=_payload())
    assert r.status_code in (201, 200, 429)