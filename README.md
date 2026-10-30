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
- TradFi-Aktien-Perpetuals: Momentum und Rücksetzer auf geschlossenen 1-Minuten-Kerzen; angelehnt an die erste Kerze mit neuem Hoch
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
- `dist/tradfi.js`: Long-Mustererkennung für Aktien- und Krypto-Perpetuals
- `dist/field.js`: browserlokales Feldtest-Protokoll und CSV-Export
- `dist/orderbook.js`: Orderbuch-Snapshots, Liquiditätsbalken und Ausführungsschätzung
- `tradingview/`: separate Pine-Script-Strategien und Anleitung für Backtests in TradingView

Die Mustererkennung verwendet abgeschlossene Kerzen. In der Standardansicht bedeutet „Ausbruch bestätigt“ einen gerichteten Schlusskurs über dem Hoch bzw. unter dem Tief der Konsolidierung und die Erfüllung des gewählten Volumenfilters; es ist keine Aussage zur Wahrscheinlichkeit einer weiteren Fortsetzung. Es werden keine Orders ausgeführt.

Die TradingView-Skripte sind eigenständige Backtest-Annahmen und keine Änderung am Dashboard. Regeln, Abweichungen und Ausführungsgrenzen stehen in [`tradingview/README.md`](tradingview/README.md).

Google Fonts wird für die Schriftarten verwendet; ohne Zugriff greifen Systemschriften.

## TradFi-Ansicht

Die Ansicht filtert Bitgets USDT-Perpetual-Instrumente anhand der Klassifizierung `isRwa=YES` und `instrumentType=stock`. Sie ist eine vereinfachte Annäherung an eine Momentum-Pullback-Strategie: Rollierende 24h-Futures-Veränderung ersetzt keine vorbörsliche Aktienveränderung. Nachrichten, Free Float und Aktien-Relativvolumen gegenüber dem 50-Tage-Durchschnitt sind nicht enthalten. Das neue Hoch wird erst nach Abschluss der 1-Minuten-Kerze und beim Scan angezeigt, nicht tickgenau. Die Ansicht ist kein vollständiger Strategietest und führt keine Orders aus.

## Coin-Feldtest

Unter „Coins · Impuls & Rücksetzer“ durchsucht das Dashboard Krypto-USDT-Perpetuals nach dem Long-Momentum-Muster auf abgeschlossenen 1-Minuten-Kerzen. „Neues Hoch berührt“ ist ein nach Kerzenschluss und Scan angezeigtes Muster, kein Echtzeitsignal. Das manuelle Feldtest-Protokoll speichert Zeit, Richtung, Ein- und Ausstieg, Positionswert, Gebühren und Notiz lokal im Browser und bietet CSV-Export. Das geschätzte Ergebnis berücksichtigt kein Funding; Slippage nur über eingegebene Ausführungskurse. Es werden keine Orders ausgeführt.

## Orderbuch-Ansicht

Über „◫ Orderbuch“ bei einem Scanner-Treffer zeigt das Dashboard aggregierte Liquiditätszonen über aktuellen 15-Minuten-Marktkurskerzen, einschließlich der noch laufenden Kerze. Der Preisbereich ist zwischen ±0,5 %, ±1 % und ±2 % wählbar; die Zonen sind jeweils 0,05 % des Startkurses breit. Die Standardansicht mittelt bis zu 15 Minuten der im offenen Fenster etwa alle fünf Sekunden gesammelten Snapshots. Der Zeitraum beginnt beim Öffnen; nach Schließen oder Verbergen wird die Sammlung zurückgesetzt. Pro Zone zählt nur ein Snapshot, dessen gelieferte Tiefe die Zone vollständig abdeckt. n/N zeigt die Abdeckung pro Zone. Bitget liefert maximal 1.000 Stufen je Seite, daher kann der tatsächlich sichtbare Bereich kleiner sein. Spread und Buchverhältnis sind aktuelle Momentaufnahmen. Die geschätzte Auswirkung eines Kaufs über 1.200 USDT ist eine Momentaufnahme ohne Spread und Gebühren; es werden keine Orders ausgeführt. Die Darstellung ist keine Kursprognose.

Die Orderbuchansicht lädt die 15-Minuten-Kerzen für den ausgewählten Kontrakt separat ungefähr alle 30 Sekunden direkt von Bitget. Die Zeitachse verwendet UTC und die Kerzen beginnen zu den angezeigten Zeiten. Die gestrichelte Linie zeigt die Orderbuch-Mitte, die vom letzten gehandelten Preis abweichen kann.
