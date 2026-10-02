"""TDD — o e-mail de boas-vindas precisa do template certo.

Bug real de 2026-10-02: a lead Viviane Forte (assistentecomercial@pbg.com.br),
primeira lead real capturada depois da porta ser restaurada, recebeu a OS com
`template_id = 11111111…` (`gateway_message`, o template genérico) em vez de
`66666666…` (`gateway_lead_welcome`).

Causa: quando a captura saiu do plugin Lua do Kong para o backend, o
`MessageDispatcher.send()` do backend não sabia passar `template_id`. O MD
aceita (o `InboundController` repassa), mas o cliente Python montava um payload
sem esse campo — e o MD caía no template genérico do tópico.

O sintoma é silencioso: a OS sai `sent`, o assunto é o do template errado, e
nada no fluxo denuncia. Só apareceu porque foi conferido o `template_id` da OS
de uma lead real.
"""

import pytest


@pytest.fixture
def md(monkeypatch):
    """Cliente do MD com `_request` interceptado — nenhum HTTP real.

    O `__init__` real continua: só `_request` (a camada HTTP) é substituída,
    então o teste exercita o `send()` de verdade.
    """
    from api import message_dispatcher as mdmod

    sent: dict = {}

    def fake_request(self, method, path, payload=None, auth=False, api_key=None):
        sent.clear()
        sent.update(payload or {})
        return {"id": "os-1", "status": "accepted"}

    monkeypatch.setattr(mdmod.MessageDispatcher, "_request", fake_request, raising=True)
    return sent


class TestBoasVindas:
    def test_envia_o_template_de_lead_welcome(self, md):
        """O template precisa ser o de boas-vindas, não o genérico."""
        from api.public_leads import LEAD_WELCOME_TEMPLATE_ID, _mailer

        send = _mailer()
        send(lead_id="l1", name="Ana", email="ana@exemplo.com", source="portal")

        assert md["template_id"] == LEAD_WELCOME_TEMPLATE_ID
        assert md["template_id"] != "11111111-1111-1111-1111-111111111111"

    def test_envia_as_variaveis_do_template(self, md):
        """Sem as variáveis, o Liquid fica com placeholder cru no corpo."""
        from api.public_leads import _mailer

        send = _mailer()
        send(lead_id="l1", name="Ana Souza", email="ana@exemplo.com", source="portal")

        variables = md.get("variables") or {}
        # O schema do template é {lead_name, portal_url, tools_url}: enviar
        # menos deixa o Liquid com `{{ ... }}` visível no e-mail do cliente.
        for key in ("lead_name", "portal_url", "tools_url"):
            assert variables.get(key), f"variável {key} ausente: {variables}"

    def test_o_assunto_vem_do_template(self, md):
        """Com template_id, o MD usa o `subject_liquid` do template."""
        from api.public_leads import _mailer

        send = _mailer()
        send(lead_id="l1", name="Ana", email="ana@exemplo.com", source="portal")

        # `title` é o fallback; com template_id o MD prefere o assunto do
        # template. Mandar os dois ébelt-and-suspenders: se o template faltar,
        # ainda há assunto legível.
        assert md.get("title")

    def test_idempotency_key_trava_o_envio(self, md):
        """Duas submissões do mesmo formulário não podem gerar 2 OS.

        O dedupe de lead já evita duas linhas no banco, mas o envio acontece
        antes da resposta — sem chave de idempotência, um reenvio que chegue
        antes do commit (ou um retry do worker) vira e-mail duplicado na caixa
        do cliente.
        """
        from api.public_leads import _mailer

        send = _mailer()
        send(lead_id="lead-abc", name="Ana", email="ana@exemplo.com", source="portal")

        assert md.get("idempotency_key"), "sem idempotency_key: reenvio duplica e-mail"
        assert "lead-abc" in md["idempotency_key"]


class TestPayloadDoMD:
    def test_send_aceita_template_id_e_variables(self, md):
        """O cliente precisa expor o que o `InboundController` já aceita."""
        from api.message_dispatcher import MessageDispatcher

        MessageDispatcher().send(
            "gateway.lead_welcome", "corpo", recipient="a@b.com",
            template_id="tpl-1", variables={"lead_name": "Ana"},
            idempotency_key="idem-1",
        )

        assert md["template_id"] == "tpl-1"
        assert md["variables"] == {"lead_name": "Ana"}
        assert md["idempotency_key"] == "idem-1"

    def test_send_sem_template_mantem_o_payload_minimo(self, md):
        """Não enviar `template_id` não pode virar `None` no payload.

        O MD distingue "não informado" de "informado e vazio"; mandar
        `None` explicitamente muda a resolução do template.
        """
        from api.message_dispatcher import MessageDispatcher

        MessageDispatcher().send("gateway.metrics_report", "corpo")

        assert "template_id" not in md
        assert "variables" not in md