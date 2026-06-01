# Conlenz Audit Tool

Desktop scanner for customer-facing content with Quick (incremental) and Deep (full) scans.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and set `RESEND_KEY` and `RESEND_MAIL`.

## Run (Desktop)

```bash
python -m app.main
```

## Run (CLI)

```bash
python -m app.cli_scan --path . --mode deep
```

## Build (Nuitka, Windows)

```bash
python -m nuitka --standalone app\\main.py
```

`--standalone` (one-folder) is recommended for EasyOCR reliability. We can try one-file later once stable.
