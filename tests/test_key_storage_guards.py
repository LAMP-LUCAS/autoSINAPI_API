from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_api_key_issuance_never_writes_plaintext_column():
    for name in ("admin_portal.py", "admin_crm.py"):
        source = (ROOT / "api" / name).read_text()
        assert "key_value, key_prefix" not in source
        assert "key_prefix, key_hash" in source
        assert "crypt(:key_value, gen_salt('bf'))" in source or "crypt(:kv, gen_salt('bf'))" in source


def test_sso_does_not_select_or_return_plaintext_api_key():
    for name in ("admin_messages.py", "portal.py"):
        source = (ROOT / "api" / name).read_text()
        assert "k.key_value AS key_value" not in source
        assert "key_value IS NOT NULL" not in source
        assert '"autosinapi_api_key"' not in source
