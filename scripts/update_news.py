"""
Henter nye saker om norsk havvind med Claude (API + websøk) og oppdaterer news.json.

Autentisering: Workload Identity Federation fra GitHub Actions (ingen API-nøkkel).
SDK-en leser disse miljøvariablene automatisk:
  ANTHROPIC_FEDERATION_RULE_ID, ANTHROPIC_ORGANIZATION_ID,
  ANTHROPIC_SERVICE_ACCOUNT_ID, ANTHROPIC_WORKSPACE_ID, ANTHROPIC_IDENTITY_TOKEN_FILE
(Alternativt fungerer en vanlig ANTHROPIC_API_KEY også.)
"""

import datetime as dt
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
NEWS_FILE = ROOT / "news.json"

MODEL = os.environ.get("HAVVIND_MODEL", "claude-sonnet-5-5")
MAX_SEARCHES = int(os.environ.get("HAVVIND_MAX_SEARCHES", "8"))
MAX_NEW_ITEMS = 10
DAYS_BACK = int(os.environ.get("HAVVIND_DAYS_BACK", "10"))
CATEGORIES = {"politikk", "prosjekter", "selskaper", "kontrakter", "marked"}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = text.replace("ø", "o").replace("æ", "ae").replace("å", "a")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:50]


def norm_url(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().rstrip("/")).lower()


def build_prompt(data: dict, today: dt.date) -> str:
    since = today - dt.timedelta(days=DAYS_BACK)
    known = "\n".join(f"- {n['date']}: {n['title']} ({n.get('url','')})" for n in data["news"][:40])
    projects = "\n".join(f"- {p['name']}: {p.get('next','')}" for p in data.get("projects", []))
    return f"""Du oppdaterer «Havvindloggen», en nyhetsoversikt om havvind i Norge for en person som vil inn i bransjen om noen år.

I dag er {today.isoformat()}. Søk etter viktige nyheter publisert mellom {since.isoformat()} og i dag om:
- norsk havvindpolitikk (regjeringen, Stortinget, NVE, Enova, Statnett, utlysninger, støtteordninger)
- norske havvindprosjekter (Utsira Nord, Sørlige Nordsjø II, nye områder, Hywind)
- selskaper og kontrakter med norsk tilknytning (Equinor, Vårgrønn, Deep Wind Offshore, Ventyr, norske leverandører, verft, rådgivere)
- marked og jobber i norsk havvindbransje

Prosjektene vi følger:
{projects}

Disse sakene har vi allerede. Ikke ta dem med igjen, heller ikke samme nyhet fra en annen kilde:
{known}

Regler:
- Bare saker du faktisk har funnet i søkeresultatene, med ekte URL. Ikke finn på noe.
- Foretrekk primærkilder (regjeringen.no, nve.no, selskapenes egne sider) og etablerte medier.
- Skriv alt på norsk bokmål med egne ord. Ikke kopier setninger fra kildene.
- Maks {MAX_NEW_ITEMS} saker. Finner du ingen nye saker av betydning, returner en tom liste.

Svar til slutt med KUN en JSON-blokk i dette formatet:
```json
{{"news": [
  {{"date": "ÅÅÅÅ-MM-DD", "category": "politikk|prosjekter|selskaper|kontrakter|marked",
    "project": "prosjektnavn eller tom streng", "importance": 1,
    "title": "kort, presis tittel", "summary": "2-3 setninger", "why": "1-2 setninger om hva dette betyr for en som vil jobbe i bransjen",
    "source": "kildens navn", "url": "https://..."}}
]}}
```
importance: 3 = viktig for bransjen, 2 = verdt å vite, 1 = mindre sak."""


def ask_claude(prompt: str) -> str:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}]
    texts = []
    for _ in range(5):  # websøk kan gi "pause_turn"; fortsett i så fall
        resp = client.messages.create(model=MODEL, max_tokens=6000, tools=tools, messages=messages)
        texts.extend(b.text for b in resp.content if b.type == "text")
        u = resp.usage
        searches = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0)
        print(f"Bruk: {u.input_tokens} inn, {u.output_tokens} ut, {searches} søk")
        if resp.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
    return "\n".join(texts)


def parse_items(text: str) -> list:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{\s*\"news\".*\})", text, re.S)
    if not m:
        raise ValueError("Fant ingen JSON i svaret fra Claude")
    return json.loads(m.group(1)).get("news", [])


def is_auth_failure(err: Exception) -> bool:
    msg = str(err).lower()
    return "authentication failed" in msg or "token exchange failed" in msg


def clean(item: dict, today: dt.date):
    title = str(item.get("title", "")).strip()
    url = str(item.get("url", "")).strip()
    if not title or not url.startswith(("http://", "https://")):
        return None
    try:
        date = dt.date.fromisoformat(str(item.get("date", ""))[:10])
    except ValueError:
        return None
    if date > today or date < today - dt.timedelta(days=DAYS_BACK + 30):
        return None
    cat = str(item.get("category", "")).strip().lower()
    try:
        imp = max(1, min(3, int(item.get("importance", 1))))
    except (TypeError, ValueError):
        imp = 1
    out = {
        "id": f"{date.isoformat()}-{slug(title)}",
        "date": date.isoformat(),
        "category": cat if cat in CATEGORIES else "marked",
        "importance": imp,
        "title": title[:200],
        "summary": str(item.get("summary", "")).strip()[:900],
        "why": str(item.get("why", "")).strip()[:400],
        "source": str(item.get("source", "")).strip()[:100],
        "url": url,
    }
    project = str(item.get("project", "")).strip()
    if project:
        out["project"] = project[:60]
    return out


def main() -> int:
    today = dt.date.today()
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    data.setdefault("news", [])

    try:
        text = ask_claude(build_prompt(data, today))
    except Exception as e:
        if is_auth_failure(e):
            print(f"Autentisering mot Anthropic feilet, ingen oppdatering: {e}")
            return 1
        print(f"Klarte ikke å hente svar fra Claude: {e}")
        return 1
    try:
        raw = parse_items(text)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Kunne ikke lese svaret: {e}\n---\n{text[:2000]}")
        return 1

    seen_urls = {norm_url(n.get("url", "")) for n in data["news"]}
    seen_ids = {n["id"] for n in data["news"]}
    added = []
    for item in raw[:MAX_NEW_ITEMS]:
        c = clean(item, today)
        if not c or norm_url(c["url"]) in seen_urls or c["id"] in seen_ids:
            continue
        added.append(c)
        seen_urls.add(norm_url(c["url"]))
        seen_ids.add(c["id"])

    data["news"] = sorted(data["news"] + added, key=lambda n: n["date"], reverse=True)[:400]
    data.setdefault("meta", {})["lastUpdated"] = today.isoformat()
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"La til {len(added)} nye saker:")
    for a in added:
        print(f"  {a['date']}  {a['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
