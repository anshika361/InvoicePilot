import json
import os
import re
from collections import defaultdict

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024


def is_hosted_demo():
    return (
        os.environ.get("INVOICEPILOT_HOSTED", "").lower() == "true"
        or os.environ.get("RENDER", "").lower() == "true"
    )


def normalize_amount(value):
    if value is None:
        return 0.0
    text = str(value).strip().replace("USD", "").replace("$", "").replace(",", "")
    text = text.replace("€", "").replace("£", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def extract_invoice(text):
    raw = (text or "").strip()
    if not raw:
        return {"vendor": "", "client": "", "invoice_id": "", "date": "", "subtotal": 0.0, "tax": 0.0, "total": 0.0, "items": [], "summary": {}}

    lines = [line.strip() for line in raw.splitlines() if line.strip()]

    vendor = ""
    client = ""
    invoice_id = ""
    invoice_date = ""
    subtotal = 0.0
    tax_total = 0.0
    total = 0.0

    for index, line in enumerate(lines):
        if not vendor:
            if re.search(r"(Invoice|Bill|Receipt)", line, flags=re.I):
                continue
            if any(keyword in line.lower() for keyword in ["studio", "consulting", "design", "labs", "solutions", "freelance", "agency"]):
                vendor = line
                continue
        if not invoice_id:
            match = re.search(r"(?:Invoice|Bill|Receipt)[\s#:-]*([A-Za-z0-9-]+)", line, flags=re.I)
            if match:
                invoice_id = match.group(1)
        if not client:
            match = re.search(r"(?:Client|Customer|For):\s*(.+)", line, flags=re.I)
            if match:
                client = match.group(1).strip()
        if not invoice_date:
            match = re.search(r"(?:Date|Issued):\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}-\d{1,2}-\d{4})", line, flags=re.I)
            if match:
                invoice_date = match.group(1).strip()

        if re.search(r"(?:subtotal|sub total)", line, flags=re.I):
            subtotal_match = re.search(r"\$?\d[\d,]*\.\d{2}|\$?\d[\d,]*", line)
            if subtotal_match:
                subtotal = normalize_amount(subtotal_match.group(0))
        if re.search(r"(?:tax|vat|sales tax)", line, flags=re.I):
            tax_match = re.search(r"\$?\d[\d,]*\.\d{2}|\$?\d[\d,]*", line)
            if tax_match:
                tax_total = normalize_amount(tax_match.group(0))
        if re.search(r"(?:total|amount due|grand total)", line, flags=re.I):
            total_match = re.search(r"\$?\d[\d,]*\.\d{2}|\$?\d[\d,]*", line)
            if total_match:
                total = normalize_amount(total_match.group(0))

    if not vendor:
        vendor = lines[0] if lines else ""

    item_lines = []
    for line in lines:
        if not any(keyword in line.lower() for keyword in ["invoice", "date", "client", "customer", "tax", "total", "subtotal", "amount due", "bill to", "ship to"]):
            amount_match = re.search(r"\$?\d[\d,]*\.\d{2}|\$?\d[\d,]*", line)
            if amount_match:
                item_name = line.split(amount_match.group(0))[0].strip(" -•*")
                if item_name:
                    item_lines.append({
                        "item": item_name,
                        "amount": normalize_amount(amount_match.group(0)),
                        "category": infer_category(item_name),
                    })

    if not total and item_lines:
        total = sum(item["amount"] for item in item_lines)
    if not subtotal and item_lines:
        subtotal = sum(item["amount"] for item in item_lines)

    summary = summarize_breakdown(item_lines)

    result = {
        "vendor": vendor,
        "client": client,
        "invoice_id": invoice_id,
        "date": invoice_date,
        "subtotal": subtotal,
        "tax": tax_total,
        "total": total,
        "items": item_lines,
        "summary": summary,
    }
    return result


def infer_category(item_name):
    lowered = item_name.lower()
    if any(word in lowered for word in ["design", "brand", "logo", "ui", "layout", "creative"]):
        return "design"
    if any(word in lowered for word in ["website", "dev", "build", "app", "integration", "backend", "api"]):
        return "development"
    if any(word in lowered for word in ["travel", "hotel", "flight", "parking", "uber", "mileage"]):
        return "travel"
    if any(word in lowered for word in ["hosting", "subscription", "software", "tool", "license"]):
        return "software"
    if any(word in lowered for word in ["bundle", "package", "content", "writing", "copy"]):
        return "content"
    return "miscellaneous"


def summarize_breakdown(items):
    totals = defaultdict(float)
    for item in items:
        category = item.get("category", "miscellaneous")
        totals[category] += float(item.get("amount", 0.0))
    return dict(sorted(totals.items()))


def call_local_ollama(text):
    default_url = "" if is_hosted_demo() else "http://localhost:11434"
    base_url = os.environ.get("OLLAMA_BASE_URL", default_url).rstrip("/")
    if not base_url:
        return None

    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    try:
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "stream": False,
                "prompt": (
                    "Extract structured invoice data from this text. Return JSON with fields: "
                    "vendor, client, invoice_id, date, subtotal, tax, total, items. "
                    "Use numbers without currency symbols.\n\n" + text
                ),
            },
            timeout=12,
        )
        if response.status_code == 200:
            payload = response.json()
            answer = payload.get("response", "")
            if answer:
                return json.loads(answer)
    except Exception:
        return None
    return None


@app.route("/")
def index():
    return render_template("index.html", hosted_demo=is_hosted_demo())


@app.route("/healthz")
def health_check():
    return jsonify({"status": "ok"})


@app.route("/api/parse", methods=["POST"])
def parse_invoice_route():
    text = (request.form.get("invoice_text") or "").strip()
    if not text:
        uploaded = request.files.get("invoice_file")
        if uploaded and uploaded.filename:
            text = uploaded.read().decode("utf-8", errors="ignore")

    parsed = extract_invoice(text) if text else {"vendor": "", "client": "", "invoice_id": "", "date": "", "subtotal": 0.0, "tax": 0.0, "total": 0.0, "items": [], "summary": {}}
    model_status = "offline"
    model_notes = "No Ollama model configured. Using the deterministic fallback parser."

    try:
        model_payload = call_local_ollama(text)
        if model_payload:
            model_status = "online"
            merged = {**parsed, **model_payload}
            for amount_field in ("subtotal", "tax", "total"):
                merged[amount_field] = parsed.get(amount_field, 0.0)
            if not merged["total"] and merged.get("items"):
                merged["total"] = round(
                    sum(normalize_amount(item.get("amount")) for item in merged["items"]),
                    2,
                )
            merged["summary"] = summarize_breakdown(merged.get("items", []))
            parsed = merged
            model_notes = "Open-weight model connected locally via Ollama and used for structured extraction."
    except Exception:
        pass

    return jsonify({"result": parsed, "model": {"status": model_status, "notes": model_notes}})


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=5000)
