#!/usr/bin/env python3
"""
update_all.py – Spiegel für Gesetze-im-Internet

Funktionen
──────────
1.  gii-toc.xml laden
2.  jede xml.zip holen und als JSON speichern      → data/<code>.json
3.  Paragraphen erkennen und einzeln exportieren   → data/paragraphs/<code>/<id>.json
4.  nur bei Änderungen committen & (im CI) pushen
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import zipfile
from subprocess import CalledProcessError, run
from typing import Any, Dict, List

import xml.etree.ElementTree as ET
import requests
import xmltodict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ──────────────────────────────────────────────────────────────────────────────
# Konstante Pfade
# ──────────────────────────────────────────────────────────────────────────────
BASE = pathlib.Path(__file__).resolve().parent
DATA = BASE.parent / "data"
DATA.mkdir(exist_ok=True)

TOC_URL = "https://www.gesetze-im-internet.de/gii-toc.xml"

# ──────────────────────────────────────────────────────────────────────────────
# HTTP-Session mit Retry
# ──────────────────────────────────────────────────────────────────────────────
session = requests.Session()
session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        ),
    ),
)


def get(url: str) -> bytes:
    """GET mit großzügigem Timeout + Retry-Session"""
    return session.get(url, timeout=(30, 120)).content


def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Paragraph-Extraktion (speziell für GiI-XML)
# ──────────────────────────────────────────────────────────────────────────────
PARA_ID_RE = re.compile(r"§\s*([0-9]+[a-zA-Z0-9]*)")


def extract_paragraphs(xml_bytes: bytes) -> List[Dict[str, str]]:
    """
    Liefert eine Liste von Dicts: {id, heading, text}
    • Ein Paragraph ist ein <norm>, dessen <enbez> mit '§' beginnt.
    • heading  = erster <titel>-Text unterhalb der <metadaten>
    • text     = zusammengesetzter Plain-Text aller <P>-Elemente
    """
    docs: list[Dict[str, str]] = []

    # <!DOCTYPE …> stört expat nicht; ET.fromstring reicht
    root = ET.fromstring(xml_bytes)

    for norm in root.iter("norm"):
        enbez_elem = norm.find("./metadaten/enbez")
        if enbez_elem is None or not (en_text := (enbez_elem.text or "").strip()).startswith("§"):
            continue

        m = PARA_ID_RE.search(en_text)
        if not m:
            continue
        pid = m.group(1)  # z. B. '242' oder '90a'

        heading_elem = norm.find("./metadaten/titel")
        heading = (heading_elem.text or "").strip() if heading_elem is not None else ""

        # Inhalt sammeln
        lines: list[str] = []
        for p in norm.iter("P"):
            if p.text and p.text.strip():
                lines.append(p.text.strip())
        text = "\n".join(lines).strip()

        docs.append({"id": pid, "heading": heading, "text": text})

    return docs


def export_paragraphs(code: str, xml_bytes: bytes) -> bool:
    """
    Schreibt jede Paragraph-Dict als
       data/paragraphs/<code>/<id>.json
    Rückgabe: True, wenn mind. eine Datei neu/aktualisiert wurde.
    """
    outdir = DATA / "paragraphs" / code.lower()
    outdir.mkdir(parents=True, exist_ok=True)

    changed = False
    for para in extract_paragraphs(xml_bytes):
        target = outdir / f"{para['id']}.json"
        blob = json.dumps(para, ensure_ascii=False, separators=(",", ":")).encode()

        if not target.exists() or sha1(target.read_bytes()) != sha1(blob):
            target.write_bytes(blob)
            changed = True
            print(f"    ↪︎ §{para['id']} ({code.upper()}) exportiert")

    return changed


# ──────────────────────────────────────────────────────────────────────────────
# Haupt-Routine
# ──────────────────────────────────────────────────────────────────────────────
def main() -> bool:
    changed_any = False

    print("⤓  Lade Inhaltsverzeichnis …")
    toc_xml = get(TOC_URL)
    toc_root = ET.fromstring(toc_xml)

    for link in toc_root.findall(".//item/link"):
        url = (link.text or "").strip()
        if not url.endswith("/xml.zip"):
            continue

        code = url.split("/")[-2].lower()
        print(f"• {code.upper()} – lade xml.zip …")

        try:
            z_bytes = get(url)
        except Exception as err:
            print(f"  ⚠️  Download-Fehler: {err}")
            continue

        with zipfile.ZipFile(io.BytesIO(z_bytes)) as zf:
            try:
                xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
            except StopIteration:
                print("  ⚠️  Keine XML im Archiv")
                continue
            xml_bytes = zf.read(xml_name)

        # 1) Komplettes Gesetz als kompakte JSON-Datei
        law_obj = xmltodict.parse(xml_bytes, dict_constructor=dict)
        law_blob = json.dumps(law_obj, ensure_ascii=False, separators=(",", ":")).encode()
        law_path = DATA / f"{code}.json"

        if not law_path.exists() or sha1(law_path.read_bytes()) != sha1(law_blob):
            law_path.write_bytes(law_blob)
            changed_any = True
            print(f"  ↪︎ {law_path.relative_to(DATA.parent)} aktualisiert")

        # 2) Paragraphen exportieren
        if export_paragraphs(code, xml_bytes):
            changed_any = True

    return changed_any


# ──────────────────────────────────────────────────────────────────────────────
# Git-Commit & Exit
# ──────────────────────────────────────────────────────────────────────────────
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
            print("⚠️  git commit: nichts zu committen")
    else:
        print("✓ Keine Änderungen – alle Daten aktuell")