import csv
from pathlib import Path


def save_rows_to_csv(data, filename, delimiter="\t"):
    if not data:
        return

    output_path = Path(filename)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=delimiter)
        writer.writerows(data)

    print(f"Erfolg! {len(data)} Zeilen in '{output_path}' gespeichert.")
