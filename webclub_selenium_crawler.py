import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from webclub_crawler.cli import selenium_main
from webclub_crawler.crawlers.selenium_best_times import WebClubCrawler


__all__ = ["WebClubCrawler"]


if __name__ == "__main__":
    raise SystemExit(selenium_main())
