# VOR Abfahrten für Home Assistant

Zeigt die nächsten Abfahrten an einer Haltestelle im Verkehrsverbund Ost-Region (Wien, Niederösterreich, Burgenland) – inklusive Echtzeit-Verspätung. Datenquelle ist die Verkehrsauskunft Österreich (VAO), die auch die AnachB-App verwendet.

## Installation

**Manuell:** Ordner `custom_components/vor_departures` nach `<config>/custom_components/` kopieren, Home Assistant neu starten.

**HACS (empfohlen):**
[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=woistdiekatze&repository=ha-vor-departures&category=integration)

Oder manuell: HACS → drei Punkte → *Benutzerdefinierte Repositories* → `https://github.com/woistdiekatze/ha-vor-departures`, Kategorie *Integration* → installieren → Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → VOR Abfahrten*

1. Haltestellennamen eingeben, z. B. `Kapelln` oder `Kapelln Hauptstraße`
2. Treffer auswählen (auch Metahaltestellen werden angeboten)
3. Filter setzen (alles optional):
   - **Linien:** genaue Bezeichnung, mehrere mit Komma, z. B. `1234, 1240`
   - **Fahrtrichtung:** Teil des Fahrtziels, z. B. `Tulln`
   - Mit vorangestelltem `!` wird ausgeschlossen, z. B. `!Tulln`
   - Anzahl Abfahrten, Vorschau-Zeitraum, Ausfälle anzeigen, Aktualisierungsintervall

Die Integration kann mehrfach hinzugefügt werden, z. B. einmal pro Fahrtrichtung. Filter lassen sich später unter *Konfigurieren* ändern.

## Entitäten

Pro Haltestelle entstehen:

- **Abfahrt 1 … N** (`sensor.<haltestelle>_abfahrt_1` usw., N = „Anzahl Abfahrten“): Der Zustand ist die **erwartete** Abfahrtszeit (Echtzeit). Attribute:

  | Attribut | Inhalt |
  |---|---|
  | `line` | Linie |
  | `direction` | Fahrtrichtung (Ziel) |
  | `planned_time` / `planned` | planmäßige Abfahrt (`HH:MM` / ISO-Zeitstempel) |
  | `expected_time` / `expected` | erwartete Abfahrt |
  | `delay_min` | Verspätung in Minuten (`null`, wenn keine Echtzeitdaten) |
  | `platform`, `stop`, `cancelled` | Steig, genaue Haltestelle, Ausfall |
  | `summary` | fertiger Text, z. B. `1234 → Tulln Bahnhof · 19:33 (+3)` |

- **Nächste Abfahrt** (`sensor.<haltestelle>_nachste_abfahrt`): Zustand = nächste Abfahrt, Attribut `departures` = komplette Liste mit denselben Feldern.

## Dashboard

Tabelle mit Linie, Richtung, Soll, Ist und Verspätung (Markdown-Karte):

```yaml
type: markdown
title: Bus Kapelln
content: >
  {% set e = 'sensor.kapelln_hauptstrasse_nachste_abfahrt' %}
  | Linie | Richtung | Soll | Ist | Versp. |
  |:--|:--|:-:|:-:|:-:|
  {% for d in state_attr(e, 'departures') -%}
  | {{ d.line }} | {{ d.direction }} | {{ d.planned_time }} | {{ d.expected_time }} | {{ ('%+d' | format(d.delay_min)) if d.delay_min is not none else '–' }} |
  {% endfor %}
```

Kompakt mit einer Zeile pro Abfahrt (Entities-Karte):

```yaml
type: entities
title: Bus Kapelln
entities:
  - type: attribute
    entity: sensor.kapelln_hauptstrasse_abfahrt_1
    attribute: summary
    name: " "
  - type: attribute
    entity: sensor.kapelln_hauptstrasse_abfahrt_2
    attribute: summary
    name: " "
```

(Die Entitätsnamen an deine Installation anpassen.)

## Hinweise

- Standardmäßig wird die öffentliche Zugangs-ID der AnachB-App verwendet. Für den Dauerbetrieb ist eine eigene VAO-Zugangs-ID sauberer; sie lässt sich im ersten Einrichtungsschritt eintragen.
- Kürzeres Intervall als 30 s ist nicht möglich, Standard sind 60 s.
- Die Filter werden lokal angewendet. Es werden bis zu 60 Fahrten im Vorschau-Zeitraum geladen.

## Tests

`python3 -I tests/test_api.py` prüft Parser und Filter offline mit Testdaten.
