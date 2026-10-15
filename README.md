# InvoicePilot

InvoicePilot is a lightweight local invoice organizer for freelancers and small businesses. It takes a pasted invoice or receipt and extracts the vendor, client, date, total, tax, and line items, then groups them by category so the user can see where revenue is going.

## Why this fits the challenge

This project supports open-source AI and privacy-first local use:

- It can run with a local Ollama model such as `llama3.2` or `qwen2.5` if the user has an open-weight model installed.
- In local mode, invoice text is sent only to the app running on your machine; optional Ollama inference targets a local model endpoint.
- It is designed for a real freelance workflow: sorting invoices and receipts without paying an ongoing SaaS fee.
- The parsing logic is fast, offline-friendly, and can be extended for niche invoice formats.

## Local open-source model mode

If Ollama is installed locally, the app will try to call a local model before falling back to its deterministic parser:

1. Install Ollama.
2. Run: `ollama pull llama3.2`
3. Start the app with: `python app.py`
4. The app will automatically use local inference when the model is available.

If no local model is available, the app keeps working with a transparent rule-based parser. In local mode, neither path requires a hosted AI service.

## Run locally

```bash
python -m pip install -r requirements.txt
python app.py
```

Then open: http://localhost:5000

## Deploy on Render

The repository includes a Render Blueprint in `render.yaml`. To deploy:

1. Push this project to a GitHub repository.
2. In Render, create a new Blueprint and connect that repository.
3. Review the `invoicepilot` web service and deploy it. Render will install `requirements-render.txt`, start Gunicorn, and use `/healthz` for its health check.

Render runs InvoicePilot in **hosted demo mode**. Invoice text submitted to the public site is sent to the Render server for processing, so use fictional/test invoices only—not real customer or financial documents. The app does not intentionally persist request text, but this is not the same privacy boundary as running it on your own device. The hosted service uses the deterministic fallback by default and does not try localhost Ollama. An operator can set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` to use a separately reachable Ollama endpoint; in that configuration, invoice text is also sent to that endpoint.

For real invoices, use the local setup above instead of the public demo.

## Business angle

A freelancer who receives 15-30 invoices a month can use this to:

- spot duplicate vendor bills
- separate design, development, travel, and software expenses
- estimate tax obligations from receipts
- keep data on their own machine instead of paying for a cloud-only tool

## Stack

- Python
- Flask
- Open-source local inference via Ollama (optional)
- Rule-based extraction fallback for no-internet / local-only use
