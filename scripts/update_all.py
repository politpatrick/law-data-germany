#!/usr/bin/env python3
"""
Lädt alle xml.zip-Pakete aus gii-toc.xml, entpackt die .xml-Datei,
wandelt sie mit xmltodict in JSON und speichert sie unter data/<kürzel>.json.
Commit + Push erfolgen nur, wenn sich mindestens eine Datei geändert hat.
"""
import io, json, zipfile, hashlib, pathlib, datetime as dt
import requests, xml.etree.ElementTree as ET, xmltodict
from subprocess import run, CalledProcessError

BASE = pathlib.Path(__file__).resolve().parent
DATA = BASE.parent / "data"
DATA.mkdir(exist_ok=True)

def sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def main() -> bool:
    toc_url = "https://www.gesetze-im-internet.de/gii-toc.xml"
    toc_xml = requests.get(toc_url, timeout=60).content
    root = ET.fromstring(toc_xml)

    changed = False
    for item in root.findall(".//item"):
        link = item.findtext("link", "")
        if not link.endswith("/xml.zip"):
            continue                        # z. B. PDF-Links überspringen
        law = link.split("/")[-2]           # z. B. "bgb"
        json_path = DATA / f"{law}.json"

        # Datei laden und entpacken
        z_bytes = requests.get(link, timeout=120).content
        with zipfile.ZipFile(io.BytesIO(z_bytes)) as zf:
            xml_name = next(n for n in zf.namelist() if n.endswith(".xml"))
            xml_bytes = zf.read(xml_name)

        # XML → Dict → JSON (ohne Formatierung, spart Speicher)
        obj = xmltodict.parse(xml_bytes)
        new_json = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()

        # Nur speichern, wenn wirklich neu
        if not json_path.exists() or sha1(json_path.read_bytes()) != sha1(new_json):
            json_path.write_bytes(new_json)
            changed = True
            print(f"🔄  {law}.json aktualisiert")

    return changed

if __name__ == "__main__":
    if main():
        ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        # Git-User für den Commit setzen
        run(["git", "config", "user.name", "law-bot"], check=True)
        run(["git", "config", "user.email", "bot@example.com"], check=True)
        run(["git", "add", "data"], check=True)
        try:
            run(["git", "commit", "-m", f"Auto-Update {ts}"], check=True)
        except CalledProcessError:
            print("⚠️  git commit: nichts zu committen")
