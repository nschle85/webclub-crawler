import html
import json
from pathlib import Path

from bs4 import BeautifulSoup


def parse_ajax_response(text, debug_path: str | Path = "debug_raw_ajax.txt"):
    print(f"Antwort-Länge: {len(text)} Zeichen")
    html_content = ""

    try:
        response_json = json.loads(text)
        html_content = (
            response_json.get("c", "")
            or response_json.get("html", "")
            or response_json.get("table", "")
            or response_json.get("content", "")
        )

        if not html_content and "data" in response_json:
            data = response_json["data"]
            if isinstance(data, dict):
                html_content = data.get("html", "") or data.get("table", "") or data.get("content", "")
            elif isinstance(data, str):
                html_content = data

        if not html_content:
            html_content = text
    except Exception:
        html_content = text

    if isinstance(html_content, str):
        html_content = html.unescape(html_content)

    soup = BeautifulSoup(html_content, "html.parser")
    table = soup.find("table")
    rows = []

    if table:
        print("Tabelle im HTML gefunden.")
        for table_row in table.find_all("tr"):
            row = [cell.get_text(" ", strip=True) for cell in table_row.find_all(["td", "th"])]
            if row:
                rows.append(row)
    else:
        print("Keine klassische Tabelle gefunden, suche nach Alternativstrukturen...")
        div_rows = soup.find_all(
            ["div", "li"],
            class_=lambda class_name: class_name and ("row" in class_name.lower() or "item" in class_name.lower()),
        )
        for div_row in div_rows:
            row = [
                span.get_text(strip=True)
                for span in div_row.find_all(["span", "div"])
                if span.get_text(strip=True)
            ]
            if row:
                rows.append(row)

    if not rows:
        print("Konnte keine strukturierten Daten extrahieren.")
        Path(debug_path).write_text(text, encoding="utf-8")
        print(f"Die rohe Antwort wurde in '{debug_path}' gespeichert.")
        return None

    return rows


def merge_rows(all_rows, new_rows):
    if not new_rows:
        return all_rows

    if not all_rows:
        return list(new_rows)

    header = all_rows[0]
    start_index = 1 if new_rows and new_rows[0] == header else 0
    all_rows.extend(new_rows[start_index:])
    return all_rows
