#!/usr/bin/env python3
"""
generate_index.py  –  baut index.json für PolitPatrick Law API

• durchsucht das Verzeichnis ./data/ nach <code>.json
• extrahiert (heuristisch) einen Titel aus jeder Datei
• schreibt eine sortierte Liste von Dicts nach ./data/index.json

Benötigt: Python 3.8+, Standardbibliothek
"""

import json, pathlib, re
from typing import Any

BASE_URL = "https://politpatrick.github.io/law-data-germany/data"
DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
OUT_FILE = DATA_DIR / "index.json"

# ---------------------------------------------------------------
# Hilfsfunktion: sucht rekursiv nach einem feldähnlichen "Titel"
# ---------------------------------------------------------------
TITLE_KEYS = {
    "title", "titel", "kurztitle", "kurztitel", "kurzbezeichnung",
    "langtitle", "langtitel", "langbezeichnung", "official_long_title",
}

def find_title(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                found = find_title(v)
                if found:
                    return found
            elif isinstance(v, str) and k.lower() in TITLE_KEYS:
                # HTML/Zeilenumbrüche entfernen
                return re.sub(r"\s+", " ", v.strip())
    elif isinstance(obj, list):
        for item in obj:
            found = find_title(item)
            if found:
                return found
    return None

# ---------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------
def main() -> None:
    index: list[dict[str, str]] = []

    for file in sorted(DATA_DIR.glob("*.json")):
        if file.name == "index.json":
            continue                             # eigene Datei überspringen
        code = file.stem.lower()                 # z. B. "bgb"
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            title = find_title(data) or code.upper()
        except Exception as e:
            print(f"⚠️  {file.name}: {e}")
            title = code.upper()

        index.append(
            {
                "code": code,
                "title": title,
                "link": f"{BASE_URL}/{code}.json",
            }
        )

    # alphabetisch nach code sortieren
    index.sort(key=lambda x: x["code"])

    OUT_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"index.json mit {len(index)} Einträgen erstellt → {OUT_FILE.relative_to(DATA_DIR.parent)}")

if __name__ == "__main__":
    main()
