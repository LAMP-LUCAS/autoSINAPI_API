"""Fixtures do contrato de captura de lead (`test_public_leads.py`).

O router `api.public_leads` recebe **injetáveis** (repositório, despachante de
e-mail, limitador) justamente para que o teste possa exercitar falha de MD,
Redis fora do ar e estouro de orçamento sem monkeypatch do módulo inteiro.

Nenhuma fixture toca banco, Redis ou rede: o teste da porta de entrada precisa
rodar em qualquer máquina, inclusive sem Docker.
"""

import time
from collections import defaultdict

import pytest


class FakeRepo:
    """Repositório de leads em memória.

    Guarda o que foi gravado para o teste afirmar sobre a escrita — é isso que
    separa "respondeu 201" de "gravo mesmo".
    """

    def __init__(self):
        self.rows = {}
        self.inserts = 0
        self.created = {}
        self.updated = {}
        self.mail_attempts = 0

    def seed(self, email, status="contacted", name=""):
        self.rows[email] = {"id": f"id-{email}", "email": email,
                            "status": status, "name": name}

    def find_by_email(self, email):
        """Devolve um dict ou None — o mesmo contrato do `_SqlLeadRepo`.

        O plugin Lua devolvia lista; aqui é dict porque o SQL `LIMIT 1` já
        garante unicidade e o chamador não faz `for` sobre o resultado.
        """
        return self.rows.get(email)

    def insert(self, data):
        self.inserts += 1
        # O status é fixado pela camada de persistência (como no SQL real),
        # nunca pelo payload do chamador. `last_activity_at` é preenchido pelo
        # banco com now() — o dublê registra que o contrato foi cumprido.
        data["status"] = "contacted"
        data["last_activity_at"] = "2026-10-01T00:00:00+00:00"
        data["id"] = "novo-id"
        self.created = data
        self.rows[data["email"]] = data
        return data

    def enrich(self, lead_id, fields):
        """Atualiza só campos enviados — nunca rebaixa status."""
        for row in self.rows.values():
            if row.get("id") == lead_id:
                row.update(fields)
        self.updated.update(fields)
        return True


class FakeMailer:
    """Despachante de e-mail. `fail`/`delay` simulam o MD fora do ar."""

    def __init__(self, fail=False, delay=0.0, budget=3):
        self.fail = fail
        self.delay = delay
        self.budget = budget
        self.attempts = 0

    def send_lead_welcome(self, lead_id, name, email, source=None):
        self.attempts += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("MessageDispatcher indisponível")
        return {"ok": True, "orders_of_service_id": "os-1"}


class MemoryLimiter:
    """Limitador em memória, com janela deslizante.

    Reproduz o comportamento do Redis sem precisar dele — e é também o
    caminho de degradação que o router usa quando o Redis está fora do ar.
    """

    def __init__(self):
        self._hits = defaultdict(list)

    def hit(self, key, limit, window_s):
        now = time.time()
        bucket = self._hits[key]
        bucket[:] = [t for t in bucket if now - t < window_s]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


@pytest.fixture
def fake_repo():
    return FakeRepo()


def _inject_mailer(monkeypatch, mailer):
    """Registra o mailer no router. Cada fixture de mailer se autoinjeta,
    porque `_wire` (autouse) roda antes e não pode escolher por nós."""
    import api.public_leads as pl
    monkeypatch.setattr(pl, "mailer", mailer, raising=False)
    return mailer


@pytest.fixture
def mailer(monkeypatch):
    return _inject_mailer(monkeypatch, FakeMailer())


@pytest.fixture
def failing_md(monkeypatch):
    return _inject_mailer(monkeypatch, FakeMailer(fail=True))


@pytest.fixture
def slow_md(monkeypatch):
    return _inject_mailer(monkeypatch, FakeMailer(delay=0.01))


@pytest.fixture
def limiter():
    return MemoryLimiter()


@pytest.fixture
def broken_redis():
    """Redis indisponível: o limiter_factory levanta e o router degrada."""
    def _boom(*_a, **_k):
        raise ConnectionError("redis fora do ar")
    return _boom


@pytest.fixture(autouse=True)
def _wire(monkeypatch, request, fake_repo):
    """Faz o router usar os dublês antes de cada teste.

    Importa dentro do fixture (e não no topo) porque `api.public_leads` puxa
    `api.config`, que exige `DATABASE_URL` — definido pelo `conftest.py` da
    suíte.

    O **limiter é criado por teste**: um compartilhado carregaria o orçamento do
    teste anterior e o próximo nasceria em 429 — o teste falharia por ordem de
    execução, não por comportamento.

    O **mailer** é o que o teste pediu. `_wire` é autouse e roda antes dos
    fixtures do teste, então pedir `mailer` aqui sobrescreveria `failing_md` /
    `slow_md` e o teste de resiliência não exercitaria falha nenhuma. Por isso
    `_wire` não injeta mailer: cada fixture de mailer se autoinjeta.
    """
    import api.public_leads as pl

    monkeypatch.setattr(pl, "repo", fake_repo, raising=False)
    monkeypatch.setattr(pl, "limiter", MemoryLimiter(), raising=False)
    return fake_repo