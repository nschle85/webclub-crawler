import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from webclub_crawler.cli import requests_main
from webclub_crawler.crawlers.requests_best_times import WebClubTurboCrawler
from webclub_crawler.models import BEST_TIME_VARIANTS


__all__ = ["BEST_TIME_VARIANTS", "WebClubTurboCrawler"]


if __name__ == "__main__":
    raise SystemExit(requests_main())
