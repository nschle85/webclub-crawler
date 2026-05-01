import requests
import getpass
import os
from bs4 import BeautifulSoup
import json
import csv
import urllib.parse
import re
import html
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus .env Datei falls vorhanden
load_dotenv()


DEFAULT_CLUB_ID = "1"
DEFAULT_BASE_URL = os.getenv("WEBCLUB_BASE_URL")
BEST_TIME_VARIANTS = [
    {"key": "kurzbahn", "label": "Kurzbahn", "list_value": 0, "filename": "bestzeiten_turbo_kurzbahn.csv"},
    {"key": "langbahn", "label": "Langbahn", "list_value": 1, "filename": "bestzeiten_turbo_langbahn.csv"},
]
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def _normalize_base_url(base_url):
    return base_url.rstrip("/") + "/"

def _resolve_base_url(base_url=None):
    resolved_base_url = (base_url or DEFAULT_BASE_URL or "").strip()
    if not resolved_base_url:
        raise ValueError("WEBCLUB_BASE_URL must be set in .env or passed as base_url.")
    return _normalize_base_url(resolved_base_url)

class WebClubTurboCrawler:
    def __init__(self, base_url=None):
        self.base_url = _resolve_base_url(base_url)
        self.session = requests.Session()
        # Wir nutzen exakt die Header aus dem Reverse Engineering
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest"
        })

    def _request_base_options(self):
        ajax_url = self.base_url + "ajax.php"
        return self.session.post(ajax_url, data={"func": "best/swrbase2"})

    def _build_member_payload(self, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
        return {
            "ausSTR": club_id,
            "ausSTA": branch_id,
            "ausGRP": group_id,
            "actonly": 1,
            "dsvonly": 1
        }

    def _request_member_options(self, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
        ajax_url = self.base_url + "ajax.php"
        ajax_payload = {
            "func": "best/swrgetswr",
            "data": json.dumps(self._build_member_payload(club_id, branch_id, group_id))
        }
        return self.session.post(ajax_url, data=ajax_payload)

    def _build_best_times_payload(self, swimmer_id, list_value, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
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
            "list": [list_value]
        }

    def _merge_rows(self, all_rows, new_rows):
        if not new_rows:
            return all_rows

        if not all_rows:
            return list(new_rows)

        header = all_rows[0]
        start_index = 1 if new_rows and new_rows[0] == header else 0
        all_rows.extend(new_rows[start_index:])
        return all_rows

    def _prompt_for_swimmers(self, swimmers):
        if not swimmers:
            print("No swimmers found.")
            return []

        print("\nAvailable swimmers:")
        for index, swimmer in enumerate(swimmers, start=1):
            print(f"{index:>3}: {swimmer['name']}")

        print("\nSelection examples: 1, 3-5, Anna, all")
        while True:
            raw_selection = input("Which swimmers should be exported? ").strip()
            if not raw_selection:
                print("Please enter at least one swimmer or 'all'.")
                continue

            if raw_selection.lower() == "all":
                return swimmers

            selected = []
            seen_ids = set()
            invalid_tokens = []

            for token in [part.strip() for part in raw_selection.split(",") if part.strip()]:
                range_match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
                if range_match:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2))
                    if start > end:
                        start, end = end, start
                    for idx in range(start, end + 1):
                        if 1 <= idx <= len(swimmers):
                            swimmer = swimmers[idx - 1]
                            if swimmer["id"] not in seen_ids:
                                selected.append(swimmer)
                                seen_ids.add(swimmer["id"])
                        else:
                            invalid_tokens.append(token)
                            break
                    continue

                if token.isdigit():
                    idx = int(token)
                    if 1 <= idx <= len(swimmers):
                        swimmer = swimmers[idx - 1]
                        if swimmer["id"] not in seen_ids:
                            selected.append(swimmer)
                            seen_ids.add(swimmer["id"])
                    else:
                        invalid_tokens.append(token)
                    continue

                matches = [swimmer for swimmer in swimmers if token.lower() in swimmer["name"].lower()]
                if len(matches) == 1:
                    swimmer = matches[0]
                    if swimmer["id"] not in seen_ids:
                        selected.append(swimmer)
                        seen_ids.add(swimmer["id"])
                elif len(matches) > 1:
                    invalid_tokens.append(f"{token} (matches multiple swimmers)")
                else:
                    invalid_tokens.append(token)

            if selected and not invalid_tokens:
                print("Selected swimmers:")
                for swimmer in selected:
                    print(f"- {swimmer['name']}")
                return selected

            if invalid_tokens:
                print("Could not resolve:", ", ".join(invalid_tokens))
            else:
                print("No valid swimmers selected.")

    def login(self, username, password):
        print(f"Logge ein als {username}...")
        payload = {
            "userlogin": "1",
            "username": username,
            "userpwd": password
        }
        # Login an der Hauptseite
        res = self.session.post(self.base_url + "index.php", data=payload)
        if res.status_code == 200 and any(m in res.text for m in ["Logout", "Abmelden"]):
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
            except Exception as e:
                print(f"Hinweis: Basisdaten konnten nicht geparst werden: {e}")

        res = self._request_member_options()
        if res.status_code == 200:
            try:
                data = res.json()
                if data.get("error"):
                    print(f"Fehler beim Abruf der Mitgliederliste: {data}")
                    return []

                members = []
                for member in data.get("list", []):
                    val = member.get("v")
                    name = member.get("n", "").strip()
                    if val and str(val) != "0":
                        members.append({"id": val, "name": name})
                return members
            except Exception as e:
                print(f"Fehler beim Parsen der Mitglieder: {e}")
        return []

    def _fetch_best_times_for_variant(self, swimmer_ids, variant):
        ajax_url = self.base_url + "ajax.php"

        all_rows = []
        for index, swimmer_id in enumerate(swimmer_ids, start=1):
            print(
                f"[{index}/{len(swimmer_ids)}] Lade {variant['label']}-Bestzeiten für Schwimmer-ID {swimmer_id}..."
            )
            ajax_payload = {
                "func": "best/swrbest",
                "data": json.dumps(self._build_best_times_payload(swimmer_id, variant["list_value"]))
            }

            response = self.session.post(ajax_url, data=ajax_payload)
            if response.status_code != 200:
                print(f"Fehler bei Schwimmer-ID {swimmer_id}: {response.status_code}")
                continue

            rows = self._parse_ajax_response(response.text)
            if not rows:
                print(f"Keine Daten für Schwimmer-ID {swimmer_id} extrahiert.")
                continue

            all_rows = self._merge_rows(all_rows, rows)

        if not all_rows:
            return None

        print(f"{variant['label']}-Daten erfolgreich empfangen!")
        return all_rows

    def fetch_best_times(self, swimmer_ids=None):
        print("Rufe Bestzeiten über natives Protokoll ab...")

        swimmers = list(swimmer_ids) if swimmer_ids else [member["id"] for member in self.fetch_members()]
        if not swimmers:
            print("Keine Schwimmer gefunden.")
            return {}

        results = {}
        for variant in BEST_TIME_VARIANTS:
            print(f"\n--- Exportiere {variant['label']} separat ---")
            rows = self._fetch_best_times_for_variant(swimmers, variant)
            if rows:
                results[variant["key"]] = rows
            else:
                print(f"Keine {variant['label']}-Ergebnisse extrahiert.")

        return results

    def _parse_ajax_response(self, text):
        # WebClub AJAX antwortet oft mit JSON, das HTML-Schnipsel enthält
        print(f"Antwort-Länge: {len(text)} Zeichen")
        html_content = ""

        try:
            resp_json = json.loads(text)
            # WebClub liefert die HTML-Tabelle je nach Endpoint unter unterschiedlichen Schlüsseln.
            html_content = (
                resp_json.get("c", "")
                or resp_json.get("html", "")
                or resp_json.get("table", "")
                or resp_json.get("content", "")
            )

            if not html_content and "data" in resp_json:
                d = resp_json["data"]
                if isinstance(d, dict):
                    html_content = d.get("html", "") or d.get("table", "") or d.get("content", "")
                elif isinstance(d, str):
                    html_content = d

            if not html_content:
                html_content = text
        except Exception:
            html_content = text

        if isinstance(html_content, str):
            html_content = html.unescape(html_content)

        soup = BeautifulSoup(html_content, "html.parser")
        
        # Manchmal ist es keine klassische <table>, sondern eine Liste oder Divs
        # Wir suchen nach Tabellen ODER Zeilen-Containern
        table = soup.find("table")
        rows = []
        
        if table:
            print("Tabelle im HTML gefunden.")
            for tr in table.find_all("tr"):
                row = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if row: rows.append(row)
        else:
            # Fallback: Suche nach DIV-basierten Zeilen (oft bei mobilen Ansichten)
            print("Keine klassische Tabelle gefunden, suche nach Alternativstrukturen...")
            # Suche nach allen Elementen, die wie Datenzeilen aussehen könnten
            # (Das ist sehr generisch, aber oft effektiv als letzter Versuch)
            div_rows = soup.find_all(["div", "li"], class_=lambda c: c and ("row" in c.lower() or "item" in c.lower()))
            for dr in div_rows:
                row = [span.get_text(strip=True) for span in dr.find_all(["span", "div"]) if span.get_text(strip=True)]
                if row: rows.append(row)

        if not rows:
            print("Konnte keine strukturierten Daten extrahieren.")
            # Speichere die rohe Antwort zur Analyse
            with open("debug_raw_ajax.txt", "w", encoding="utf-8") as f:
                f.write(text)
            print("Die rohe Antwort wurde in 'debug_raw_ajax.txt' gespeichert.")
            return None

        return rows

    def save_csv(self, data, filename="bestzeiten_turbo.csv"):
        if not data:
            return

        output_path = filename if os.path.isabs(filename) else os.path.join(OUTPUT_DIR, filename)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerows(data)
        print(f"Erfolg! {len(data)} Zeilen in '{output_path}' gespeichert.")

if __name__ == "__main__":
    print("--- WebClub Turbo-Crawler (Native Protocol) ---")
    
    # Versuche Zugangsdaten aus Umgebungsvariablen zu laden (.env Support)
    u = os.getenv("WEBCLUB_USER")
    p = os.getenv("WEBCLUB_PASSWORD")
    
    # Falls nicht gesetzt, interaktiv abfragen
    if not u:
        u = input("Benutzername: ")
    if not p:
        p = getpass.getpass("Passwort: ")
    
    crawler = WebClubTurboCrawler()
    if crawler.login(u, p):
        members = crawler.fetch_members()
        selected_members = crawler._prompt_for_swimmers(members) if members else []
        results_by_variant = crawler.fetch_best_times([member["id"] for member in selected_members])
        if results_by_variant:
            for variant in BEST_TIME_VARIANTS:
                rows = results_by_variant.get(variant["key"])
                if rows:
                    crawler.save_csv(rows, variant["filename"])
        else:
            print("Keine Ergebnisse extrahiert.")
