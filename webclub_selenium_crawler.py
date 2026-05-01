import time
import getpass
import csv
import os
import re
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# Lade Umgebungsvariablen aus .env Datei falls vorhanden
load_dotenv()


DEFAULT_CLUB_ID = "1"
DEFAULT_BASE_URL = os.getenv("WEBCLUB_BASE_URL")

def _normalize_base_url(base_url):
    return base_url.rstrip("/") + "/"

def _resolve_base_url(base_url=None):
    resolved_base_url = (base_url or DEFAULT_BASE_URL or "").strip()
    if not resolved_base_url:
        raise ValueError("WEBCLUB_BASE_URL must be set in .env or passed as base_url.")
    return _normalize_base_url(resolved_base_url)

class WebClubCrawler:
    def __init__(self, headless=True, base_url=None):
        self.base_url = _resolve_base_url(base_url)
        self.chrome_options = Options()
        if headless:
            self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--window-size=1920,1080")
        self.chrome_options.add_argument("--start-maximized")
        self.chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self.chrome_options)
        # Navigator.webdriver-Flag entfernen
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        self.wait = WebDriverWait(self.driver, 20)

    def _create_authenticated_session(self):
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.driver.execute_script("return navigator.userAgent;") or "Mozilla/5.0",
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest"
        })

        for cookie in self.driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        return session

    def _fetch_swimmers_via_ajax(self, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
        session = self._create_authenticated_session()
        ajax_url = self.base_url + "ajax.php"
        payload = {
            "func": "best/swrgetswr",
            "data": json.dumps({
                "ausSTR": club_id,
                "ausSTA": branch_id,
                "ausGRP": group_id,
                "actonly": 1,
                "dsvonly": 1
            })
        }

        response = session.post(ajax_url, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError(f"Mitgliederliste konnte nicht geladen werden: {data}")

        swimmers = []
        for member in data.get("list", []):
            value = str(member.get("v", "")).strip()
            name = (member.get("n", "") or "").strip()
            if value and value != "0" and name:
                swimmers.append({"value": value, "name": name})

        return swimmers

    def _find_swimmer_select_for_apply(self):
        candidate_ids = ["pers", "ausSWR", "swr", "swimmer"]

        for candidate_id in candidate_ids:
            try:
                element = self.driver.find_element(By.ID, candidate_id)
                Select(element)
                return element
            except Exception:
                continue

        for element in self.driver.find_elements(By.TAG_NAME, "select"):
            element_id = (element.get_attribute("id") or "").strip().lower()
            element_name = (element.get_attribute("name") or "").strip().lower()
            if "pers" in element_id or "pers" in element_name or "swr" in element_id or "swr" in element_name:
                try:
                    Select(element)
                    return element
                except Exception:
                    continue

        return None

    def _find_swimmer_checkboxes_for_apply(self):
        checkbox_xpath = "//form[@id='formswrbest']//input[@type='checkbox' and @name='swr']"
        checkboxes = []
        for element in self.driver.find_elements(By.XPATH, checkbox_xpath):
            try:
                if element.is_enabled():
                    checkboxes.append(element)
            except Exception:
                continue
        return checkboxes

    def _set_select_value_with_events(self, select_element, value):
        self.driver.execute_script(
            """
            const select = arguments[0];
            const value = arguments[1];
            select.value = value;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
            if (window.jQuery) {
                window.jQuery(select).trigger('change');
            }
            """,
            select_element,
            str(value)
        )

    def _apply_swimmer_selection(self, swimmers):
        if not swimmers:
            return False

        checkbox_elements = self._find_swimmer_checkboxes_for_apply()
        if checkbox_elements:
            try:
                clear_button = self.driver.find_element(By.XPATH, "//form[@id='formswrbest']//button[@name='listNONE']")
                self.driver.execute_script("arguments[0].click();", clear_button)
                time.sleep(0.5)
            except Exception:
                for checkbox in checkbox_elements:
                    try:
                        if checkbox.is_selected():
                            self.driver.execute_script("arguments[0].click();", checkbox)
                    except Exception:
                        continue

            selected_any = False
            for swimmer in swimmers:
                checkbox = self.driver.find_element(
                    By.XPATH,
                    f"//form[@id='formswrbest']//input[@type='checkbox' and @name='swr' and @value='{swimmer['value']}']"
                )
                if not checkbox.is_selected():
                    self.driver.execute_script("arguments[0].click();", checkbox)
                selected_any = True

            return selected_any

        swimmer_select = self._find_swimmer_select_for_apply()
        if swimmer_select and len(swimmers) == 1:
            self._set_select_value_with_events(swimmer_select, swimmers[0]["value"])
            return True

        return False

    def _configure_combined_results_view(self):
        try:
            new_page_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausNEWPAGE"))))
            if (new_page_select.first_selected_option.get_attribute("value") or "1") != "0":
                new_page_select.select_by_value("0")
                time.sleep(0.5)
            return True
        except Exception as e:
            print(f"Hint: Could not switch 'Neue Seite für jeden Schwimmer' to 'Nein': {e}")
            return False

    def _click_auswertung_button(self):
        print("Trying to open evaluation...")
        form = None

        try:
            form = self.driver.find_element(By.ID, "formswrbest")
        except Exception:
            form = None

        button_locators = [
            (By.ID, "butAUSWERTUNG"),
            (By.NAME, "butAUSWERTUNG"),
            (By.XPATH, "//form[@id='formswrbest']//button[contains(normalize-space(.), 'Auswertung') or contains(normalize-space(.), 'Anzeigen')]"),
            (By.XPATH, "//form[@id='formswrbest']//input[(@type='submit' or @type='button') and (contains(@value, 'Auswertung') or contains(@value, 'Anzeigen'))]"),
        ]

        for locator in button_locators:
            try:
                buttons = self.driver.find_elements(*locator)
            except Exception:
                buttons = []

            for button in buttons:
                try:
                    if not button.is_displayed() or not button.is_enabled():
                        continue
                    self.driver.execute_script("arguments[0].click();", button)
                    return True
                except Exception:
                    continue

        if form is not None:
            try:
                self.driver.execute_script(
                    """
                    const form = arguments[0];
                    if (typeof form.requestSubmit === 'function') {
                        form.requestSubmit();
                    } else {
                        form.submit();
                    }
                    """,
                    form,
                )
                return True
            except Exception as e:
                print(f"Hint: form submit fallback failed: {e}")

        return False

    def _prompt_for_swimmers(self, swimmers):
        if not swimmers:
            print("No swimmers found on the page.")
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
            seen_values = set()
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
                            if swimmer["value"] not in seen_values:
                                selected.append(swimmer)
                                seen_values.add(swimmer["value"])
                        else:
                            invalid_tokens.append(token)
                            break
                    continue

                if token.isdigit():
                    idx = int(token)
                    if 1 <= idx <= len(swimmers):
                        swimmer = swimmers[idx - 1]
                        if swimmer["value"] not in seen_values:
                            selected.append(swimmer)
                            seen_values.add(swimmer["value"])
                    else:
                        invalid_tokens.append(token)
                    continue

                matches = [swimmer for swimmer in swimmers if token.lower() in swimmer["name"].lower()]
                if len(matches) == 1:
                    swimmer = matches[0]
                    if swimmer["value"] not in seen_values:
                        selected.append(swimmer)
                        seen_values.add(swimmer["value"])
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

    def _extract_tables_from_current_page(self):
        print("Extract data from current page...")
        all_data = []
        try:
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            print(f"Tables found on page: {len(tables)}")

            for i, table in enumerate(tables):
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) > 1:
                    print(f"Process table #{i} ({len(rows)} rows)...")
                    for row in rows:
                        cols = row.find_elements(By.XPATH, "./td | ./th")
                        data_row = [col.text.strip() for col in cols]
                        if any(data_row) and len("".join(data_row)) > 2:
                            all_data.append(data_row)
        except Exception as e:
            print(f"Error during extraction: {e}")

        print(f"Collected {len(all_data)} rows from current page.")
        return all_data

    def _merge_rows(self, all_rows, new_rows):
        if not new_rows:
            return all_rows

        if not all_rows:
            return list(new_rows)

        header = all_rows[0]
        start_index = 1 if new_rows and new_rows[0] == header else 0
        all_rows.extend(new_rows[start_index:])
        return all_rows

    def login(self, username, password):
        print(f"Versuche Login für {username}...")
        self.driver.get(self.base_url)
        
        # Login Dialog öffnen
        try:
            btn = self.wait.until(EC.element_to_be_clickable((By.ID, "login")))
        except:
            btn = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Anmelden')]")))
        
        self.driver.execute_script("arguments[0].click();", btn)
        
        # Felder ausfüllen
        user_field = self.wait.until(EC.visibility_of_element_located((By.ID, "username")))
        pwd_field = self.driver.find_element(By.ID, "pwd")
        submit_btn = self.driver.find_element(By.ID, "butLOGIN")
        
        user_field.clear()
        user_field.send_keys(username)
        pwd_field.clear()
        pwd_field.send_keys(password)
        self.driver.execute_script("arguments[0].click();", submit_btn)
        time.sleep(5)
        print("Login-Prozess abgeschlossen.")

    def get_best_times(self, target_url=None):
        target_url = target_url or self.base_url + "swrbest.php"
        print(f"Navigiere zu {target_url}...")
        self.driver.get(target_url)
        time.sleep(3)
        
        try:
            print("Wähle TSV Erding als Startrecht und Stammverein...")
            # Startrecht auswählen
            str_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTR"))))
            str_select.select_by_value("1") # TSV Erding
            
            # Stammverein auswählen
            sta_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTA"))))
            sta_select.select_by_value("1") # TSV Erding
            
            print("TSV Erding erfolgreich ausgewählt.")
        except Exception as e:
            print(f"Hinweis: Konnte TSV Erding nicht automatisch auswählen: {e}")

        try:
            print("Wähle Kurzbahn und Langbahn...")
            for value in ["0", "1"]:
                cb = self.wait.until(EC.presence_of_element_located(
                    (By.XPATH, f"//input[@name='list' and @value='{value}']")
                ))
                if not cb.is_selected():
                    self.driver.execute_script("arguments[0].click();", cb)
            print("Kurzbahn und Langbahn ausgewählt.")
        except Exception as e:
            print(f"Hinweis: Konnte Kurzbahn/Langbahn nicht automatisch auswählen: {e}")

        club_id = "1"
        branch_id = "1"
        group_id = "0"
        try:
            club_id = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTR")))).first_selected_option.get_attribute("value") or "1"
        except Exception:
            pass
        try:
            branch_id = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTA")))).first_selected_option.get_attribute("value") or "0"
        except Exception:
            pass
        try:
            group_id = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausGRP")))).first_selected_option.get_attribute("value") or "0"
        except Exception:
            pass

        try:
            swimmers = self._fetch_swimmers_via_ajax(club_id=club_id, branch_id=branch_id, group_id=group_id)
            can_apply_swimmers = bool(
                self._find_swimmer_checkboxes_for_apply() or self._find_swimmer_select_for_apply()
            )
        except Exception as e:
            print(f"Hinweis: Konnte keine Schwimmerliste automatisch laden: {e}")
            can_apply_swimmers, swimmers = False, []

        selected_swimmers = self._prompt_for_swimmers(swimmers) if swimmers else []

        if can_apply_swimmers and selected_swimmers:
            print("\n--- SEMI-MANUAL MODE ---")
            print("The script selects all chosen swimmers for you.")
            print("When you press ENTER in the console, the script will open the combined evaluation automatically.")

            print("\nSelecting swimmers:")
            for swimmer in selected_swimmers:
                print(f"- {swimmer['name']}")

            self._configure_combined_results_view()
            if not self._apply_swimmer_selection(selected_swimmers):
                print("Could not apply the swimmer selection automatically.")
            else:
                time.sleep(1)

            input("Press ENTER to open the combined results for the selected swimmers...")
            if not self._click_auswertung_button():
                print("Could not trigger 'Auswertung Anzeigen' automatically.")
                return []

            time.sleep(3)

            with open("debug_final_page.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print("Current page source saved to 'debug_final_page.html'.")

            return self._extract_tables_from_current_page()

        print("\n--- MANUAL MODE ---")
        print("1. Please set everything in the browser manually (club, swimmer, period).")
        print("2. When ready, press ENTER here. The script will click 'Auswertung Anzeigen' for you.")
        input("\nPress ENTER to open the results with your current GUI selection...")

        if not self._click_auswertung_button():
            print("Could not trigger 'Auswertung Anzeigen' automatically.")
            return []

        time.sleep(3)

        with open("debug_final_page.html", "w", encoding="utf-8") as f:
            f.write(self.driver.page_source)
        print("Page source saved to 'debug_final_page.html'.")

        return self._extract_tables_from_current_page()

    def save_to_csv(self, data, filename="bestzeiten.csv"):
        if not data:
            print("Keine Daten zum Speichern gefunden.")
            return
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)
        print(f"Gespeichert in {filename}")

    def close(self):
        self.driver.quit()

if __name__ == "__main__":
    # Versuche Zugangsdaten aus Umgebungsvariablen zu laden (.env Support)
    user = os.getenv("WEBCLUB_USER")
    pwd = os.getenv("WEBCLUB_PASSWORD")
    
    # Falls nicht gesetzt, interaktiv abfragen
    if not user:
        user = input("Benutzername: ")
    if not pwd:
        pwd = getpass.getpass("Passwort: ")
    
    # Auf False setzen, um die Auswahl im Browser-Fenster treffen zu können
    crawler = WebClubCrawler(headless=False) 
    try:
        crawler.login(user, pwd)
        data = crawler.get_best_times()
        crawler.save_to_csv(data)
    finally:
        crawler.close()
