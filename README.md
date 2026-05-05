# WebClub Crawler

Python package for exporting WebClub best-times data.

## Setup

```bash
python -m pip install -e .
cp .env.example .env
```

Set `WEBCLUB_USER`, `WEBCLUB_PASSWORD`, and `WEBCLUB_BASE_URL` in `.env`.

## Usage

Fast AJAX/requests crawler:

```bash
webclub-crawler requests
```

Browser-based Selenium fallback:

```bash
webclub-crawler selenium
```

The legacy scripts still work:

```bash
python webclub_requests_crawler.py
python webclub_selenium_crawler.py
```
