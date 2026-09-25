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
