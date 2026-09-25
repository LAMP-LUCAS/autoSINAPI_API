"""Regressão do handoff SSO: a asserção precisa ser montada sem KeyError.

Incidente 2026-09-25: o endpoint `message-dispatcher-sso` respondia HTTP 500.
A causa foi a construção das claims iterando `row["jti"]`, sendo `jti` uma
variável local e não uma coluna do SELECT — `KeyError` em tempo de execução.
Nenhum teste cobria a montagem porque ela estava inline no handler.

Estes testes fixam o contrato da asserção:
  - claims contêm os identificadores e o `jti`, nessa ordem;
  - a assinatura é HMAC-SHA256 das claims e é verificável de forma independente;
  - `key_prefix` nulo (linha legada) não quebra a montagem;
  - a asserção NÃO contém a raw key.
"""
import hashlib
import hmac

import pytest

from api.portal import _build_sso_claims, _sign_sso_claims


class _Row(dict):
    """Stand-in do Row do SQLAlchemy: acesso por chave, como no handler."""

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        return super().__getitem__(key)


def _row(**overrides):
    base = {
        "email": "cliente@exemplo.test",
        "client_id": "11111111-1111-1111-1111-111111111111",
        "subscription_id": "22222222-2222-2222-2222-222222222222",
        "key_id": "33333333-3333-3333-3333-333333333333",
        "key_prefix": "ab12cd34",
    }
    base.update(overrides)
    return _Row(base)


def test_claims_include_every_claim_in_stable_order():
    claims = _build_sso_claims(_row(), jti="XYZ", issued_at=1700000000, expires_at=1700000300)
    parts = claims.split("|")
    assert parts == [
        "cliente@exemplo.test",
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
        "33333333-3333-3333-3333-333333333333",
        "ab12cd34",
        "XYZ",
        "1700000000",
        "1700000300",
    ]


def test_signature_is_hmac_of_the_claims_and_verifiable():
    claims = _build_sso_claims(_row(), jti="XYZ", issued_at=1, expires_at=2)
    signature = _sign_sso_claims(claims, "segredo-de-teste")
    expected = hmac.new(b"segredo-de-teste", claims.encode(), hashlib.sha256).hexdigest()
    assert signature == expected
    # Verificação independente, como o receptor do MD fará.
    assert hmac.compare_digest(
        signature,
        hmac.new(b"segredo-de-teste", claims.encode(), hashlib.sha256).hexdigest(),
    )


def test_tampering_changes_the_signature():
    claims = _build_sso_claims(_row(), jti="XYZ", issued_at=1, expires_at=2)
    original = _sign_sso_claims(claims, "segredo-de-teste")
    tampered = _sign_sso_claims(claims.replace("ab12cd34", "deadbeef"), "segredo-de-teste")
    assert original != tampered


def test_legacy_row_without_key_prefix_does_not_raise():
    """Linha legada pode ter key_prefix NULL; a montagem não pode explodir."""
    row = _row(key_prefix=None)
    claims = _build_sso_claims(row, jti="XYZ", issued_at=1, expires_at=2)
    assert claims.split("|")[4] == ""
    _sign_sso_claims(claims, "segredo-de-teste")


def test_claims_never_carry_a_raw_key():
    raw = "autosinapi_deadbeefdeadbeefdeadbeefdeadbeef"
    row = _row()
    claims = _build_sso_claims(row, jti="XYZ", issued_at=1, expires_at=2)
    assert raw not in claims
    # Nenhum valor de `row` além dos metadados permitidos entra na asserção.
    allowed = {str(v) for v in row.values()} | {"XYZ", "1", "2"}
    assert set(claims.split("|")) <= allowed


def test_missing_column_raises_informative_error():
    row = _row()
    del row["key_id"]
    with pytest.raises(KeyError):
        _build_sso_claims(row, jti="XYZ", issued_at=1, expires_at=2)
