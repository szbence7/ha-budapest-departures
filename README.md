# Budapesti Indulások – Home Assistant integráció

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Bármelyik budapesti és agglomerációs megálló valós idejű indulásai Home Assistantban, a BKK FUTÁR hivatalos nyílt API-jából. Busz, villamos, troli, metró, HÉV és a Volánbusz agglomerációs járatai is.

A **[Dotmatrix Indulási Kijelző](https://github.com/szbence7/dot-matrix-departure-card)** kártyával olyan, mint egy igazi FUTÁR kijelző:

![Előnézet](images/preview.png)

## Mit tud

- Beállítás felületről: API kulcs, megálló keresése név alapján, irány kiválasztása
- Valós idejű (előrejelzett) indulási idők, a törölt járatokat kiszűri
- Körjáratoknál (pl. 57) a fordulópont után a valódi végállomást mutatja
- Aktív forgalmi zavarok a megállóban közlekedő járatokra
- Megállónként egy szenzor: az állapota a következő indulásig hátralévő perc, a teljes lista az attribútumokban
- Az indulási listát nem menti az adatbázisba, így az nem hízik tőle

## Telepítés

1. HACS → jobb felső ⋮ → **Egyéni tárolók (Custom repositories)** → `https://github.com/szbence7/ha-budapest-departures`, típus: **Integráció**
2. Telepítsd a **Budapesti Indulások** integrációt, majd indítsd újra a Home Assistantot
3. Kérj ingyenes API kulcsot: <https://opendata.bkk.hu>
4. Beállítások → Eszközök és szolgáltatások → **Integráció hozzáadása** → *Budapesti Indulások*
5. Add meg a kulcsot, keresd meg a megállót, válaszd ki az irányt. További megállókat ugyanígy adhatsz hozzá.

## Beállítások (Konfigurálás gomb)

| Beállítás | Alapérték | Megjegyzés |
|---|---|---|
| Frissítési idő | 30 mp | 15–300 mp. Kíméld az ingyenes API-t. |
| Időablak | 60 perc | Ennyi percre előre nézi az indulásokat |
| Attribútumban tárolt indulások | 10 | |

## A szenzor attribútumai

```yaml
stop_id: BKK_F04706
stop_name: Templom tér
alert: "57: Terelés ..."
departures:
  - route: 164B
    headsign: Hűvösvölgy
    minutes: 12
    departure: 1793605472   # unix idő, a kártya ebből számol vissza
    realtime: true
    color: "#009EE3"
    text_color: "#FFFFFF"
    vehicle_type: BUS
    night: false
```

Sablon példa: `{{ state_attr('sensor.templom_ter_kovetkezo_indulas', 'departures')[0].headsign }}`

## Fontos

Nem hivatalos projekt, a BKK Zrt.-hez nincs köze. Adatok: BKK FUTÁR nyílt adatok.

## Támogatás

Ha megspórol pár percet a megállóban, meghívhatsz egy kávéra. Köszönöm! ☕

[![Buy Me a Coffee](https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png)](https://www.buymeacoffee.com/benceix)
