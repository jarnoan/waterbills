# Vesiosuuskunnan laskutustyökalu

## Yleiskuvaus

Tämä komentorivityökalu automatisoi pienen vesiosuuskunnan (noin 20 asiakasta) laskutusprosessin. Se lukee mittarilukemat ja asetustiedostot CSV-tiedostoista, laskee kulutukset ja laskujen summat, luo suomalaisen standardin mukaiset PDF-laskut viivakoodeineen, lähettää laskut sähköpostitse asiakkaille ja tuottaa paperilaskujen yhdistetyn PDF:n sekä rahastonhoitajalle menevän yhteenvedon.

Yksi laskutusjakso kattaa tyypillisesti kaksi kalenterikuukautta. Komennon `--kuukausi`-valitsin ilmaisee jakson **viimeisen** kuukauden numeron (esim. `--kuukausi 2` tarkoittaa jaksoa tammikuu–helmikuu).

## Asennus

```bash
pip install -e .
cp .env.example .env
# Täytä .env-tiedoston arvot
```

Aktivoi virtuaaliympäristö ennen komennon ajamista:

```bash
source .venv/bin/activate
laskutus --help
```

Tai aja suoraan ilman aktivointia:

```bash
.venv/bin/laskutus --help
```

Tarvittavat `.env`-muuttujat:

| Muuttuja | Kuvaus |
|----------|--------|
| `DATA_ROOT` | Laskutusdata-hakemiston polku (esim. Google Drive -liitetty kansio) |
| `SMTP_HOST` | Sähköpostipalvelimen osoite |
| `SMTP_PORT` | SMTP-portti (yleensä 587 tai 465) |
| `SMTP_USER` | SMTP-käyttäjätunnus (sähköpostiosoite) |
| `SMTP_PASSWORD` | SMTP-salasana |
| `SMTP_TLS` | `true` = STARTTLS, `false` = SSL |
| `TREASURER_EMAIL` | Varaosaite: rahastonhoitajan sähköposti. Ensisijainen lähde on `yleiset`-tiedoston `rahastonhoitajan_sähköposti`-avain; tämä arvo toimii varauksena, jos yleiset-avain puuttuu. |

## Laskutustyönkulku

1. Päivitä `osakkaat`-CSV tarvittaessa (uudet tai lähteneet osakkaat)
2. Päivitä `laskurivit`-CSV tarvittaessa (hinnanmuutokset)
3. Luo tai päivitä `yleiset`-CSV jaksokohtaisilla päivämäärillä
4. Luo `lukemat`-CSV jaksoa varten (mittarilukemat kullekin asiakkaalle; `uusi`-ohjaaja osaa hakea lukemat Vesitili-portaalista, ks. [lukemat](#lukemat))
5. Aja `laskutus lasku` → luodaan `laskut`-CSV
6. Tarkista ja tarvittaessa muokkaa `laskut`-CSV
7. Aja `laskutus pdf` → luodaan PDF-laskut
8. Tarkista PDF-laskut
9. Aja `laskutus julkaise` → lähetetään sähköpostit, luodaan paperilaskut ja yhteenveto

**Vinkki:** Komento `laskutus uusi` ohjaa koko työnkulun läpi interaktiivisesti.

## Komennot

**Suositeltu aloitustapa uusille käyttäjille: `laskutus uusi`** ohjaa koko laskutuskierron läpi interaktiivisesti yhdellä komennolla.

| Komento | Kuvaus |
|---------|--------|
| `laskutus uusi` | Interaktiivinen ohjattu laskutuskierto alusta loppuun — kerää syötteet, laskee laskut, luo PDF:t ja julkaisee |
| `laskutus lasku` | Laskee kulutukset ja kirjoittaa laskut CSV-tiedostoon |
| `laskutus pdf` | Luo PDF-laskut olemassa olevasta laskut-CSV:stä |
| `laskutus julkaise` | Lähettää sähköpostit, luo paperilaskut ja lähettää yhteenvedon tilintarkastajalle |
| `laskutus lukemat` | Hakee ja näyttää viimeisimmät mittarilukemat Vesitili-portaalista (ei tallenna mitään) |

`--kuukausi` ei ole pakollinen millekään komennolle:
- `laskutus uusi`: oletuksena seuraava kaksikuukautinen jakso edellisen jakson jälkeen (alkaa edellisen jakson päättymispäivää seuraavana päivänä, päättyy toisen kuukauden lopussa). Jos edellinen jakso on vielä kesken (yhteenveto-PDF puuttuu), ohjaaja jatkaa sitä samaa jaksoa sen sijaan, että hyppäisi seuraavaan.
- `laskutus lasku` / `pdf` / `julkaise`: oletuksena nykyisen (viimeksi luodun) laskutusjakson loppukuukausi.

Kaikki komennot tukevat seuraavia valitsimia:

| Valitsin | Oletusarvo | Kuvaus |
|----------|-----------|--------|
| `--vuosi` | Kuluva vuosi (`uusi`: seuraavan jakson vuosi) | Laskutusvuosi |
| `--kuukausi` | Ks. yllä | Jakson loppukuukausi (1–12) |
| `--data-hakemisto` | `.env`-tiedoston `DATA_ROOT` | Datatiedostojen juurihakemisto |
| `--ylikirjoita` | ei | Ylikirjoittaa olemassa olevat tulostiedostot (`lasku`, `julkaise`) |
| `--lähetä-uudelleen` | ei | Lähettää sähköpostit uudelleen jo lähetetyille (`julkaise`) |

## Tiedostorakenne

Laskutusdata tallennetaan kaksitasoiseen kansiorakenteeseen:

```
DATA_ROOT/
  2026/
    2026-02/     ← helmikuun laskutusjakso
      20260228-yleiset.csv          ← uusi-ohjaaja luo (jakson loppupäivä, ei lisätietoa)
      20260228-osakkaat.csv         ← uusi-ohjaaja luo (jakson loppupäivä, ei lisätietoa)
      20260228-lukemat-uudet.csv    ← jakson loppupäivä + lisätieto
      20260228-laskut-uudet.csv
      20260228-lasku-meikalainen-matti.pdf
      20260228-paperilaskut.pdf
      20260228-yhteenveto.pdf
    2026-08/     ← elokuun laskutusjakso
      ...
  2025/
    2025-02/
      ...
```

Tiedostot nimetään muodossa `VVVVKKPP-tyyppi[-lisätieto].ext`.
- Komennot `lasku`, `pdf` ja `julkaise` käyttävät jakson **loppupäivää** tiedostonimessä.
- `uusi`-ohjaajan luomat `yleiset`- ja `osakkaat`-tiedostot käyttävät jakson **loppupäivää**, kuten muutkin tiedostot, eikä niihin lisätä lisätietoa.

| Tiedostotyyppi | Suunta | Kuvaus |
|----------------|--------|--------|
| `osakkaat` | syöte | Osakkaiden yhteystiedot ja mittarinumerot |
| `laskurivit` | syöte | Laskurivit hintatietoineen ja soveltamistapoineen |
| `yleiset` | syöte | Jakson päivämäärät ja osuuskunnan yhteystiedot (avain-arvo-muoto) |
| `lukemat` | syöte | Mittarilukemat kullekin asiakkaalle ja päämittarille |
| `laskut` | tuloste | Lasketut laskut asiakaskohtaisesti |
| `lasku` | tuloste | Yksittäisen asiakkaan PDF-lasku |
| `paperilaskut` | tuloste | Kaikki paperilaskut yhdistetty yhteen PDF:ään |
| `yhteenveto` | tuloste | Tilintarkastajan yhteenveto-PDF laskuista ja vesihävikistä |

## CSV-tiedostomuodot

### osakkaat

| Sarake | Tyyppi | Kuvaus |
|--------|--------|--------|
| `nimi` | teksti | Asiakkaan koko nimi |
| `katuosoite` | teksti | Katuosoite |
| `postinumero` | teksti | Postinumero |
| `postitoimipaikka` | teksti | Postitoimipaikka |
| `sähköposti` | teksti | Sähköpostiosoite |
| `puhelin` | teksti | Puhelinnumero |
| `mittarinro` | teksti | Vesimittarin numero; tyhjä = ei aktiivinen osakas |
| `laskutustapa` | teksti | `sähköposti` tai `paperi` |
| `liittynyt` | päivämäärä (YYYY-MM-DD) | Liittymispäivä |
| `lähtenyt` | päivämäärä tai tyhjä | Lähtöpäivä |
| `kiinteistötunnus` | teksti | Kiinteistötunnus |
| `henkilömäärä` | kokonaisluku | Kiinteistön henkilömäärä |
| `tilinumero` | teksti | Pankkitilinumero (vain tiedoksi — ei käytetä laskennassa) |
| `asiakasnumero` | teksti tai tyhjä | Asiakasnumero Vesitili-portaalissa; käytetään mittarilukeman hakuun portaalista |
| `kulutuspiste` | teksti tai tyhjä | Käyttöpaikan numero Vesitili-portaalissa; käytetään mittarilukeman hakuun portaalista |

### laskurivit

| Sarake | Tyyppi | Kuvaus |
|--------|--------|--------|
| `nimike` | teksti | Laskurivin nimi (esim. "Perusmaksu") |
| `määrä` | desimaaliluku | Kappalemäärä tai ajanjaksomäärä (esim. `2` kuukautta) |
| `yksikkö` | teksti | Yksikkö (esim. `kk` tai `m³`) |
| `a-hinta` | desimaaliluku | Yksikköhinta euroina ilman ALV:tä |
| `netto` | desimaaliluku | Laskennallinen: `määrä × a-hinta` (viitetieto) |
| `alv-%` | desimaaliluku | ALV-prosentti (esim. `25.50`) |
| `alv` | desimaaliluku | Laskennallinen: `netto × alv-%` (viitetieto) |
| `yhteensä` | desimaaliluku | Laskennallinen: `netto + alv` (viitetieto) |
| `soveltamistapa` | teksti | `aktiiviset` / `kaikki` / `kulutus` |
| `jakso_alkaa` | päivämäärä (YYYY-MM-DD) tai tyhjä | Rivin laskutusjakson alkupäivä; jos tyhjä, käytetään `yleiset`-tiedoston arvoa |
| `jakso_loppuu` | päivämäärä (YYYY-MM-DD) tai tyhjä | Rivin laskutusjakson loppupäivä; jos tyhjä, käytetään `yleiset`-tiedoston arvoa |

Huom: `netto`, `alv` ja `yhteensä` ovat viitetietoja — laskennassa käytetään `määrä`- ja `a-hinta`-sarakkeita.

Rivikohtainen laskutusjakso on hyödyllinen esimerkiksi vakuutusmaksuille ja pankkikuluille, jotka laskutetaan kerran vuodessa eri jaksolla kuin vesimaksut.

Soveltamistavat:
- `aktiiviset` — jaetaan tasan aktiiville osakkaille (kattohinta per osakas)
- `kaikki` — jaetaan tasan kaikille osakkaille
- `kulutus` — veloitetaan kulutuksen mukaan (€/m³)

### yleiset

Avain-arvo-muoto: kaksi saraketta `avain` ja `arvo`, yksi rivi per asetus.
Jaksokohtainen tiedosto sisältää tyypillisesti vain `jakso_alkaa`, `jakso_loppuu` ja valinnaisesti `laskupäivä`;
muut arvot haetaan automaattisesti vanhemmista tiedostoista (cascade-periaate).

Huom: `eräpäivä` **ei** ole yleiset-avain — se lasketaan automaattisesti `laskupäivä + 14 päivää`.

| Avain | Tyyppi | Pakollinen | Kuvaus |
|-------|--------|-----------|--------|
| `jakso_alkaa` | YYYY-MM-DD | kyllä | Laskutusjakson alkupäivä |
| `jakso_loppuu` | YYYY-MM-DD | kyllä | Laskutusjakson loppupäivä |
| `laskupäivä` | YYYY-MM-DD | ei | Laskun päiväys; oletuksena kuluva päivä |
| `osuuskunnan_nimi` | teksti | kyllä | Vesiosuuskunnan nimi |
| `iban` | teksti | kyllä | Osuuskunnan pankkitilinumero (FI + 16 numeroa) |
| `y_tunnus` | teksti | kyllä | Y-tunnus |
| `yhteyshenkilö` | teksti | kyllä | Yhteyshenkilön nimi |
| `puhelin` | teksti | kyllä | Yhteyshenkilön puhelinnumero |
| `sähköposti` | teksti | kyllä | Yhteyshenkilön sähköpostiosoite |
| `päämittarinro` | teksti | kyllä | Päämittarin numero |
| `rahastonhoitajan_sähköposti` | teksti | kyllä | Rahastonhoitajan sähköposti yhteenvetolaskun lähetystä varten |
| `päämittarin_asiakasnumero` | teksti | ei | Päämittarin asiakasnumero Vesitili-portaalissa; käytetään päämittarin lukeman hakuun portaalista |
| `päämittarin_kulutuspiste` | teksti | ei | Päämittarin käyttöpaikan numero Vesitili-portaalissa |
| `päämittarin_perusmaksu` | desimaaliluku | ei | Päämittarin perusmaksu **yhteensä** euroina ilman ALV:tä; jaetaan tasan aktiivisten asiakkaiden kesken; käytetään oletusarvona laskurivejä luotaessa `uusi`-ohjaajassa |
| `vesihinta` | desimaaliluku | ei | Vesihinta euroina per kuutiometri ilman ALV:tä; käytetään oletusarvona laskurivejä luotaessa `uusi`-ohjaajassa |
| `aloituslaskunumero` | kokonaisluku | ei | Ensimmäisen laskun numero osuuskunnan ensimmäisessä laskutusajossa. Ohitetaan automaattisesti, kun aiempia `laskut`-tiedostoja on olemassa — tällöin numerointi jatkuu suurimmasta aiemmasta laskunumerosta + 1. Cascatuu vanhemmista yleiset-tiedostoista, mutta on käytännössä merkityksellinen vain kerran. |
| `viesti` | teksti | ei | Vapaamuotoinen viesti, näytetään laskun alalaidassa |

### lukemat

| Sarake | Tyyppi | Kuvaus |
|--------|--------|--------|
| `nimi` | teksti | Asiakkaan nimi tai `päämittari` päämittarille |
| `päivämäärä` | YYYY-MM-DD | Lukemispäivä |
| `lukema` | kokonaisluku (m³) | Mittarilukema kuutiometreissä |

**Lukemien haku Vesitili-portaalista:** `uusi`-ohjaaja tarjoutuu Vaiheessa 3 hakemaan lukemat osoitteesta <https://vesitili.fi/nokia/portal/> niille osakkaille, joiden `asiakasnumero` ja `kulutuspiste` (käyttöpaikan numero) on täytetty `osakkaat`-tiedostoon, sekä päämittarille, jos `yleiset`-tiedostossa on `päämittarin_asiakasnumero` ja `päämittarin_kulutuspiste`. Työkalu kirjautuu kunkin osakkaan tunnuksilla yksityisasiakkaana, lukee portaalin etusivun edellisen lukeman ja sen ilmoituspäivän ja kirjautuu ulos. Haettu lukema näytetään kysymyksen yhteydessä (`portaali: 1234, 30.08.2026`) ja Enter hyväksyy sen; lukeman päivämääräksi tallennetaan portaalin ilmoituspäivä. Portaali näyttää aina viimeisimmän ilmoitetun lukeman, joten lukema hyväksytään vain, jos sen ilmoituspäivä on uudempi kuin osakkaan edellinen laskutuslukema — muuten osakas ei ole vielä ilmoittanut uutta lukemaa ja lukema kysytään käsin (tai kulutus arvioidaan). Komennolla `laskutus lukemat` haun voi kokeilla tallentamatta mitään.

**Kulutuksen arviointi:** Jos asiakkaalle ei ole nykyisen jakson lukemaa (esim. mittarille ei päästy), kulutus arvioidaan kahden edellisen jakson lukemien erotuksena — eli edellisen jakson toteutunutta kulutusta käytetään arviona nykyiselle jaksolle. Jos kahta edellistä lukemaa ei löydy, kulutus arvioidaan nollaksi ja asiasta varoitetaan. Arvioidut kulutukset merkitään laskuille ja Vaihe 5:n taulukkoon `A`-merkinnällä (`laskut`-CSV:n `arvio`-sarake). Edelliset lukemat haetaan kaikista laskutusjaksojen kansioista — kaksi tuoreinta jaksoa, jotka edeltävät nykyistä jaksoa, riippumatta siitä montako lukemat-tiedostoa samassa kansiossa on (esim. ensimmäisen jakson `-alkutilanne`-siemenlukema ja sen oma loppulukema lasketaan molemmat mukaan).

## Ensiajaminen

**Suositeltava tapa:** Käynnistä `laskutus uusi --vuosi VVVV --kuukausi KK` (ensimmäisellä kerralla ei ole edellistä jaksoa, josta oletusarvo voitaisiin päätellä, joten nämä on annettava), joka havaitsee automaattisesti ensimmäisen laskutuskerran ja kerää alkutilanteen mittarilukemat interaktiivisesti. Ohjaaja tallentaa ne tiedostoon `VVVVKKPP-lukemat-alkutilanne.csv` (päivätty yhtä päivää ennen jakson alkua) ja jatkaa suoraan laskujen laskentaan.

**Manuaalinen tapa:** Luo siemenlukemat-tiedosto käsin. Se on `lukemat`-CSV, joka sisältää yhden rivin per aktiivinen osakas sekä rivin päämittarille **ennen** ensimmäistä laskutusjaksoa. Tiedoston päivämäärän tulee olla ennen jakson alkupäivää. Sijoita tiedosto hakemistoon `DATA_ROOT/<vuosi>/<vuosi>-<KK>/`.

Esimerkki siemenlukemat-tiedostosta (`20251231-lukemat-alkutilanne.csv`):

| nimi | päivämäärä | lukema |
|------|-----------|--------|
| Matti Meikäläinen | 2025-12-31 | 1250 |
| Liisa Virtanen | 2025-12-31 | 873 |
| Pekka Korhonen | 2025-12-31 | 2105 |
| päämittari | 2025-12-31 | 45820 |

`laskut`-tiedostoa ei tarvita ensimmäistä ajoa varten — laskunumerointi alkaa automaattisesti ykkösestä (tai `aloituslaskunumero`-arvosta `yleiset`-tiedostossa, jos se on asetettu).
