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

- Ausbruchsscanner: drei gerichtete 15-Minuten-Kerzen (alternativ 5 Minuten), eine Gegenkerze und Schlusskurs-Ausbruch mit wählbarem Volumenfaktor
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

Scans laufen bei geöffnetem Dashboard jede Minute. Strategie, Richtung und Scannerfilter bleiben während des Scans bedienbar; Änderungen brechen den laufenden Scan ab und starten einen neuen. Die Coin-Suche filtert die angezeigten Ergebnisse. Standarduniversum: die 100 liquidesten Kontrakte nach 24h-Volumen, mit mindestens 10 Mio. USDT Volumen. Große Universen können länger als eine Minute benötigen. Ausfälle und vorläufige Ergebnisse werden gekennzeichnet.

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

Die Mustererkennung verwendet abgeschlossene Kerzen. Im Treppenprofil bedeutet „Ausbruch bestätigt“ einen gerichteten Schlusskurs über dem Hoch bzw. unter dem Tief der einen Gegenkerze und die Erfüllung des gewählten Volumenfilters gegenüber dieser Gegenkerze; es ist keine Aussage zur Wahrscheinlichkeit einer weiteren Fortsetzung. Es werden keine Orders ausgeführt.

Google Fonts wird für die Schriftarten verwendet; ohne Zugriff greifen Systemschriften.

## TradFi-Ansicht

Die Ansicht filtert Bitgets USDT-Perpetual-Instrumente anhand der Klassifizierung `isRwa=YES` und `instrumentType=stock`. Sie ist eine vereinfachte Annäherung an eine Momentum-Pullback-Strategie: Rollierende 24h-Futures-Veränderung ersetzt keine vorbörsliche Aktienveränderung. Nachrichten, Free Float und Aktien-Relativvolumen gegenüber dem 50-Tage-Durchschnitt sind nicht enthalten. Das neue Hoch wird erst nach Abschluss der 1-Minuten-Kerze und beim Scan angezeigt, nicht tickgenau. Die Ansicht ist kein vollständiger Strategietest und führt keine Orders aus.

## Coin-Feldtest

Unter „Coins · Impuls & Rücksetzer“ durchsucht das Dashboard Krypto-USDT-Perpetuals nach dem Long-Momentum-Muster auf abgeschlossenen 1-Minuten-Kerzen. „Neues Hoch berührt“ ist ein nach Kerzenschluss und Scan angezeigtes Muster, kein Echtzeitsignal. Das manuelle Feldtest-Protokoll speichert Zeit, Richtung, Ein- und Ausstieg, Positionswert, Gebühren und Notiz lokal im Browser und bietet CSV-Export. Das geschätzte Ergebnis berücksichtigt kein Funding; Slippage nur über eingegebene Ausführungskurse. Es werden keine Orders ausgeführt.

## Orderbuch-Ansicht

Über „◫ Orderbuch“ bei einem Scanner-Treffer zeigt das Dashboard aggregierte Liquiditätszonen über aktuellen 15-Minuten-Marktkurskerzen, einschließlich der noch laufenden Kerze. Der Preisbereich ist zwischen ±0,5 %, ±1 % und ±2 % wählbar; die Zonen sind jeweils 0,05 % des Startkurses breit. Die Standardansicht mittelt bis zu 15 Minuten der im offenen Fenster etwa alle fünf Sekunden gesammelten Snapshots. Der Zeitraum beginnt beim Öffnen; nach Schließen oder Verbergen wird die Sammlung zurückgesetzt. Pro Zone zählt nur ein Snapshot, dessen gelieferte Tiefe die Zone vollständig abdeckt. n/N zeigt die Abdeckung pro Zone. Bitget liefert maximal 1.000 Stufen je Seite, daher kann der tatsächlich sichtbare Bereich kleiner sein. Spread und Buchverhältnis sind aktuelle Momentaufnahmen. Die geschätzte Auswirkung eines Kaufs über 1.200 USDT ist eine Momentaufnahme ohne Spread und Gebühren; es werden keine Orders ausgeführt. Die Darstellung ist keine Kursprognose.

Die Orderbuchansicht lädt die 15-Minuten-Kerzen für den ausgewählten Kontrakt separat ungefähr alle 30 Sekunden direkt von Bitget. Die Zeitachse verwendet UTC und die Kerzen beginnen zu den angezeigten Zeiten. Die gestrichelte Linie zeigt die Orderbuch-Mitte, die vom letzten gehandelten Preis abweichen kann.

## Volumenprofil

In der Orderbuchansicht kann ein geschätztes historisches Volumenprofil für 4, 12 oder 24 Stunden eingeblendet werden. Es verteilt das Basisvolumen jeder abgeschlossenen 15-Minuten-Kerze gleichmäßig zwischen deren Tief und Hoch auf 24 Preiszonen. Die tatsächliche Verteilung ist unbekannt; die Anzeige nennt vorhandene und erwartete Kerzen. Die laufende Kerze wird ausgeschlossen. Das Profil ergänzt den Chart und verändert keine Scannerregeln; ein Nutzen als Filter wurde nicht nachgewiesen.

## Marktüberblick

Über „◉ Marktüberblick“ bei einem Treffer werden der 1h-Trend (EMA 20/50 auf abgeschlossenen 1h-Kerzen; Abstand unter 0,1 % gilt als uneinheitlich) und die Hochs und Tiefs des UTC-Vortags sowie der letzten 24 Stunden angezeigt. Die Prozentabstände beziehen sich auf den letzten abgeschlossenen 15m-Schlusskurs. Der 24h-Zeitraum endet mit dieser Kerze. Der Überblick lädt Daten nur beim Öffnen und aktualisiert ungefähr minütlich. Bei unvollständigen Daten werden Werte nicht angezeigt. Es handelt sich um Marktinformationen, keine Filter, Prognose oder garantierten Unterstützungs- und Widerstandszonen.
