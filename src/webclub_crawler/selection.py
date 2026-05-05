import re
from collections.abc import Mapping


def _item_value(item, id_key):
    if isinstance(item, Mapping):
        return str(item[id_key])
    return str(getattr(item, id_key))


def _item_name(item):
    if isinstance(item, Mapping):
        return str(item["name"])
    return str(getattr(item, "name"))


def prompt_for_swimmers(swimmers, id_key="id", empty_message="No swimmers found."):
    if not swimmers:
        print(empty_message)
        return []

    print("\nAvailable swimmers:")
    for index, swimmer in enumerate(swimmers, start=1):
        print(f"{index:>3}: {_item_name(swimmer)}")

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
                        value = _item_value(swimmer, id_key)
                        if value not in seen_values:
                            selected.append(swimmer)
                            seen_values.add(value)
                    else:
                        invalid_tokens.append(token)
                        break
                continue

            if token.isdigit():
                idx = int(token)
                if 1 <= idx <= len(swimmers):
                    swimmer = swimmers[idx - 1]
                    value = _item_value(swimmer, id_key)
                    if value not in seen_values:
                        selected.append(swimmer)
                        seen_values.add(value)
                else:
                    invalid_tokens.append(token)
                continue

            matches = [swimmer for swimmer in swimmers if token.lower() in _item_name(swimmer).lower()]
            if len(matches) == 1:
                swimmer = matches[0]
                value = _item_value(swimmer, id_key)
                if value not in seen_values:
                    selected.append(swimmer)
                    seen_values.add(value)
            elif len(matches) > 1:
                invalid_tokens.append(f"{token} (matches multiple swimmers)")
            else:
                invalid_tokens.append(token)

        if selected and not invalid_tokens:
            print("Selected swimmers:")
            for swimmer in selected:
                print(f"- {_item_name(swimmer)}")
            return selected

        if invalid_tokens:
            print("Could not resolve:", ", ".join(invalid_tokens))
        else:
            print("No valid swimmers selected.")
