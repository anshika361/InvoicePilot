from app import extract_invoice, summarize_breakdown


def test_extract_invoice_parses_common_fields():
    text = """
    Acme Studio
    Invoice #2049
    Date: 2026-10-12
    Client: Northwind Labs
    Services: Brand Design, Website QA
    Total: $1,240.00
    Tax: $96.50
    """
    result = extract_invoice(text)

    assert result["vendor"] == "Acme Studio"
    assert result["client"] == "Northwind Labs"
    assert result["total"] == 1240.0
    assert result["tax"] == 96.5


def test_summarize_breakdown_groups_items():
    items = [
        {"item": "Brand Design", "category": "design", "amount": 600.0},
        {"item": "Website QA", "category": "development", "amount": 640.0},
        {"item": "Travel", "category": "travel", "amount": 120.0},
    ]

    summary = summarize_breakdown(items)

    assert summary["design"] == 600.0
    assert summary["development"] == 640.0
    assert summary["travel"] == 120.0


def test_parse_endpoint_returns_local_result_without_ollama(monkeypatch):
    import app as invoice_app

    monkeypatch.setattr(invoice_app, "call_local_ollama", lambda _text: None)
    client = invoice_app.app.test_client()

    response = client.post(
        "/api/parse",
        data={"invoice_text": "Acme Studio\nClient: Northwind Labs\nTotal: $125.00"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"]["vendor"] == "Acme Studio"
    assert payload["result"]["total"] == 125.0
    assert payload["model"]["status"] == "offline"


def test_parse_endpoint_keeps_source_total_when_model_returns_conflicting_total(monkeypatch):
    import app as invoice_app

    monkeypatch.setattr(
        invoice_app,
        "call_local_ollama",
        lambda _text: {
            "vendor": "Model Vendor",
            "total": 999.99,
            "items": [{"item": "Brand Design", "amount": 50.0, "category": "design"}],
        },
    )
    client = invoice_app.app.test_client()

    response = client.post(
        "/api/parse",
        data={"invoice_text": "Acme Studio\nTotal: $125.00"},
    )

    payload = response.get_json()
    assert payload["result"]["vendor"] == "Model Vendor"
    assert payload["result"]["total"] == 125.0
    assert payload["result"]["items"][0]["item"] == "Brand Design"


def test_hosted_demo_does_not_call_local_ollama_by_default(monkeypatch):
    import app as invoice_app

    monkeypatch.setenv("INVOICEPILOT_HOSTED", "true")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(
        invoice_app.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected Ollama call")),
    )

    assert invoice_app.call_local_ollama("fictional invoice") is None


def test_render_environment_activates_hosted_demo_mode(monkeypatch):
    import app as invoice_app

    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("INVOICEPILOT_HOSTED", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(
        invoice_app.requests,
        "post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected Ollama call")),
    )
    client = invoice_app.app.test_client()

    page = client.get("/")

    assert invoice_app.is_hosted_demo()
    assert invoice_app.call_local_ollama("fictional invoice") is None
    assert b"Hosted demo" in page.data
    assert b"fictional or test invoice data" in page.data


def test_health_check_and_hosted_privacy_notice(monkeypatch):
    import app as invoice_app

    monkeypatch.setenv("INVOICEPILOT_HOSTED", "true")
    client = invoice_app.app.test_client()

    health = client.get("/healthz")
    page = client.get("/")

    assert health.status_code == 200
    assert health.get_json() == {"status": "ok"}
    assert b"Hosted demo" in page.data
    assert b"fictional or test invoice data" in page.data
