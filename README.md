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

## Entität

`sensor.<haltestelle>_nachste_abfahrt` (Zeitstempel der nächsten Abfahrt, mit Verspätung) und das Attribut `departures`:

```yaml
- line: "1234"
  direction: Tulln Bahnhof
  planned: "2026-11-02T19:30:00+01:00"
  departure: "2026-11-02T19:33:00+01:00"
  delay_min: 3
  platform: "1"
  stop: Kapelln Hauptstraße
  cancelled: false
```

## Dashboard-Beispiel (Markdown-Karte)

```yaml
type: markdown
title: Bus Kapelln
content: >
  {% set e = 'sensor.kapelln_nachste_abfahrt' %}
  {% for d in state_attr(e, 'departures') %}
  **{{ d.line }}** → {{ d.direction }} –
  {{ as_timestamp(d.departure) | timestamp_custom('%H:%M') }}
  {% if d.delay_min and d.delay_min > 0 %}(+{{ d.delay_min }}){% endif %}
  {% if d.cancelled %}~~Ausfall~~{% endif %}

  {% endfor %}
```

(Den Entitätsnamen an deine Installation anpassen.)

## Hinweise

- Standardmäßig wird die öffentliche Zugangs-ID der AnachB-App verwendet. Für den Dauerbetrieb ist eine eigene VAO-Zugangs-ID sauberer; sie lässt sich im ersten Einrichtungsschritt eintragen.
- Kürzeres Intervall als 30 s ist nicht möglich, Standard sind 60 s.
- Die Filter werden lokal angewendet. Es werden bis zu 60 Fahrten im Vorschau-Zeitraum geladen.

## Tests

`python3 -I tests/test_api.py` prüft Parser und Filter offline mit Testdaten.
