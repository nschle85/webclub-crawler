import json

import requests

from webclub_crawler.config import DEFAULT_CLUB_ID, resolve_base_url
from webclub_crawler.exporters import save_rows_to_csv
from webclub_crawler.models import BEST_TIME_VARIANTS
from webclub_crawler.parsers import merge_rows, parse_ajax_response
from webclub_crawler.selection import prompt_for_swimmers


class WebClubTurboCrawler:
    def __init__(self, base_url=None):
        self.base_url = resolve_base_url(base_url)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _request_base_options(self):
        return self.session.post(self.base_url + "ajax.php", data={"func": "best/swrbase2"})

    def _build_member_payload(self, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
        return {
            "ausSTR": club_id,
            "ausSTA": branch_id,
            "ausGRP": group_id,
            "actonly": 1,
            "dsvonly": 1,
        }

    def _request_member_options(self, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
        ajax_payload = {
            "func": "best/swrgetswr",
            "data": json.dumps(self._build_member_payload(club_id, branch_id, group_id)),
        }
        return self.session.post(self.base_url + "ajax.php", data=ajax_payload)

    def _build_best_times_payload(
        self,
        swimmer_id,
        list_value,
        club_id=DEFAULT_CLUB_ID,
        branch_id="0",
        group_id="0",
    ):
        return {
            "ausSTR": club_id,
            "ausSTA": branch_id,
            "ausGRP": group_id,
            "ausZEITRAUM": "0",
            "ausSAISON": "4",
            "ausZEITRVON": "01.01.1900",
            "ausZEITRBIS": "31.12.2099",
            "ausNEWPAGE": "1",
            "ausMASTERBEZ": "1",
            "ausMASTERSCM": "0",
            "ausMASTERLCM": "0",
            "ausFINASCM": "0",
            "ausFINALCM": "0",
            "ausPKTDBS": "0",
            "ausRUDOLPH": "0",
            "actonly": 1,
            "dsvonly": 1,
            "pers": int(swimmer_id),
            "list": [list_value],
        }

    def _merge_rows(self, all_rows, new_rows):
        return merge_rows(all_rows, new_rows)

    def _prompt_for_swimmers(self, swimmers):
        return prompt_for_swimmers(swimmers, id_key="id")

    def login(self, username, password):
        print(f"Logge ein als {username}...")
        payload = {
            "userlogin": "1",
            "username": username,
            "userpwd": password,
        }
        response = self.session.post(self.base_url + "index.php", data=payload)
        if response.status_code == 200 and any(marker in response.text for marker in ["Logout", "Abmelden"]):
            print("Login erfolgreich!")
            return True
        print("Login fehlgeschlagen.")
        return False

    def fetch_members(self):
        print("Rufe Mitgliederliste ab...")
        base_options = self._request_base_options()
        if base_options.status_code == 200:
            try:
                data = base_options.json()
                if data.get("error"):
                    print(f"Fehler beim Abruf der Basisdaten: {data}")
                else:
                    print(
                        f"Basisdaten geladen: {len(data.get('sta', []))} Stammvereine, "
                        f"{len(data.get('grp', []))} Gruppen."
                    )
            except Exception as exc:
                print(f"Hinweis: Basisdaten konnten nicht geparst werden: {exc}")

        response = self._request_member_options()
        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("error"):
                    print(f"Fehler beim Abruf der Mitgliederliste: {data}")
                    return []

                members = []
                for member in data.get("list", []):
                    value = member.get("v")
                    name = member.get("n", "").strip()
                    if value and str(value) != "0":
                        members.append({"id": value, "name": name})
                return members
            except Exception as exc:
                print(f"Fehler beim Parsen der Mitglieder: {exc}")
        return []

    def _fetch_best_times_for_variant(self, swimmer_ids, variant):
        all_rows = []
        for index, swimmer_id in enumerate(swimmer_ids, start=1):
            print(f"[{index}/{len(swimmer_ids)}] Lade {variant.label}-Bestzeiten für Schwimmer-ID {swimmer_id}...")
            ajax_payload = {
                "func": "best/swrbest",
                "data": json.dumps(self._build_best_times_payload(swimmer_id, variant.list_value)),
            }

            response = self.session.post(self.base_url + "ajax.php", data=ajax_payload)
            if response.status_code != 200:
                print(f"Fehler bei Schwimmer-ID {swimmer_id}: {response.status_code}")
                continue

            rows = self._parse_ajax_response(response.text)
            if not rows:
                print(f"Keine Daten für Schwimmer-ID {swimmer_id} extrahiert.")
                continue

            all_rows = merge_rows(all_rows, rows)

        if not all_rows:
            return None

        print(f"{variant.label}-Daten erfolgreich empfangen!")
        return all_rows

    def fetch_best_times(self, swimmer_ids=None):
        print("Rufe Bestzeiten über natives Protokoll ab...")

        swimmers = list(swimmer_ids) if swimmer_ids else [member["id"] for member in self.fetch_members()]
        if not swimmers:
            print("Keine Schwimmer gefunden.")
            return {}

        results = {}
        for variant in BEST_TIME_VARIANTS:
            print(f"\n--- Exportiere {variant.label} separat ---")
            rows = self._fetch_best_times_for_variant(swimmers, variant)
            if rows:
                results[variant.key] = rows
            else:
                print(f"Keine {variant.label}-Ergebnisse extrahiert.")

        return results

    def _parse_ajax_response(self, text):
        return parse_ajax_response(text)

    def save_csv(self, data, filename="bestzeiten_turbo.csv"):
        save_rows_to_csv(data, filename, delimiter="\t")
