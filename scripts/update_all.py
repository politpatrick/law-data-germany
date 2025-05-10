#!/usr/bin/env python3
"""
update_all.py
=============

• Lädt das Inhaltsverzeichnis (gii-toc.xml) von Gesetze-im-Internet.
• Holt jede xml.zip, konvertiert die enthaltene XML-Datei mit xmltodict
  nach JSON und speichert sie unter  data/<code>.json.
• Exportiert zusätzlich jeden Paragraphen als  data/paragraphs/<code>/<id>.json.
• Commit + Git-Push erfolgen nur, wenn sich mindestens eine Datei geändert hat.

Benötigt:
  pip install requests xmltodict
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import pathlib
import zipfile
from subprocess import CalledProcessError, run
from typing import Any, Dict, List

import requests
import xml.etree.ElementTree as ET
import xmltodict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Pfade & Konstanten
# ---------------------------------------------------------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

TOC_URL = "https://www.gesetze-im-internet.de/gii-toc.xml"

# ---------------------------------------------------------------------------
# HTTP-Session mit Retry (5 Versuche, exponentieller Backoff)
# ---------------------------------------------------------------------------
retry_strategy = Retry(
    total=5,
    backoff_factor=1,            # 1s, 2s, 4s, 8s, 16s
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)
session = requests.Session()
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)


def get(url: str) -> bytes:
    """GET mit verlängertem Timeout und Retry-Session."""
    return session.get(url, timeout=(30, 120)).content


def sha1(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()


# ---------------------------------------------------------------------------
# Paragraph-Export
# ---------------------------------------------------------------------------
def export_paragraphs(code: str, law_obj: Dict[str, Any]) -> bool:
    """
    Schreibt für jedes Paragraph-Objekt eine Datei
    data/paragraphs/<code>/<id>.json.
    Gibt True zurück, wenn mindestens eine Datei neu/aktualisiert wurde.
    """
    para_dir = DATA_DIR / "paragraphs" / code.lower()
    para_dir.mkdir(parents=True, exist_ok=True)

    changed_local = False
    paragraphs: List[Dict[str, Any]] = law_obj.get("paragraphs", [])
    for para in paragraphs:
        pid = str(
            para.get("id")
            or para.get("@id")
            or para.get("identifier")
            or ""
        ).strip()
        if not pid:
            continue  # ohne ID keine eindeutige Datei

        target = para_dir / f"{pid}.json"
        blob = json.dumps(
            para,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()

        if not target.exists() or sha1(target.read_bytes()) != sha1(blob):
            target.write_bytes(blob)
            changed_local = True
            print(f"    ↪︎ Paragraph {code.upper()} §{pid} exportiert")

    return changed_local


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------
def main() -> bool:
    changed = False

    # 1. Inhaltsverzeichnis laden
    print("⤓  Lade gii-toc.xml …")
    toc_xml = get(TOC_URL)
    root = ET.fromstring(toc_xml)

    # 2. Für jedes Gesetz die xml.zip verarbeiten
    for link in root.findall(".//item/link"):
        url = link.text.strip()
        if not url.endswith("/xml.zip"):
            continue
        code = url.split("/")[-2].lower()  # z. B. "bgb"
        print(f"• {code.upper()} …")

        # 2.1 ZIP laden und XML extrahieren
        try:
            z_bytes = get(url)
        except Exception as e:
            print(f"  ⚠️  Download fehlgeschlagen: {e}")
            continue

        with zipfile.ZipFile(io.BytesIO(z_bytes)) as zf:
            try:
                xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
            except StopIteration:
                print("  ⚠️  Keine XML-Datei im Archiv")
                continue
            xml_bytes = zf.read(xml_name)

        # 2.2 XML → JSON (kompakt) und speichern
        law_obj = xmltodict.parse(xml_bytes)
        blob = json.dumps(
            law_obj,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        law_path = DATA_DIR / f"{code}.json"

        if not law_path.exists() or sha1(law_path.read_bytes()) != sha1(blob):
            law_path.write_bytes(blob)
            changed = True
            print(f"  ↪︎ {law_path.relative_to(DATA_DIR.parent)} aktualisiert")

        # 2.3 Paragraph-Dateien erzeugen
        changed |= export_paragraphs(code, law_obj)

    return changed


# ---------------------------------------------------------------------------
# Ausführung & Git-Commit
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        updated = main()
    except Exception as exc:
        print(f"❌  Abbruch: {exc}")
        raise SystemExit(1)

    if updated:
        ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        try:
            run(["git", "config", "user.name", "law-bot"], check=True)
            run(["git", "config", "user.email", "bot@example.com"], check=True)
            run(["git", "add", "data"], check=True)
            run(["git", "commit", "-m", f"Auto-Update {ts}"], check=True)
            print("✓ Änderungen committed")
        except CalledProcessError:
            print("⚠️  git commit: nichts zu committen (Race Condition?)")
    else:
        print("✓ Keine Änderungen – alles aktuell")
