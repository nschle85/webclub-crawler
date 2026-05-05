import argparse
import getpass
import sys

from webclub_crawler.config import get_credentials
from webclub_crawler.models import BEST_TIME_VARIANTS


def _resolve_credentials(args):
    username, password = get_credentials(args.username, args.password)

    if not username:
        username = input("Benutzername: ")
    if not password:
        password = getpass.getpass("Passwort: ")

    return username, password


def run_requests(args):
    from webclub_crawler.crawlers.requests_best_times import WebClubTurboCrawler

    username, password = _resolve_credentials(args)

    crawler = WebClubTurboCrawler(base_url=args.base_url)
    if crawler.login(username, password):
        members = crawler.fetch_members()
        selected_members = crawler._prompt_for_swimmers(members) if members else []
        results_by_variant = crawler.fetch_best_times([member["id"] for member in selected_members])
        if results_by_variant:
            for variant in BEST_TIME_VARIANTS:
                rows = results_by_variant.get(variant.key)
                if rows:
                    crawler.save_csv(rows, variant.filename)
        else:
            print("Keine Ergebnisse extrahiert.")


def run_selenium(args):
    from webclub_crawler.crawlers.selenium_best_times import WebClubCrawler

    username, password = _resolve_credentials(args)

    crawler = WebClubCrawler(headless=args.headless, base_url=args.base_url)
    try:
        crawler.login(username, password)
        data = crawler.get_best_times()
        crawler.save_to_csv(data, args.output)
    finally:
        crawler.close()


def build_parser():
    parser = argparse.ArgumentParser(prog="webclub-crawler")
    subparsers = parser.add_subparsers(dest="command")

    requests_parser = subparsers.add_parser("requests", help="Run the fast AJAX/requests crawler.")
    requests_parser.add_argument("--base-url", default=None, help="Override WEBCLUB_BASE_URL.")
    requests_parser.add_argument("--username", default=None, help="Override WEBCLUB_USER.")
    requests_parser.add_argument("--password", default=None, help="Override WEBCLUB_PASSWORD.")
    requests_parser.set_defaults(func=run_requests)

    selenium_parser = subparsers.add_parser("selenium", help="Run the browser-based Selenium fallback crawler.")
    selenium_parser.add_argument("--base-url", default=None, help="Override WEBCLUB_BASE_URL.")
    selenium_parser.add_argument("--username", default=None, help="Override WEBCLUB_USER.")
    selenium_parser.add_argument("--password", default=None, help="Override WEBCLUB_PASSWORD.")
    selenium_parser.add_argument("--output", default="bestzeiten.csv", help="CSV output filename.")
    selenium_parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=False)
    selenium_parser.set_defaults(func=run_selenium)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    args.func(args)
    return 0


def requests_main(argv=None):
    forwarded_args = sys.argv[1:] if argv is None else argv
    return main(["requests", *forwarded_args])


def selenium_main(argv=None):
    forwarded_args = sys.argv[1:] if argv is None else argv
    return main(["selenium", *forwarded_args])
