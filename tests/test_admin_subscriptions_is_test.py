"""Testes do campo `is_test` na listagem de assinaturas.

Contexto: o validador de plataforma emite uma credencial temporária para os
checks autenticados e a revoga em seguida. Em qual assinatura ela é pendurada
importa: usar a assinatura de um cliente real deixa `created_at` no registro
dele e pode consumir quota.

A coluna `saas.clients.is_test` existe exatamente para separar registro de
teste/integração do funil real (migration 018), e o painel admin já a filtra.
Mas a listagem de assinaturas **não a expunha**, então o validador era
obrigado a adivinhar pelo e-mail — heurística que pode classificar um cliente
real como teste.

Estes testes fixam a exposição do sinal autoritativo.
"""
import pytest
from api import admin_crm


class _Result:
    def __init__(self, rows, total=0):
        self._rows = rows
        self._total = total

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._total


class _DB:
    def __init__(self):
        self.queries = []

    def execute(self, stmt, params=None):
        text = str(stmt)
        self.queries.append(text)
        if "COUNT(*)" in text and "LIMIT" not in text:
            return _Result([], 0)
        return _Result([])


def test_subscription_list_exposes_the_is_test_flag():
    db = _DB()
    admin_crm.list_subscriptions(limit=10, offset=0, include_deleted=False,
                                 q=None, status=None, source=None, db=db)
    select = next(q for q in db.queries if "FROM saas.subscriptions s" in q and "LIMIT" in q)
    assert "is_test" in select, (
        "a listagem precisa expor c.is_test: sem o sinal autoritativo o "
        "validador depende de heuristica de e-mail"
    )


def test_grandfathered_rows_stay_valid_without_the_flag():
    """`_row` normaliza ausências para False — nunca None/ausente.

    Sem isso, um cliente legado sem `is_test` viraria None e a comparação
    booleana no consumidor quebraria.
    """
    row = admin_crm._row({"client_email": "a@b.c"})
    assert row.get("client_is_test") is False


def test_flag_is_true_when_the_client_is_marked():
    row = admin_crm._row({"client_email": "e2e@x.test", "client_is_test": True})
    assert row["client_is_test"] is True
