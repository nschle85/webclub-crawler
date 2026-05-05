# WebClub Crawler

Python package for exporting WebClub best-times data.

## Clean Clone Setup

```bash
git clone https://github.com/nschle85/webclub-crawler.git
cd webclub-crawler

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e .

cp .env.example .env
```

Set `WEBCLUB_USER`, `WEBCLUB_PASSWORD`, and `WEBCLUB_BASE_URL` in `.env`.

```env
WEBCLUB_USER=your_username
WEBCLUB_PASSWORD=your_password
WEBCLUB_BASE_URL=https://your-club.webclub.app/
```

## Usage

Fast AJAX/requests crawler:

```bash
webclub-crawler requests
```

Browser-based Selenium fallback:

```bash
webclub-crawler selenium --no-headless
```

The legacy scripts still work:

```bash
python webclub_requests_crawler.py
python webclub_selenium_crawler.py
```

## Development

The package uses a `src` layout. Change module code under:

```text
src/webclub_crawler/
```

Useful checks:

```bash
python -m compileall webclub_requests_crawler.py webclub_selenium_crawler.py src
webclub-crawler --help
webclub-crawler requests --help
webclub-crawler selenium --help
```

Because the package is installed editable with `python -m pip install -e .`, changes under
`src/webclub_crawler/` are picked up immediately. Reinstall only after changing package metadata,
entry points, or dependencies in `pyproject.toml`.

## Repository Hygiene

Keep these files in Git:

```text
pyproject.toml
README.md
.env.example
.gitignore
src/webclub_crawler/
webclub_requests_crawler.py
webclub_selenium_crawler.py
```

Do not commit local runtime, environment, or IDE artifacts:

```text
.env
.venv/
__pycache__/
*.egg-info/
.junie/
.idea/
*.csv
debug_*.html
debug_*.txt
```

If an IDE file was already tracked by Git, remove it from tracking while keeping it locally:

```bash
git rm --cached .idea/crawl-besttimes.iml
```
