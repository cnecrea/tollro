# CNAIR eToll — Integrare Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.11%2B-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/cnecrea/tollro)](https://github.com/cnecrea/tollro/releases)
[![GitHub Stars](https://img.shields.io/github/stars/cnecrea/tollro?style=flat&logo=github)](https://github.com/cnecrea/tollro/stargazers)
[![Instalări](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/tollro/main/statistici/shields/descarcari.json)](https://github.com/cnecrea/tollro)
[![Ultima versiune](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/cnecrea/tollro/main/statistici/shields/ultima_release.json)](https://github.com/cnecrea/tollro/releases/latest)

Integrare custom pentru [Home Assistant](https://www.home-assistant.io/) care monitorizează contul tău [CNAIR eToll](https://www.etoll.ro/) — același cont pe care îl folosești în aplicația mobilă **TollRo** sau pe [portal.etoll.ro](https://portal.etoll.ro).

CNAIR eToll este noul sistem electronic de tarifare rutieră al CNAIR, care, începând cu 1 octombrie 2026, înlocuiește sistemele anterioare pentru rovinietă, treceri de pod și tariful pe kilometru (TollRo).

Integrarea oferă un dispozitiv pentru cont (notificări, facturi, plăți, starea serviciului) și câte un dispozitiv pentru fiecare vehicul (categorie, valabilitatea rovinietei, cheltuieli, datele vehiculului). Doar citește informațiile din cont: nu cumpără roviniete și nu modifică nimic.

---

## Ce face integrarea

- **Descoperire automată** a vehiculelor din contul eToll — fiecare vehicul devine un dispozitiv separat, cu numărul de înmatriculare în nume
- **Valabilitatea rovinietei** — data de expirare (ora României), zile rămase și un senzor binar „Valabilă / Expirată sau lipsă”, gata de folosit în automatizări
- **Funcționează și pentru roviniete cumpărate în altă parte** — data de expirare vine din eligibilitatea vehiculului, nu doar din achizițiile contului
- **Cheltuieli pe vehicul** — cât ai dat în anul curent pe roviniete, treceri de pod și tichete de rută, plus totaluri pe ultimii 5 ani
- **Facturi și plăți** — ultima factură (sumă, serviciu, metodă de plată, TVA) și totalul plătit în anul curent, cu istoric pe ani
- **Notificări necitite** din aplicația TollRo
- **Starea serviciului eToll** — de pe pagina publică de status CNAIR (funcțional, întârzieri, întrerupere parțială/majoră)
- **Datele vehiculului** — număr, VIN, certificat de înmatriculare, clasă de emisii, țară, MTMA, categorie pentru poduri, plus semnalarea datelor care necesită verificare
- **Statistici pe termen lung** — senzorii de sume se resetează la 1 ianuarie și apar corect în graficele Home Assistant
- **Valori traduse** — stările și atributele apar în română (sau engleză), datele în format românesc (`29/05/2027 23:59`)
- **Autentificare și prin ROeID, Google sau eIDAS** — conturile create astfel se conectează prin pagina oficială eToll; Home Assistant primește doar accesul la cont, nu și datele de autentificare
- **Sesiune păstrată** — autentificarea se reîmprospătează automat, fără să ceară parola la fiecare repornire
- **Reautentificare și reconfigurare** din interfață, fără a șterge integrarea
- **Sistem de licență** — testare gratuită 30 de zile; fără licență validă se afișează doar senzorul „Licență necesară”

---

## Sursa datelor

Datele vin din API-ul folosit de aplicația TollRo și de portalul eToll (`portal.etoll.ro`), doar prin cereri de citire:

| Endpoint | Descriere |
|----------|-----------|
| `profiles` | Profilul contului (identifică intrarea în Home Assistant) |
| `vehicles` | Vehiculele contului (paginat) |
| `tolls` | Serviciile cumpărate: roviniete, treceri de pod, tichete de rută — inclusiv cele expirate și consumate |
| `invoices` | Facturile din ultimii 5 ani |
| `notifications/summary` | Numărul notificărilor necitite |
| `sessions/current` | Sesiunea activă de tarifare pe kilometru (folosită doar în diagnostic) |
| `resources/countries` | Numele țărilor (pentru țara de înmatriculare) |
| `status/api/components/3` | Pagina publică de status CNAIR (fără autentificare) |

Autentificarea se face la serverul CNAIR (`sso.etoll.ro`), în unul din două moduri:

- **cu e-mail (sau telefon) și parolă** — parola se păstrează local; dacă serverul refuză sesiunea, integrarea se reconectează singură cu ea;
- **prin pagina oficială eToll** — pentru conturile create prin ROeID, Google sau eIDAS. Te autentifici în pagina eToll, la fel ca în aplicația TollRo, iar Home Assistant primește doar accesul la cont (un token), nu și datele tale de autentificare.

Sesiunea durează 30 de minute și se reîmprospătează automat înainte de expirare.

Datele se actualizează la fiecare **30 de minute**.

---

## Instalare

### HACS (recomandat)

1. Deschide HACS în Home Assistant
2. Click pe cele 3 puncte (⋮) din colțul dreapta sus → **Custom repositories**
3. Adaugă URL-ul: `https://github.com/cnecrea/tollro`
4. Categorie: **Integration**
5. Click **Add** → găsește „CNAIR eToll” → **Install**
6. Restartează Home Assistant

### Manual

1. Copiază folderul `custom_components/tollro/` în directorul `config/custom_components/` din Home Assistant
2. Restartează Home Assistant

---

## Configurare

### Pasul 1 — Adaugă integrarea

1. **Setări** → **Dispozitive și Servicii** → **Adaugă Integrare**
2. Caută „**CNAIR eToll**”
3. Alege cum te autentifici — la fel ca în aplicația TollRo:

#### Cu e-mail și parolă

| Câmp | Descriere |
|------|-----------|
| **Adresă de e-mail sau număr de telefon** | Datele cu care te autentifici în aplicația TollRo sau pe portal.etoll.ro |
| **Parolă** | Parola contului eToll — se păstrează local, în Home Assistant |

#### Prin pagina oficială eToll (ROeID, Google, eIDAS)

Pentru conturile create prin **ROeID**, **Google** sau **eIDAS**: ele nu au o parolă eToll, deci nu pot folosi varianta de mai sus.

1. Alege „**Prin pagina oficială eToll (ROeID, Google, eIDAS)**” — se deschide o fereastră nouă, cu pagina de autentificare eToll
2. Apasă **Continuă cu ROeID** (sau Google / eIDAS) și autentifică-te ca în aplicația TollRo
3. La final fereastra se închide singură, iar integrarea se adaugă

> La prima folosire, pagina **My Home Assistant** îți poate cere adresa instanței tale (de exemplu `http://homeassistant.local:8123`). Prin ea revine browserul în Home Assistant după autentificare.

Indiferent de metodă, contul e verificat imediat (autentificare reală). Vehiculele contului sunt descoperite automat.

### Pasul 2 — Licență

Integrarea poate fi testată gratuit **30 de zile**. După aceea are nevoie de o licență, de forma `ETOLL-XXXX-XXXX-XXXX-XXXX`, pe care o obții de la [hubinteligent.org/donate?ref=tollro](https://hubinteligent.org/donate?ref=tollro).

Licența se introduce din **Setări** → **Dispozitive și Servicii** → **CNAIR eToll** → **Configurare** (⚙️) → câmpul **Cheie de licență**. Tot acolo vezi starea licenței (evaluare, activă, expirată).

### Pasul 3 — Reconfigurare (opțional)

Dacă ți-ai schimbat parola sau adresa de e-mail în aplicația TollRo, ori vrei să treci pe ROeID, Google sau eIDAS:

1. **Setări** → **Dispozitive și Servicii** → **CNAIR eToll**
2. Meniul (⋮) → **Reconfigurare**
3. Alege metoda și autentifică-te din nou → integrarea se reîncarcă automat; vehiculele, entitățile și istoricul rămân

Dacă autentificarea nu mai este acceptată, Home Assistant îți cere singur să **reconectezi contul** (notificare de reautentificare): introduci parola actuală sau, pentru conturile conectate prin pagina eToll, te autentifici din nou în acea pagină.

---

## Entități create

Integrarea creează:

- un dispozitiv **CNAIR eToll — Date cont**, cu 4 senzori;
- câte un dispozitiv **CNAIR eToll — {număr de înmatriculare}** pentru fiecare vehicul, cu 3–5 entități.

Entity ID-urile de mai jos sunt cele generate de Home Assistant în limba română, pentru un vehicul `B123ABC`. Pe o instalare în engleză, ID-urile sunt generate din numele englezești.

### Dispozitivul „Date cont”

| Entitate | Entity ID | Valoare principală |
|----------|-----------|-------------------|
| `Notificări necitite` | `sensor.cnair_etoll_date_cont_notificari_necitite` | Număr de notificări |
| `Starea serviciului eToll` | `sensor.cnair_etoll_date_cont_starea_serviciului_etoll` | Funcțional / Întreruperi |
| `Ultima factură` | `sensor.cnair_etoll_date_cont_ultima_factura` | Suma (lei) |
| `Total plătit în anul curent` | `sensor.cnair_etoll_date_cont_total_platit_in_anul_curent` | Suma (lei) |

### Dispozitivul vehiculului

| Entitate | Entity ID | Valoare principală | Când apare |
|----------|-----------|-------------------|------------|
| `Categorie vehicul` | `sensor.cnair_etoll_b123abc_categorie_vehicul` | A, B, C, D, I, II, III | Mereu |
| `Cheltuieli în anul curent` | `sensor.cnair_etoll_b123abc_cheltuieli_in_anul_curent` | Suma (lei) | Mereu |
| `Datele vehiculului` | `binary_sensor.cnair_etoll_b123abc_datele_vehiculului` | În regulă / Necesită verificare | Mereu |
| `Rovinietă valabilă până la` | `sensor.cnair_etoll_b123abc_rovinieta_valabila_pana_la` | `29/05/2027 23:59` | Autovehicule din categoriile A–D |
| `Valabilitate rovinietă` | `binary_sensor.cnair_etoll_b123abc_valabilitate_rovinieta` | Valabilă / Expirată sau lipsă | Autovehicule din categoriile A–D |

Vehiculele din categoriile I, II și III plătesc tariful pe kilometru și nu au rovinietă, iar remorcile nu au rovinietă proprie — pentru ele nu se creează entitățile de rovinietă.

### Licență

| Entitate | Entity ID | Când apare |
|----------|-----------|------------|
| `Licență necesară` | `sensor.tollro_licenta_{id_intrare}` | Doar când licența (sau perioada de evaluare) nu este validă — atunci este singura entitate |

---

## Detalii senzori

Atributele fără valoare nu se afișează. În interfață atributele apar cu numele traduse; în șabloane și automatizări folosești **cheia** din tabele (ex. `state_attr('…', 'days_remaining')`).

### Senzor: Notificări necitite

**Valoare principală**: numărul notificărilor necitite din aplicația TollRo (ex. `2`). Pictograma se schimbă când există notificări.

**Atribute**: —

### Senzor: Starea serviciului eToll

**Valoare principală** — starea componentei aplicației mobile, de pe pagina publică de status CNAIR:

| Stare | Semnificație |
|-------|--------------|
| `Funcțional` | Serviciul funcționează normal |
| `Funcționează cu întârzieri` | Probleme de performanță |
| `Întrerupere parțială` | O parte din funcții nu merg |
| `Întrerupere majoră` | Serviciul nu funcționează |
| `Stare necunoscută` | Pagina de status nu a răspuns |

**Atribute secundare**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Ultima actualizare a stării | `last_updated` | `22/10/2026 14:05` |

### Senzor: Ultima factură

**Valoare principală**: suma celei mai recente facturi (după data plății), în lei.

**Atribute principale**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Număr factură | `invoice_number` | `ETL 000123` |
| Data plății | `payment_date` | `30/05/2026 18:42` |
| Serviciu facturat | `billed_service` | Rovinietă / Treceri de pod / Tichet de rută / Credite TollRo / Mai multe servicii |

**Atribute secundare**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Metodă de plată | `payment_method` | Card bancar online (EuPlătesc) / Google Pay / Apple Pay |
| Valoare fără TVA (lei) | `amount_without_vat` | `115.21` |
| TVA (lei) | `vat_amount` | `24.19` |
| Cota de TVA (%) | `vat_rate` | `21` |

### Senzor: Total plătit în anul curent

**Valoare principală**: banii plătiți efectiv în anul curent, din facturi (inclusiv alimentările pentru tariful pe kilometru), în lei. Se resetează la 1 ianuarie.

**Atribute principale**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Facturi în anul curent | `invoices_count` | `3` |
| Ultima plată | `last_payment` | `30/05/2026 18:42` |
| Totaluri pe ani (lei) | `yearly_totals` | `{"2026": 165.4}` (de la primul an cu plăți) |

**Atribute secundare**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Valoare fără TVA (lei) | `amount_without_vat` | `136.69` |
| TVA (lei) | `vat_amount` | `28.71` |

### Senzor: Categorie vehicul

**Valoare principală** — categoria de tarifare a vehiculului:

| Stare | Semnificație |
|-------|--------------|
| `A` | Autoturisme (sub 8+1 locuri) |
| `B` | Transport marfă, MTMA de până la 3,5 t |
| `C` | Transport persoane, între 9 și 23 de locuri |
| `D` | Transport persoane, peste 23 de locuri |
| `I` | Transport marfă, MTMA peste 3,5 t și până la 7,5 t |
| `II` | Transport marfă, MTMA peste 7,5 t și sub 12 t |
| `III` | Transport marfă, MTMA de 12 t sau mai mult |

**Atribute**: — (datele de identificare sunt pe senzorul binar „Datele vehiculului”)

### Senzor: Rovinietă valabilă până la

**Valoare principală**: data și ora până la care rovinieta e valabilă, în ora României (ex. `29/05/2027 23:59`). Pictograma devine de avertizare cu 30 de zile înainte de expirare și de eroare după expirare.

Data vine din eligibilitatea vehiculului, deci apare și pentru roviniete cumpărate din alt cont sau din alt canal.

**Atribute principale**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Zile rămase | `days_remaining` | `218` (negativ după expirare) |
| Valabilă de la | `valid_from` | `30/05/2026` |
| Perioadă de valabilitate | `validity_period` | 1 zi / 10 zile / 30 de zile / 60 de zile / 12 luni |

**Atribute secundare** (doar dacă rovinieta a fost cumpărată din acest cont):

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Stare rovinietă | `vignette_status` | Activă / Expirată / Consumată / Ciornă (neplătită) / Anulată / Restituită |
| Preț plătit (lei) | `price_paid` | `139.4` |
| Serie rovinietă | `vignette_serial` | `RO1234567890` |
| Data achiziției | `purchased_at` | `30/05/2026 18:42` |

### Senzor: Cheltuieli în anul curent

**Valoare principală**: cât s-a cheltuit pentru vehicul în anul curent (servicii cumpărate din acest cont pentru el), în lei. Ciornele, serviciile anulate și cele restituite nu se iau în calcul. Se resetează la 1 ianuarie.

**Atribute principale**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Roviniete (lei) | `vignette_amount` | `139.4` |
| Treceri de pod (lei) | `bridge_amount` | `26.0` |
| Tichete de rută (lei) | `route_amount` | `0.0` |

**Atribute secundare**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Achiziții în anul curent | `purchases_count` | `3` |
| Ultima achiziție | `last_purchase` | `30/05/2026 18:42` |
| Totaluri pe ani (lei) | `yearly_totals` | `{"2026": 165.4}` (de la primul an cu achiziții) |

### Senzor binar: Datele vehiculului

**Valoare principală**: `În regulă` sau `Necesită verificare` — datele vehiculului sunt marcate ca invalide în contul eToll (verifică-le în aplicația TollRo).

**Atribute principale**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Număr de înmatriculare | `plate_number` | `B123ABC` |
| Serie de șasiu (VIN) | `vin` | `WVWZZZ1KZ6W000000` |
| Clasă de emisii | `emission_standard` | Euro 0–7 / EEV / Electric / Fără normă de poluare |
| Țara de înmatriculare | `registration_country` | `România` |

**Atribute secundare**:

| Atribut | Cheie | Exemplu |
|---------|-------|---------|
| Serie certificat de înmatriculare | `registration_certificate` | `T000000` |
| Tip vehicul | `vehicle_type` | Autovehicul / Remorcă |
| Masă totală maximă autorizată (kg) | `max_authorised_mass` | `1800` |
| Categorie pentru treceri de pod | `bridge_toll_category` | `A` |
| Număr de înmatriculare provizoriu | `temporary_plate` | Da / Nu (`true` / `false` în șabloane) |
| Vehicul favorit | `favorite` | Da / Nu (`true` / `false` în șabloane) |

### Senzor binar: Valabilitate rovinietă

**Valoare principală**: `Valabilă` sau `Expirată sau lipsă`, calculat în timp real față de data de expirare.

**Atribute**: — (detaliile sunt pe senzorul „Rovinietă valabilă până la”)

### Senzor: Licență necesară

Apare doar când licența nu este validă; în acest caz celelalte entități sunt eliminate până la activarea licenței.

| Stare | Semnificație |
|-------|--------------|
| `Trial — N zile rămase` | Perioadă de evaluare |
| `Trial expirat` | Perioada de evaluare s-a încheiat |
| `Licență expirată` | Licența a expirat |
| `Licență necesară` | Fără licență |

**Atribute**: `nr_identificare`, `status_licență`, `zile_trial_rămase` (în evaluare), `informații`.

---

## Exemple de automatizări

### Notificare cu 7 zile înainte de expirarea rovinietei

```yaml
automation:
  - alias: "Rovinieta expiră curând"
    trigger:
      - platform: template
        value_template: >
          {{ state_attr('sensor.cnair_etoll_b123abc_rovinieta_valabila_pana_la', 'days_remaining') | int(99) <= 7 }}
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Rovinieta B123ABC expiră"
          message: >
            Rovinieta e valabilă până la
            {{ states('sensor.cnair_etoll_b123abc_rovinieta_valabila_pana_la') }}
            ({{ state_attr('sensor.cnair_etoll_b123abc_rovinieta_valabila_pana_la', 'days_remaining') }} zile).
```

### Alertă când rovinieta nu mai e valabilă

```yaml
automation:
  - alias: "Rovinietă expirată"
    trigger:
      - platform: state
        entity_id: binary_sensor.cnair_etoll_b123abc_valabilitate_rovinieta
        to: "off"
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "Rovinietă expirată"
          message: "Vehiculul B123ABC nu mai are rovinietă valabilă."
```

### Notificare la probleme cu serviciul eToll

```yaml
automation:
  - alias: "eToll — serviciu afectat"
    trigger:
      - platform: state
        entity_id: sensor.cnair_etoll_date_cont_starea_serviciului_etoll
        to:
          - "partial_outage"
          - "major_outage"
    action:
      - service: notify.mobile_app_telefonul_meu
        data:
          title: "eToll nu funcționează normal"
          message: "Starea serviciului: {{ states('sensor.cnair_etoll_date_cont_starea_serviciului_etoll') }}"
```

În automatizări, stările enum se scriu cu cheia internă (`operational`, `performance_issues`, `partial_outage`, `major_outage`, `unknown`), nu cu textul tradus.

### Card pentru Dashboard

```yaml
type: entities
title: CNAIR eToll
entities:
  - entity: binary_sensor.cnair_etoll_b123abc_valabilitate_rovinieta
    name: Rovinietă
  - entity: sensor.cnair_etoll_b123abc_rovinieta_valabila_pana_la
    name: Valabilă până la
  - type: attribute
    entity: sensor.cnair_etoll_b123abc_rovinieta_valabila_pana_la
    attribute: days_remaining
    name: Zile rămase
  - entity: sensor.cnair_etoll_b123abc_cheltuieli_in_anul_curent
    name: Cheltuieli vehicul
  - entity: sensor.cnair_etoll_date_cont_total_platit_in_anul_curent
    name: Total plătit
  - entity: sensor.cnair_etoll_date_cont_notificari_necitite
    name: Notificări
  - entity: sensor.cnair_etoll_date_cont_starea_serviciului_etoll
    name: Serviciu eToll
```

---

## Structura fișierelor

```
custom_components/tollro/
├── __init__.py          # Setup/unload integrare, manager licență (runtime_data pattern)
├── api.py               # Client API read-only — autentificare SSO, reîmprospătare sesiune, paginare
├── binary_sensor.py     # Datele vehiculului, Valabilitate rovinietă
├── config_flow.py       # ConfigFlow (adăugare, reconfigurare, reautentificare) + OptionsFlow (licență)
├── const.py             # Constante, URL-uri API, categorii, statusuri
├── coordinator.py       # DataUpdateCoordinator — actualizare la 30 de minute, salvarea sesiunii
├── diagnostics.py       # Export diagnostic cu datele personale ascunse
├── entity.py            # Dispozitivele (cont, vehicule) și verificarea licenței
├── helpers.py           # Formatare date (ora României), cheltuieli și plăți pe ani
├── license.py           # Manager licență (server-side, Ed25519, HMAC-SHA256)
├── manifest.json        # Metadata integrare
├── oauth.py             # Autentificarea prin pagina oficială eToll (ROeID, Google, eIDAS)
├── sensor.py            # Senzorii contului și ai vehiculelor, „Licență necesară”
├── strings.json         # Traduceri implicite (engleză)
├── brand/               # Pictograma integrării
└── translations/
    ├── en.json          # Traduceri engleză
    └── ro.json          # Traduceri române
```

---

## Cerințe

- **Home Assistant** 2025.11 sau mai nou
- **HACS** (opțional, pentru instalare ușoară)
- **Cont CNAIR eToll** activ (aplicația TollRo sau portal.etoll.ro) — cu e-mail sau telefon și parolă, ori creat prin ROeID, Google sau eIDAS
- **Licență** validă după perioada de evaluare — [hubinteligent.org/donate?ref=tollro](https://hubinteligent.org/donate?ref=tollro)

Singura dependență, `cryptography` (pentru verificarea licenței), este deja inclusă în Home Assistant.

---

## Limitări cunoscute

1. **O singură intrare per cont eToll** — dacă adaugi din nou același cont, vei primi eroarea „Acest cont eToll este deja adăugat în Home Assistant”.

2. **Doar citire** — integrarea nu cumpără roviniete, treceri de pod sau tichete și nu pornește/oprește sesiuni de tarifare pe kilometru.

3. **Vehicule noi** — un vehicul adăugat ulterior în cont apare după reîncărcarea integrării (Setări → Dispozitive și Servicii → CNAIR eToll → ⋮ → Reîncarcă) sau după o repornire.

4. **Rovinieta** — entitățile de rovinietă apar doar pentru autovehiculele din categoriile A–D. Categoriile I, II, III (tarif pe kilometru) și remorcile nu le au.

5. **Cheltuieli vs. plăți** — „Cheltuieli în anul curent” (pe vehicul) însumează serviciile cumpărate din acest cont, după data achiziției. „Total plătit în anul curent” (pe cont) însumează facturile, după data plății, și include alimentările pentru tariful pe kilometru. Cele două sume pot diferi.

6. **Istoric** — totalurile pe ani acoperă cel mult ultimii 5 ani.

7. **Interval fix** — datele se actualizează la 30 de minute; intervalul nu este configurabil.

8. **Autentificarea prin pagina eToll** depinde de configurarea serverului de autentificare CNAIR. Dacă CNAIR o schimbă, conturile deja conectate continuă să funcționeze, dar o conectare nouă prin această metodă poate necesita o actualizare a integrării.

---

## ☕ Susține dezvoltatorul

Dacă ți-a plăcut această integrare și vrei să sprijini munca depusă, **invită-mă la o cafea**! 🫶
Nu costă nimic, iar contribuția ta ajută la dezvoltarea viitoare a proiectului. 🙌

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Susține%20dezvoltatorul-orange?style=for-the-badge&logo=buy-me-a-coffee)](https://buymeacoffee.com/cnecrea)

---

## 🧑‍💻 Contribuții

Contribuțiile sunt binevenite! Simte-te liber să trimiți un pull request sau să raportezi probleme [aici](https://github.com/cnecrea/tollro/issues).

---

## 🌟 Suport
Dacă îți place această integrare, oferă-i un ⭐ pe [GitHub](https://github.com/cnecrea/tollro/)! 😊


## Licență

[Licență proprietară](LICENSE.md) — © 2026 Ciprian Nicolae. Toate drepturile rezervate.
