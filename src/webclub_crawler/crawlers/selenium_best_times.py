import json
import time
from pathlib import Path

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from webclub_crawler.config import DEFAULT_CLUB_ID, resolve_base_url
from webclub_crawler.exporters import save_rows_to_csv
from webclub_crawler.parsers import merge_rows
from webclub_crawler.selection import prompt_for_swimmers


class WebClubCrawler:
    def __init__(self, headless=True, base_url=None):
        self.base_url = resolve_base_url(base_url)
        self.chrome_options = Options()
        if headless:
            self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--window-size=1920,1080")
        self.chrome_options.add_argument("--start-maximized")
        self.chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.chrome_options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=self.chrome_options)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        self.wait = WebDriverWait(self.driver, 20)

    def _create_authenticated_session(self):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self.driver.execute_script("return navigator.userAgent;") or "Mozilla/5.0",
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        for cookie in self.driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"])

        return session

    def _fetch_swimmers_via_ajax(self, club_id=DEFAULT_CLUB_ID, branch_id="0", group_id="0"):
        session = self._create_authenticated_session()
        payload = {
            "func": "best/swrgetswr",
            "data": json.dumps(
                {
                    "ausSTR": club_id,
                    "ausSTA": branch_id,
                    "ausGRP": group_id,
                    "actonly": 1,
                    "dsvonly": 1,
                }
            ),
        }

        response = session.post(self.base_url + "ajax.php", data=payload, timeout=20)
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
            str(value),
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
                    f"//form[@id='formswrbest']//input[@type='checkbox' and @name='swr' and @value='{swimmer['value']}']",
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
        except Exception as exc:
            print(f"Hint: Could not switch 'Neue Seite für jeden Schwimmer' to 'Nein': {exc}")
            return False

    def _click_auswertung_button(self):
        print("Trying to open evaluation...")
        try:
            form = self.driver.find_element(By.ID, "formswrbest")
        except Exception:
            form = None

        button_locators = [
            (By.ID, "butAUSWERTUNG"),
            (By.NAME, "butAUSWERTUNG"),
            (
                By.XPATH,
                "//form[@id='formswrbest']//button[contains(normalize-space(.), 'Auswertung') "
                "or contains(normalize-space(.), 'Anzeigen')]",
            ),
            (
                By.XPATH,
                "//form[@id='formswrbest']//input[(@type='submit' or @type='button') "
                "and (contains(@value, 'Auswertung') or contains(@value, 'Anzeigen'))]",
            ),
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
            except Exception as exc:
                print(f"Hint: form submit fallback failed: {exc}")

        return False

    def _prompt_for_swimmers(self, swimmers):
        return prompt_for_swimmers(swimmers, id_key="value", empty_message="No swimmers found on the page.")

    def _extract_tables_from_current_page(self):
        print("Extract data from current page...")
        all_data = []
        try:
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            print(f"Tables found on page: {len(tables)}")

            for index, table in enumerate(tables):
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) > 1:
                    print(f"Process table #{index} ({len(rows)} rows)...")
                    for row in rows:
                        cols = row.find_elements(By.XPATH, "./td | ./th")
                        data_row = [col.text.strip() for col in cols]
                        if any(data_row) and len("".join(data_row)) > 2:
                            all_data.append(data_row)
        except Exception as exc:
            print(f"Error during extraction: {exc}")

        print(f"Collected {len(all_data)} rows from current page.")
        return all_data

    def _merge_rows(self, all_rows, new_rows):
        return merge_rows(all_rows, new_rows)

    def login(self, username, password):
        print(f"Versuche Login für {username}...")
        self.driver.get(self.base_url)

        try:
            button = self.wait.until(EC.element_to_be_clickable((By.ID, "login")))
        except Exception:
            button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(., 'Anmelden')]")))

        self.driver.execute_script("arguments[0].click();", button)

        user_field = self.wait.until(EC.visibility_of_element_located((By.ID, "username")))
        password_field = self.driver.find_element(By.ID, "pwd")
        submit_button = self.driver.find_element(By.ID, "butLOGIN")

        user_field.clear()
        user_field.send_keys(username)
        password_field.clear()
        password_field.send_keys(password)
        self.driver.execute_script("arguments[0].click();", submit_button)
        time.sleep(5)
        print("Login-Prozess abgeschlossen.")

    def get_best_times(self, target_url=None):
        target_url = target_url or self.base_url + "swrbest.php"
        print(f"Navigiere zu {target_url}...")
        self.driver.get(target_url)
        time.sleep(3)

        try:
            print("Wähle TSV Erding als Startrecht und Stammverein...")
            str_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTR"))))
            str_select.select_by_value("1")

            sta_select = Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTA"))))
            sta_select.select_by_value("1")

            print("TSV Erding erfolgreich ausgewählt.")
        except Exception as exc:
            print(f"Hinweis: Konnte TSV Erding nicht automatisch auswählen: {exc}")

        try:
            print("Wähle Kurzbahn und Langbahn...")
            for value in ["0", "1"]:
                checkbox = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, f"//input[@name='list' and @value='{value}']"))
                )
                if not checkbox.is_selected():
                    self.driver.execute_script("arguments[0].click();", checkbox)
            print("Kurzbahn und Langbahn ausgewählt.")
        except Exception as exc:
            print(f"Hinweis: Konnte Kurzbahn/Langbahn nicht automatisch auswählen: {exc}")

        club_id = "1"
        branch_id = "1"
        group_id = "0"
        try:
            club_id = (
                Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTR"))))
                .first_selected_option.get_attribute("value")
                or "1"
            )
        except Exception:
            pass
        try:
            branch_id = (
                Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausSTA"))))
                .first_selected_option.get_attribute("value")
                or "0"
            )
        except Exception:
            pass
        try:
            group_id = (
                Select(self.wait.until(EC.presence_of_element_located((By.ID, "ausGRP"))))
                .first_selected_option.get_attribute("value")
                or "0"
            )
        except Exception:
            pass

        try:
            swimmers = self._fetch_swimmers_via_ajax(club_id=club_id, branch_id=branch_id, group_id=group_id)
            can_apply_swimmers = bool(self._find_swimmer_checkboxes_for_apply() or self._find_swimmer_select_for_apply())
        except Exception as exc:
            print(f"Hinweis: Konnte keine Schwimmerliste automatisch laden: {exc}")
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

            Path("debug_final_page.html").write_text(self.driver.page_source, encoding="utf-8")
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

        Path("debug_final_page.html").write_text(self.driver.page_source, encoding="utf-8")
        print("Page source saved to 'debug_final_page.html'.")

        return self._extract_tables_from_current_page()

    def save_to_csv(self, data, filename="bestzeiten.csv"):
        if not data:
            print("Keine Daten zum Speichern gefunden.")
            return
        save_rows_to_csv(data, filename, delimiter=",")

    def close(self):
        self.driver.quit()
