# api/message_dispatcher.py
"""HTTP client for the MessageDispatcher (ODC) hub.

The gateway uses MessageDispatcher as its single communication interface for
transactional messages (welcome, quota alerts, lead welcome, renewal, admin
notify). This module is used by the admin panel and workers to *manage* MD
(topics, destinations, DLQ) and to *send* messages via the internal inbound
gateway.

Configuration (env):
    MD_URL      base URL           (default: http://server_odc:3000)
    MD_API_KEY           management API key (required for management endpoints)
    MD_INBOUND_API_KEY   dedicated key for the authenticated inbound endpoint
    MD_TIMEOUT           request timeout s  (default: 5)
    MD_ENABLED  feature toggle     (default: true)
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger("autosinapi.messagedispatcher")


class MessageDispatcherError(Exception):
    """Raised when MD returns an error or is unreachable."""


class MessageDispatcher:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None,
                 timeout: Optional[float] = None):
        self.base_url = (base_url or os.getenv("MD_URL", "http://server_odc:3000")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("MD_API_KEY", "")
        self.inbound_api_key = os.getenv("MD_INBOUND_API_KEY", "")
        self.timeout = float(timeout or os.getenv("MD_TIMEOUT", "5"))
        self.enabled = os.getenv("MD_ENABLED", "true").lower() != "false"

    # ── low-level ─────────────────────────────────────────────────────────────
    def _request(self, method: str, path: str, payload: Optional[dict] = None,
                 auth: bool = True, api_key: Optional[str] = None) -> dict:
        if not self.enabled:
            raise MessageDispatcherError("MessageDispatcher disabled (MD_ENABLED=false)")

        import urllib.request
        import urllib.error

        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            credential = api_key if api_key is not None else self.api_key
            if not credential:
                variable = "MD_INBOUND_API_KEY" if api_key is not None else "MD_API_KEY"
                raise MessageDispatcherError(f"{variable} not configured")
            headers["X-Api-Key"] = credential

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode() or "{}"
                return json.loads(body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300] if e.fp else ""
            logger.warning("MD %s %s -> %s %s", method, path, e.code, detail)
            raise MessageDispatcherError(f"MD HTTP {e.code}: {detail}") from e
        except Exception as e:  # connection refused, timeout, bad json...
            logger.warning("MD %s %s failed: %s", method, path, e)
            raise MessageDispatcherError(f"MD unreachable: {e}") from e

    def health(self) -> bool:
        if not self.enabled:
            return False
        import urllib.request
        import urllib.error
        try:
            req = urllib.request.Request(f"{self.base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    # ── inbound (communication) ───────────────────────────────────────────────
    def send(self, topic: str, message: str, title: Optional[str] = None,
             sender: Optional[str] = None, metadata: Optional[dict] = None) -> dict:
        """Send a message through the authenticated MD inbound gateway."""
        return self._request("POST", "/api/v1/inbound", {
            "topic": topic,
            "message": message,
            "title": title,
            "sender": sender,
            "metadata": metadata or {},
        }, auth=True, api_key=self.inbound_api_key)

    # ── topics ────────────────────────────────────────────────────────────────
    def list_topics(self) -> list:
        return self._request("GET", "/api/v1/topics").get("topics", [])

    def create_topic(self, name: str, description: str = "", destinations: Optional[list] = None) -> dict:
        return self._request("POST", "/api/v1/topics", {
            "name": name, "description": description, "destinations": destinations or [],
        })

    def delete_topic(self, topic_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/topics/{topic_id}")

    def add_destination(self, topic_id: str, channel: str, target: str,
                        channel_account: Optional[str] = None) -> dict:
        return self._request("POST", f"/api/v1/topics/{topic_id}/add_destination", {
            "channel": channel, "target": target, "channel_account": channel_account,
        })

    def remove_destination(self, topic_id: str, channel: str, target: str) -> dict:
        return self._request("DELETE", f"/api/v1/topics/{topic_id}/remove_destination", {
            "channel": channel, "target": target,
        })

    # ── contacts (CRM do MD) ──────────────────────────────────────────────────
    def list_contacts(self) -> list:
        return self._request("GET", "/api/v1/contacts").get("contacts", [])

    def create_contact(self, channel: str, identifier: str, name: Optional[str] = None,
                       metadata: Optional[dict] = None) -> dict:
        return self._request("POST", "/api/v1/contacts", {
            "channel": channel, "identifier": identifier, "name": name,
            "metadata": metadata or {},
        })

    # ── orders (envios reais por destinatário) ────────────────────────────────
    def list_orders(self, limit: int = 100) -> list:
        """OS recentes — destinatários REAIS (usuários/leads), não destinos de tópico."""
        return self._request("GET", f"/api/v1/os?limit={int(limit)}").get("orders", [])

    # ── dead letters / audit ──────────────────────────────────────────────────
    def list_dead_letters(self) -> list:
        return self._request("GET", "/api/v1/dead_letters").get("dead_letters", [])

    def redispatch(self, dlq_id: str) -> dict:
        return self._request("POST", f"/api/v1/dead_letters/{dlq_id}/redispatch")

    def list_audit_logs(self, limit: int = 50) -> list:
        return self._request("GET", f"/api/v1/audit_logs?limit={limit}").get("audit_logs", [])

    # ── observability ─────────────────────────────────────────────────────────
    def metrics(self) -> dict:
        return self._request("GET", "/api/v1/metrics")

    def usage(self) -> dict:
        return self._request("GET", "/api/v1/usage")


def get_client() -> MessageDispatcher:
    return MessageDispatcher()
