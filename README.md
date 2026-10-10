# Havvindloggen

En nettside som følger norsk havvind: politikk, prosjekter, kontrakter og selskaper. Hver mandag søker Claude etter nye saker og legger dem inn automatisk.

## Slik fungerer det

| Fil | Hva den gjør |
|---|---|
| `index.html` | Selve nettsiden. Leser sakene fra `news.json`. |
| `news.json` | Alle sakene, prosjektene og milepælene. |
| `scripts/update_news.py` | Ber Claude søke etter nye saker og legger dem til i `news.json`. |
| `.github/workflows/oppdater-havvind.yml` | Kjører scriptet hver mandag og lagrer resultatet. |

Det ligger ingen API-nøkkel noe sted. GitHub beviser overfor Anthropic at det er *ditt* repo som spør, og får en tilgangsnøkkel som bare varer noen minutter (Workload Identity Federation).

---

## Oppsett, steg for steg

Bytt ut `BRUKERNAVN` med GitHub-brukernavnet ditt overalt under.

### 1. Lag repoet

1. Gå til github.com og trykk **New repository**.
2. Kall det `havvindloggen` og velg **Public**. GitHub Pages er gratis for offentlige repoer.
3. Trykk **uploading an existing file** og dra inn `index.html`, `news.json`, `README.md` og mappen `scripts`. Trykk **Commit changes**.
4. Workflow-filen ligger i en skjult mappe, så den er lettest å lage direkte i GitHub: Trykk **Add file → Create new file**. Skriv `.github/workflows/oppdater-havvind.yml` som filnavn, lim inn innholdet fra filen med samme navn, og trykk **Commit changes**.

### 2. Slå på nettsiden

1. I repoet: **Settings → Pages**.
2. Under *Source* velger du **Deploy from a branch**, deretter `main` og `/ (root)`. Trykk **Save**.
3. Etter et minutt eller to ligger siden på `https://BRUKERNAVN.github.io/havvindloggen/`.

### 3. Gjør klar Anthropic-kontoen

1. Logg inn på console.anthropic.com.
2. **Billing:** Legg inn betalingskort og kjøp litt kreditt. Et lite beløp holder lenge. Sett gjerne også en månedlig bruksgrense.
3. **Settings → Organization:** Kopier *Organization ID*.

### 4. Koble GitHub til Anthropic

1. I Console: **Settings → Workload identity → Connect workload**, og velg **GitHub Actions**.
2. Veiviseren registrerer GitHub som utsteder og lager en *service account*. Når du kommer til regelen (*federation rule*), bruker du:
   - **Subject prefix:** `repo:BRUKERNAVN/havvindloggen:ref:refs/heads/main`
   - **Audience:** `https://api.anthropic.com`
   - **Claim** `repository_owner` = `BRUKERNAVN`
3. Noter de tre ID-ene veiviseren viser: regelen (`fdrl_...`), service account (`svac_...`) og workspace (`wrkspc_...`).

Regelen gjør at bare workflows fra `main`-grenen i akkurat dette repoet får tilgang.

### 5. Legg ID-ene inn i GitHub

1. I repoet: **Settings → Secrets and variables → Actions**, og velg fanen **Variables**.
2. Trykk **New repository variable** fire ganger:

| Navn | Verdi |
|---|---|
| `ANTHROPIC_ORGANIZATION_ID` | Organization ID fra steg 3 |
| `ANTHROPIC_FEDERATION_RULE_ID` | `fdrl_...` |
| `ANTHROPIC_SERVICE_ACCOUNT_ID` | `svac_...` |
| `ANTHROPIC_WORKSPACE_ID` | `wrkspc_...` |

Dette er ID-er, ikke passord, så de kan ligge som vanlige variabler.

### 6. Test

1. Gå til **Actions → Oppdater Havvindloggen → Run workflow**.
2. Etter et par minutter skal kjøringen bli grønn. Åpne loggen for å se hvilke saker som ble lagt til, og hvor mange søk og tokens som ble brukt.
3. Last nettsiden på nytt. «Sist oppdatert» skal vise dagens dato.

Deretter kjører den av seg selv hver mandag morgen.

---

## Hvis noe går galt

- **`401 Authentication failed`:** Regelen i steg 4 matcher ikke. Se Console → Workload identity → *History*. Der står det hvorfor forsøket ble avvist. Den vanligste feilen er en skrivefeil i brukernavn eller reponavn i *subject prefix*.
- **Feil om kreditt eller betaling:** Fyll på kreditt under *Billing* i Console.
- **«Kunne ikke lese svaret»:** Claude svarte ikke i riktig format. Kjør workflowen på nytt. Skjer det ofte, si fra, så strammer vi inn instruksjonen.
- **Siden viser gamle data:** GitHub Pages bruker et par minutter på å publisere etter hver oppdatering.

## Justeringer

I workflow-filen kan du legge til disse under `env:` i steget «Spør Claude om nye saker»:

- `HAVVIND_MODEL`: hvilken Claude-modell som brukes (standard: `claude-sonnet-5-5`).
- `HAVVIND_MAX_SEARCHES`: maks antall websøk per kjøring (standard: 8). Dette styrer kostnaden.
- `HAVVIND_DAYS_BACK`: hvor mange dager bakover den leter (standard: 10).

Vil du endre dag eller klokkeslett, endrer du `cron`-linjen. `0 5 * * 1` betyr mandag kl. 05:00 UTC.

Prosjektstatusen og milepælene oppdateres ikke automatisk. Dem endrer du ved å redigere `projects` og `meta.milestones` i `news.json`, eller ved å be Claude om en ny versjon.
