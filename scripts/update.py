#!/usr/bin/env python3
import requests, xmltodict, json, pathlib, datetime as dt, subprocess, os

LAWS = {
    "bgb": "https://www.gesetze-im-internet.de/bgb/bgb.xml",
    "stgb": "https://www.gesetze-im-internet.de/stgb/stgb.xml",
    # weitere URLs hier ergänzen
}

out_dir = pathlib.Path("data")
out_dir.mkdir(exist_ok=True)

changed = False
for short, url in LAWS.items():
    xml = requests.get(url, timeout=60).text
    obj = xmltodict.parse(xml)
    json_path = out_dir / f"{short}.json"
    new_json = json.dumps(obj, ensure_ascii=False, indent=2)
    if not json_path.exists() or json_path.read_text() != new_json:
        json_path.write_text(new_json)
        changed = True
        print(f"🔄  {short}.json aktualisiert")

if changed:
    ts = dt.datetime.utcnow().isoformat(timespec="seconds")
    subprocess.run(["git", "config", "user.name", "law-bot"], check=True)
    subprocess.run(["git", "config", "user.email", "bot@example.com"], check=True)
    subprocess.run(["git", "add", "data"], check=True)
    subprocess.run(["git", "commit", "-m", f"Auto-Update {ts}Z"], check=True)
else:
    print("✅  Keine Änderungen")
