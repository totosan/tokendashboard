# Token Dashboard · Bitget Pulse

This dashboard allows day trader to see performing token under conditions.

Browserbasiertes Dashboard für Bitget USDT-Perpetual-Futures. Enthält einen Ausbruchsscanner mit zwei Musterprofilen und ein Momentum-Ranking.

## Lokal starten

Voraussetzung: Python 3. Es werden keine npm-Pakete und kein API-Schlüssel benötigt.

```sh
python3 -m http.server 8080 --directory dist
```

Anschließend http://localhost:8080 öffnen. Für Marktdaten ist eine Internetverbindung zur öffentlichen Bitget-API erforderlich. Das Dashboard lässt sich auch auf einem statischen Webhost mit `dist` als Veröffentlichungsverzeichnis betreiben.

## Funktionen

- Ausbruchsscanner auf Basis abgeschlossener 5-Minuten-Kerzen mit Konsolidierung, Schlusskurs-Ausbruch und wählbarem Volumenfaktor
- Musterprofile Treppen & Konsolidierung sowie Gegenkerzen in einer Scanneransicht; separates Momentum-Ranking
- Integrierte Hilfe zu Funktionen, Mustern, Filtern und der Interpretation von Treffern
- USDT-Perpetuals, Long- und Short-Ansicht
- Momentum über 1, 5 und 15 Minuten
- Breakout mit erhöhtem Volumen und 2–4 kleinen Gegenkerzen
- Wählbare 1m-/5m-Kerzen, Impulsschwelle, Volumenfaktor und maximale Rücklauf-Tiefe
- Kerzenchart mit Trigger und Strukturgrenze
- Spread, Funding und Open Interest als Ticker-Snapshots
- Browserlokale Historie und CSV-Export

Scans laufen bei geöffnetem Dashboard jede Minute. Standarduniversum: die 100 liquidesten Kontrakte nach 24h-Volumen, mit mindestens 10 Mio. USDT Volumen. Große Universen können länger als eine Minute benötigen. Ausfälle und vorläufige Ergebnisse werden gekennzeichnet.

## Dateien

- `dist/index.html`: Oberfläche
- `dist/style.css`: responsives Design
- `dist/app.js`: API-Zugriff, Scanner, Charts und Historie
- `dist/pattern.js`: deterministische Mustererkennung und Kerzenaggregation
- `dist/breakout.js`: Erkennung und Darstellung der Konsolidierungen und Ausbrüche
- `dist/help.js`: kontextbezogene Hilfe

Die Mustererkennung verwendet abgeschlossene Kerzen. In der Standardansicht bedeutet „Ausbruch bestätigt“ einen gerichteten Schlusskurs über dem Hoch bzw. unter dem Tief der Konsolidierung und die Erfüllung des gewählten Volumenfilters; es ist keine Aussage zur Wahrscheinlichkeit einer weiteren Fortsetzung. Es werden keine Orders ausgeführt.

Google Fonts wird für die Schriftarten verwendet; ohne Zugriff greifen Systemschriften.
