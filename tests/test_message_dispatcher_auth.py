from unittest.mock import patch

from api.message_dispatcher import MessageDispatcher


def test_inbound_uses_dedicated_credential_instead_of_management_key(monkeypatch):
    monkeypatch.setenv("MD_API_KEY", "management-secret")
    monkeypatch.setenv("MD_INBOUND_API_KEY", "inbound-secret")
    client = MessageDispatcher(base_url="http://md.test")

    with patch.object(client, "_request", return_value={"ok": True}) as request:
        assert client.send("topic", "message") == {"ok": True}

    assert request.call_args.kwargs["auth"] is True
    assert request.call_args.kwargs["api_key"] == "inbound-secret"


def test_inbound_fails_closed_without_dedicated_credential(monkeypatch):
    monkeypatch.setenv("MD_API_KEY", "management-secret")
    monkeypatch.delenv("MD_INBOUND_API_KEY", raising=False)
    client = MessageDispatcher(base_url="http://md.test")

    with patch("urllib.request.urlopen") as urlopen:
        # The request layer is not reached when the dedicated credential is absent.
        try:
            client.send("topic", "message")
        except Exception as exc:
            assert "MD_INBOUND_API_KEY" in str(exc)
        else:
            raise AssertionError("inbound send must fail closed")
    urlopen.assert_not_called()


def test_send_targets_a_specific_recipient(monkeypatch):
    """O inbound aceita `recipient`; sem ele a mensagem cai na regra de
    fallback (admin_notify) e nunca chega ao cliente. STORY-GW-039."""
    monkeypatch.setenv("MD_INBOUND_API_KEY", "inbound-secret")
    client = MessageDispatcher(base_url="http://md.test")

    with patch.object(client, "_request", return_value={"success": True}) as request:
        client.send("gateway.admin_notify", "msg", recipient="cliente@exemplo.test")

    payload = request.call_args.args[2]
    assert payload["recipient"] == "cliente@exemplo.test"


def test_recipient_is_omitted_when_not_given(monkeypatch):
    monkeypatch.setenv("MD_INBOUND_API_KEY", "inbound-secret")
    client = MessageDispatcher(base_url="http://md.test")

    with patch.object(client, "_request", return_value={"success": True}) as request:
        client.send("gateway.admin_notify", "msg")

    payload = request.call_args.args[2]
    assert "recipient" not in payload


def test_recipient_is_validated(monkeypatch):
    """Email malformado e erro nosso, nao do MD: falha antes de enviar."""
    monkeypatch.setenv("MD_INBOUND_API_KEY", "inbound-secret")
    client = MessageDispatcher(base_url="http://md.test")

    for bad in ("nao-e-email", "a b@x.com", ""):
        with patch.object(client, "_request") as request:
            try:
                client.send("t", "m", recipient=bad)
            except Exception:
                pass
            else:
                raise AssertionError(f"aceitou recipient invalido: {bad!r}")
            request.assert_not_called()
