"""WebClub crawler package."""

from webclub_crawler.crawlers.requests_best_times import WebClubTurboCrawler
from webclub_crawler.crawlers.selenium_best_times import WebClubCrawler

__all__ = ["WebClubCrawler", "WebClubTurboCrawler"]
