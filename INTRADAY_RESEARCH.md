# Intraday-Einstiege: Arbeitsstand zu Issue #3

**Status: offen, nicht entscheidungsreif.** Dieser Bericht dokumentiert eine Bestandsaufnahme und ein überprüfbares Forschungsdesign. Er belegt weder profitable Signale noch eine Trefferquote. Es wurden keine produktiven Dashboard-Regeln geändert und keine Orders ausgelöst. Die Akzeptanzkriterien von [Issue #3](https://github.com/totosan/tokendashboard/issues/3) sind nicht erfüllt.

## Was in dieser Sitzung tatsächlich geprüft wurde

- Die Arbeitskopie und die darin vorhandenen Implementierungen, README und TradingView-Dateien wurden geprüft. Die früher in PR #4 gemachte Aussage, es gebe keine Pine-Skripte, war falsch: Es liegen drei unter `tradingview/` samt Anleitung.
- Für alle acht JavaScript-Dateien unter `dist/` bestand `node --check`. Das Repository enthält kein Test-/Build-Manifest und keine vorhandenen automatisierten Testdateien; die Syntaxprüfung validiert weder Marktdaten noch Signalgüte.
- Im Repository wurden keine Backtest-Daten oder Artefakte des in Issue #3 erwähnten Tests mit acht Coins und 45 Tagen gefunden. Dieser dort berichtete negative Befund wurde nicht reproduziert; Auswahl, Daten, Kosten und Code sind hier nicht unabhängig prüfbar.
- Es wurde kein historischer Datenabruf und kein Backtest durchgeführt. Die Bitget-Dokumentation ließ sich in dieser Sitzung nicht direkt abrufen (DNS-Fehler); Suchanfragen liefen in Timeouts. Hinweise aus indexierten offiziellen Dokumentationsseiten sind unten ausdrücklich als **noch zu verifizieren** markiert.
- Die verfügbaren GitHub-Werkzeuge erlauben hier das Lesen, aber nicht das Erstellen/Bearbeiten von Issues oder Labels. `Issue #3` hat laut Label-Abfrage derzeit keine Labels. Die Labelsammlung des Repositories konnte wegen eines Timeouts nicht geprüft werden.

## Bestandsaufnahme des Dashboards

| Bereich | Aktuelle Implementierung | Aussagegrenze |
|---|---|---|
| Treppen-/Ausbruchprofil | `dist/breakout.js:3-20`: drei gerichtete Kerzen, eine Gegenkerze, 5–50 % Rücklauf und optionaler bestätigender Schlusskurs jenseits der Gegenkerze mit Volumenfilter. | Das Gegenkerzenhoch/-tief ist kein Nachweis einer eigenständigen vorherigen Seitwärtszone. Keine gemessene Fortsetzungswahrscheinlichkeit. |
| Impuls & Gegenkerzen | `dist/pattern.js:6-24`: 2–6 Impulskerzen, 2–4 fallende Gegenkerzen, Rücklauf- und Volumenbedingungen; 1m/5m, Long/Short, abgeschlossene Kerzen. | Bruch eines vorangegangenen 10-Kerzen-Hochs/-Tiefs bedeutet nicht automatisch enge Konsolidierung. Parameter sind Heuristiken. |
| Momentum-Ranking / Universum | `dist/app.js:56-59`: aktuell nach 24h-Quotevolumen gefilterte und gegebenenfalls auf Top-N begrenzte Kontrakte; Renditen aus jüngsten abgeschlossenen 1m-Kerzen. Standard laut README: Top 100 mit mindestens 10 Mio. USDT 24h-Volumen (`README.md:31`). | Die heutige Volumenauswahl ist kein historisches Point-in-time-Universum. Inaktive/fehlende Symbole und fehlgeschlagene Candle-Abfragen können die Stichprobe zusätzlich verzerren. Ranking ist kein Backtest und kein eigenständiger Entry-Nachweis. |
| TradFi-/Coin-Pullback | `dist/tradfi.js:3-19`: dieselbe Long-Musterfunktion wird auf abgeschlossenen 1m-Kerzen in beiden Ansichten genutzt. TradFi-Auswahl: API-Klassifizierung `isRwa=YES`, `instrumentType=stock`, online; sie wird mit normalen, perpetualen, USDT-quotierten Verträgen abgeglichen (`dist/app.js:56-58`). | Der Code prüft die Futures-Daten, nicht den Preis der zugrunde liegenden Aktie. Keine Nachrichten, Aktien-Relativvolumina, Float- oder Premarket-Historie. Die README nennt es eine Annäherung, keinen vollständigen Strategietest (`README.md:52-58`). Live-Verfügbarkeit und Bedeutung der API-Felder sind nicht verifiziert. |
| Marktüberblick | `dist/context.js:6-13`: abgeschlossene 1h-Kerzen für EMA 20/50, Vortagshoch/-tief und jüngste 24h-Zonen aus 15m-Kerzen. | Wird bei Öffnen der Ansicht geladen, ist kein Scannerfilter; 4h-Regime ist nicht implementiert. |
| Volumenprofil | `dist/orderbook.js:12,18-22`: Kerzenvolumen wird für 4/12/24 Stunden aus abgeschlossenen 15m-Kerzen gleichmäßig über 24 Preiszonen verteilt; maximale Zone als POC markiert. | Die Preisverteilung innerhalb jeder Kerze ist unbekannt. Value Area (VAH/VAL) wird nicht berechnet. Die README sagt, Filter-Nutzen sei nicht nachgewiesen (`README.md:66-68`). |
| Orderbuch und Ausführung | `dist/orderbook.js:26-30`: aktuelle Orderbuchabfrage und nur während geöffneter Ansicht etwa 5-Sekunden-Snapshots für höchstens 15 Minuten. | Keine historische Tiefe. Spread, Buchverhältnis und Wirkungsschätzung sind Momentaufnahmen; der README-Hinweis schließt Spread und Gebühren bei der Wirkungsschätzung aus (`README.md:60-64`). |
| Kosten und Feldprotokoll | Ticker liefert gegenwärtige Spread-/Funding-/OI-Werte (`dist/app.js:25`); `dist/field.js:8-14` berechnet manuell eingegebene Trades. | Keine historische Kostenreihe im Scanner. Das Feldprotokoll ist kein Backtest und zieht Funding nicht automatisch ab (`README.md:56-58`). |
| TradingView-Skripte | `tradingview/stairs_consolidation.pine`, `impulse_counter_candles.pine`, `momentum_first_new_high.pine` und `tradingview/README.md` sind vorhanden. | Eigenständige Backtest-Annahmen; keine gemessenen Ergebnisse. Pine-Parameter/Entry-Fills weichen teils von der Dashboard-Suche ab; Funding und Bitget-Liquidation werden nicht simuliert (`tradingview/README.md:3-10,36-57`). |

## Forschungsfragen und testbare Definitionen

Alle folgenden Ansätze sind **Hypothesen**, keine Empfehlungen. Die Regeln, Parameter und Varianten müssen vor dem Auswertungslauf festgeschrieben werden.

| Domäne | Präregistrierbarer Vergleich | Hauptrisiko / offene Voraussetzung |
|---|---|---|
| Breakout und Pullback | Bestehende Scanner gegen dieselbe Baseline mit separat definierter Zone: feste zurückliegende Bar-Anzahl, Rangebreite relativ zu ausschließlich vorher bekanntem ATR/Preis, klarer Schlusskurs-Ausbruch; Retest-, Fehlausbruch- und Spät-Signal-Fenster vorab festlegen. | Bisherige Muster erzwingen keine echte, enge Konsolidierung. Alle Fenster/Schwellen mehrfach testen zu können erzeugt Selektions- und Overfitting-Risiko. |
| Volumen | Bestehendes Kerzenprofil/Relativvolumen als Zusatzmerkmal einzeln gegen unveränderte Baseline testen. POC/VAH/VAL erst dann vergleichen, wenn Berechnung und Datenquelle definiert sind. | Candle-OHLCV verteilt kein tatsächliches Trade-Volumen auf Preise. Semantik der Bitget-Volumenfelder und historische Trade-Daten müssen bestätigt werden. |
| 1h-/4h-Regime | Gleiche 5m-/15m-Signale ohne Filter und mit vorher festgelegtem, ausschließlich aus bereits geschlossenen 1h-/4h-Kerzen gebildetem Regime vergleichen. | 1h-Kontext wird aktuell nur angezeigt, 4h fehlt. Unvollständige Balken und zeitliche Fehlzuordnung können Lookahead erzeugen. |
| Weitere Ansätze | EMA/Trend, Tagesniveaus, VWAP und Mean-Reversion (z. B. Bollinger/RSI) als getrennte, kausale Testarme mit benannten Marktregimen untersuchen. | Ein Indikatorname ist kein Evidenzbeleg. Trends können Reversion überrollen; Ranges können Breakouts scheitern lassen. |
| Krypto-Universum | Dieselben Regeln/Kosten auf BTC, ETH, vorab definierte Altcoin-/Liquiditätsgruppen und ein breites Universum anwenden; historische Listings und Auswahlzeitpunkt erfassen. | Aktuelles Volumen-Ranking kann Survivorship-/Auswahlbias erzeugen; korrelierte gleichzeitige Signale sind keine unabhängigen Beobachtungen. |
| TradFi-Übertragbarkeit | Aktien-Perpetuals separat je Instrument und Handelszeitabschnitt evaluieren; Derivatepreis/-volumen nicht mit Aktienkurs/-volumen gleichsetzen. | Live-Instrumentklassifikation, historische Abdeckung, Handelskalender, Referenzpreis und produktspezifische Kosten sind nicht durch lokale Daten belegt. |
| Daten und Ausführung | Erst Candle-Zeitstempel, Kerzenschluss, Lücken, Volumeneinheiten und Instrumentlisten verifizieren. Entry frühestens am nächsten plausiblen Quote/Trade nach Scan- und manueller Verzögerung modellieren. | Live-Ticker/Orderbuch sind keine historischen Spreads, Fills oder Depth. Funding muss als zeitlich passende Kostenreihe behandelt werden. |

### Mindestprotokoll für eine Evaluation

1. Vor dem Test Regeln, Long/Short, Symboluniversum samt Point-in-time-Zugehörigkeit, Zeitrahmen, alle getesteten Parameter und Marktregime einfrieren.
2. Nur abgeschlossene Kerzen am Signalzeitpunkt verwenden. Ein Signal am Kerzenschluss nicht rückwirkend zum selben Schlusskurs ausführen; Scan- und manuelle Verzögerung berücksichtigen.
3. Einstiegsqualität zunächst mit mehreren vorab festgelegten Forward-Renditen, MFE/MAE, Zeit bis zur Bewegung und Signalabdeckung bewerten. Stops, Ziele und Haltedauern wären zusätzliche Testannahmen, keine Nutzer-Vorgaben.
4. Kosten getrennt und transparent ansetzen: datierte Maker-/Taker-Gebühr je Instrument/Konto, Spread, Slippage/Markteinfluss, Funding und Verzögerung. Mit ausführbaren Preisen testen; Gaps und Kerzen mit gleichzeitig berührtem Stop/Ziel konservativ behandeln.
5. Chronologische Entwicklungs-/Validierungs-/Out-of-sample-Teile oder Walk-forward nutzen. Keine Parameterwahl anhand des Out-of-sample-Teils; Anzahl getesteter Varianten offenlegen.
6. Stichprobe, Abdeckung, brutto/netto, Mittel/Median, Trefferquote, durchschnittlichen Gewinn/Verlust, Profitfaktor, Drawdown und Unsicherheit berichten, soweit die Methode dies zulässt. Ergebnisse nach BTC/ETH, Altcoins und verfügbaren TradFi-Kontrakten trennen; negative und uneindeutige Resultate nicht auslassen.
7. Rohdatenparameter, UTC-Zeitstempel, Codeversion, fehlende Intervalle, Ausführungs- und Kostenannahmen sowie jedes getestete Signal reproduzierbar festhalten. Eine Trefferquote von 55 % ist kein alleiniges Erfolgskriterium.
8. Verluste und Hebelrisiken separat ausweisen: Renditen zunächst ungehebelt berechnen; für gesonderte Szenarien nur verifizierte Kontrakt-/Margin-/Liquidationsregeln und vorab deklarierte Exponierungen verwenden. Verlustquantile, Expected Shortfall soweit die Stichprobe trägt, Drawdown, Verlustserien und Kapital-/Marginwirkung berichten. Hebel ist kein Edge.
9. Überlappende Signale/Trades vorab regeln (z. B. eine offene Position je Symbol/Richtung oder ausdrücklich mehrere). Nicht unabhängige Ereignisse nicht als unabhängige Beobachtungen zählen; Portfolio-/Marginlimits und zeitliche bzw. symbolische Cluster in der Unsicherheitsauswertung berücksichtigen.

### Präzisierung der Muster für reproduzierbare Tests

- **Konsolidierung:** feste Anzahl abgeschlossener Bars; Grenzen aus deren Hoch/Tief; Rangebreite vorab als Anteil am Preis oder anhand eines ATR aus ausschließlich vorherigen Bars begrenzen. Die Ausbruchskerze darf die zu brechende Grenze nicht mitdefinieren. Es gibt keinen universell richtigen Grenzwert.
- **Breakout:** abgeschlossener Schluss über der vorab bestimmten Range (Long) bzw. darunter (Short); Wick-Touch allein ist kein Schlusskurs-Trigger. Ein Retest muss ebenfalls mit vorher festgelegtem Zeitfenster und Preisband definiert werden. Fehl-, Nicht-Retest- und verspätete Ausbrüche im Nenner behalten.
- **Pullback:** Impuls, Rücklauf vom Impulsextrem und Strukturbruch mit festen, abgeschlossenen Bars bestimmen. Wenn eine Swing-Erkennung spätere Bars benötigt, darf der Signalzeitpunkt nicht rückdatiert werden.
- **Volumen:** Signalbar-Volumen gegen eine ausschließlich aus vorherigen Bars gebildete Basis vergleichen; Handelsplatz, Kontrakt, Volumeneinheit und Fenster dokumentieren. Volumen ist Kontext, kein Fortsetzungsbeweis.
- **VWAP / Mean Reversion:** Sessionstart und Zeitzone für VWAP (24/7 UTC-Tag und rollierendes Fenster sind verschieden) festlegen. Bei OHLCV ist Preis×Volumen nur ein Näherungsmaß. Reversion braucht vorab definierte Referenz, Abweichung, Ausstieg und Invalidierung; Trends und Regimewechsel können die Annahme brechen.
- **Multi-Timeframe:** nur die letzte vollständig abgeschlossene höhere Kerze zum Signalzeitpunkt verwenden und Datenverfügbarkeit zeitlich ausrichten. Viele Zeitrahmen/Längen zu testen erhöht Mehrfachtest-Risiko.

## Externe Evidenz und Datenstatus

### Bitget – Dokumentationshinweise, noch nicht vollständig verifiziert

Ein Recherche-Agent fand in indexierten offiziellen Bitget-Dokumentationsseiten folgende Einstiegspunkte; direkte Seitenabrufe waren hier nicht möglich. Diese Hinweise reichen nicht aus, um Schema, Produktabdeckung oder Kostenannahmen als verifiziert auszugeben.

- [Historical Candlestick Data](https://www.bitget.com/api-doc/classic/contract/market/Get-History-Candle-Data): Dokumentationsindex nennt `GET /api/v2/mix/market/history-candles`, maximal 200 Kerzen pro Anfrage und einen maximalen Anfragebereich von 90 Tagen. Historienumfang, Pagination, Grenzwerte und Timestamp-Semantik vor Nutzung gegen die aktuelle Dokumentation/API verifizieren.
- [Historical Funding Rate](https://www.bitget.com/api-doc/classic/contract/market/Get-History-Funding-Rate): möglicher eigener Endpoint für historische Funding-Raten; Feldschema und Instrumentabdeckung hier nicht direkt geprüft.
- [Public Tickers Channel](https://www.bitget.com/api-doc/classic/contract/websocket/public/Tickers-Channel): Live-Tickerfelder belegen keine historische Verfügbarkeit.
- [Stock Perps Guide](https://www.bitget.com/support/articles/12560603835927) und [FAQ](https://www.bitget.com/support/articles/12560603847596): vor der Übertragung von Aktienstrategien Produktklassifikation, Handelszeiten, Referenzpreise, Funding und Historie je Instrument verifizieren. Keine dieser Eigenschaften wurde in dieser Sitzung an Live-Instrumenten geprüft.
- [Bitget Fees](https://www.bitget.com/fee): aktuelle konkrete Maker-/Taker-Kosten sind nicht verifiziert; Gebühren können je Konto/Instrument abweichen. Nicht eine pauschale Gebühr als aktuelle Bitget-Gebühr behaupten.

Die lokale Implementierung verwendet außerdem diese live nicht geprüften Endpoint-Aufrufe zur Instrumentauswahl: [`/api/v3/market/instruments?category=USDT-FUTURES`](https://api.bitget.com/api/v3/market/instruments?category=USDT-FUTURES), [`/api/v2/mix/market/contracts?productType=USDT-FUTURES`](https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES) und [`/api/v2/mix/market/tickers?productType=USDT-FUTURES`](https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES) (`dist/app.js:56-58`). Das belegt nur, was der Code abfragt, nicht aktuelle Listings, Klassifikationssemantik oder Datenabdeckung.

Historische Trades, Quotes, Spreads und Orderbuchtiefe konnten nicht als reproduzierbare Datenquellen bestätigt werden. Bis eine passende Historie nachgewiesen ist, sind Slippage/Spread-Sensitivitäten Szenarioannahmen und kein Messwert. Das im Dashboard angezeigte aktuelle Orderbuch ersetzt keine historische Ausführungssimulation.

### Fachliteratur – Kontext, kein Nachweis für dieses Dashboard

Die nachfolgenden Arbeiten wurden durch eine interne Rechercheaufgabe als relevante Literaturhinweise identifiziert. Originaltexte konnten in dieser Sitzung nicht unabhängig abgerufen werden; die Kurzbeschreibungen sind deshalb keine eigenständige Literaturauswertung. Ihre Märkte, Zeiträume und Regeln sind nicht Bitget-USDT- oder Stock-Perpetuals und begründen keine Wirksamkeit der lokalen Scanner:

- Shen, Urquhart & Wang, [“Bitcoin intraday time series momentum”](https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/) – direkterer Krypto-/Intraday-Kontext; nicht gleichbedeutend mit 5m/15m-Einstiegen oder Bitget-Ausführung.
- [“Technical analysis in cryptocurrency markets: Do transaction costs and bubbles matter?”](https://www.sciencedirect.com/science/article/pii/S1042443122000816) – Krypto-Technikanalyse mit Kosten-/Blasenbezug; untersuchte Regeln, Venues und Zeiträume belegen keine Bitget-Perpetual-Performance.
- Brock, Lakonishok & LeBaron, [“The Profitability of Technical Trading Rules in the Stock Market”](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x) – historische Moving-Average-/Trading-Range-Break-Regeln in Aktien; kein Nachweis für heutige Intraday- oder Krypto-Regeln.
- Park & Irwin, [“What Do We Know About the Profitability of Technical Analysis?”](https://doi.org/10.1111/j.1467-6419.2007.00519.x) – Review heterogener Studien und methodischer Grenzen, kein pauschaler Wirksamkeitsbeleg.
- Lo, Mamaysky & Wang, [“Foundations of Technical Analysis”](https://doi.org/10.1111/0022-1082.00265) – formalisierte Chartmuster in US-Aktien.
- Sullivan, Timmermann & White, [“Data-Snooping, Technical Trading Rule Performance, and the Bootstrap”](https://doi.org/10.1111/0022-1082.00163) – Daten-Snooping und Mehrfachtests technischer Regeln.
- White, [“A Reality Check for Data Snooping”](https://doi.org/10.1111/1468-0262.00152) – Bootstrap-Korrektur für Mehrfachtests; ersetzt keine realistischen Daten und Fills.
- Bailey et al., [“The Probability of Backtest Overfitting”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253) – Verfahren zur Beurteilung von Backtest-Überanpassung, kein Profitabilitätsbeleg.
- Gao et al., [“Market Intraday Momentum”](https://doi.org/10.1016/j.jfineco.2018.05.009) – Intraday-Momentum in einem anderen Markt.
- Harvey, Liu & Zhu, [“...and the Cross-Section of Expected Returns”](https://doi.org/10.1093/rfs/hhv059) – Mehrfachtests in empirischer Finanzforschung.
- Osler, [“Support for Resistance: Technical Analysis and Intraday Exchange Rates”](https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html) – veröffentlichte Support-/Resistance-Niveaus im FX-Markt.
- Bertsimas & Lo, [“Optimal Control of Execution Costs”](https://doi.org/10.1016/S1386-4181(97)00012-8) – Ausführungskosten, kein Nachweis für VWAP-Prognosekraft.

Alle Quellen belegen allenfalls Befunde in den jeweils untersuchten Daten und nicht eine Trefferquote oder einen Nettovorteil des Dashboards.

## Orchestrierung und Status

**Status-Snapshot (2026-11-01):** Issue #3 ist offen/wiedereröffnet, hat keine Labels und keine Child-Issues; die Issue-Abfrage führt Copilot als Assignee. Der Snapshot sagt nichts über nicht abgefragte spätere Änderungen aus.

Die folgende Nummerierung ist eine **vorgeschlagene Struktur**, keine angelegte GitHub-Issue-Hierarchie. Jedes Thema hätte Issue #3 als direktes Eltern-Issue. Es können hier keine Child-Issues, Spezialisten-Assignees, Labels oder Issue-Kommentare angelegt werden; Arbeitsergebnisse stehen deshalb nur in diesem Bericht. Copilot ist dem Haupt-Issue zugewiesen, aber kein domain-spezifischer Agent konnte einem Child-Issue zugewiesen werden.

| Nummer (Vorschlag) | Thema / Lieferobjekt | Interne Rechercheaufgabe | Tatsächlicher Status |
|---|---|---|---|
| 1 | Bestand: Code, Daten, Wiederverwendung | `scanner-audit` | Code-Audit abgeschlossen; keine Tests mit Marktdaten. |
| 2 | Breakout/Konsolidierung/Pullback | `scanner-audit` | Regeln und Grenzen geprüft; keine echte Konsolidierungsvalidierung oder Backtest. |
| 3 | Volumen und Profile | `scanner-audit`, `patterns-mtf-volume` | Code geprüft; Definitionsvorschläge dokumentiert; API-Volumensemantik und Profilmehrwert offen. |
| 4 | MTF/Regime | `scanner-audit`, `patterns-mtf-volume` | 1h-Kontext und kausale Bar-Ausrichtung geprüft; 4h-Filter/Test offen. |
| 5 | Zusätzliche Ansätze | `strategy-evidence`, `patterns-mtf-volume` | Literaturhinweise und operationale Hypothesen dokumentiert; keine Strategie als wirksam eingestuft. |
| 6 | Krypto-Universum | `universes-tradfi` | Lokale Auswahl- und Abdeckungsrisiken geprüft; historisches Point-in-time-Universum fehlt. |
| 7 | TradFi-Übertragbarkeit | `universes-tradfi`, `bitget-data` | Code-/Produktgrenze dokumentiert; Live-Instrumente, Aktiendaten und genaue API-Semantik bleiben ungeprüft. |
| 8 | Daten/Kosten/Ausführung | `bitget-data` | Recherche abgeschlossen; direkte Dokumentationsprüfung, tatsächliche Kosten und Historienabdeckung offen. |
| 9 | Validierung/Synthese/kritischer Review | `strategy-evidence`, danach unabhängiger Kritiker | Methodik-/Literaturhinweise dokumentiert; unabhängiger Kritiker fand eine noch offene Feldtest-Lücke, Aktualisierung zur Gegenprüfung ausstehend. |

Fünf interne Rechercheaufgaben wurden gestartet; alle fünf lieferten Ergebnisse (`scanner-audit`, `bitget-data`, `strategy-evidence`, `patterns-mtf-volume`, `universes-tradfi`). Sie decken überlappende Themen ab; es wurde nicht je eine separate Aufgabe für alle neun Themen vergeben. Der lokale Code-Audit verifizierte Implementierungsdetails. Die direkte Bitget-Dokumentation und Live-Endpunkte konnten nicht unabhängig bestätigt werden; der recherchierte Candle-Historien-Endpunkt und die Limits sind deshalb nur indexierte Dokumentationshinweise. Keine Aufgabe konnte ihr Ergebnis im Issue dokumentieren. Es gab keine Agenten-Nichtantwort und daher keinen „Lost Repeat“-Status. Der unabhängige Kritiker prüfte den Bericht und die überarbeiteten Methodik-/Statuspassagen; seine letzte offene Korrektur betrifft die Erfassung nicht gehandelter Signale und wird noch eingearbeitet.

**Vorgeschlagene Label-Konvention:** Themenlabels wie `topic:breakout`, `topic:volume-profile`, `topic:tradfi`, `topic:data-costs`, `topic:validation`; Statuslabels `state:pending`, `state:in-progress`, `state:blocked`, `state:review`, `state:done`. Issue #3 selbst hat derzeit keine Labels; ob diese Labels im Repository existieren, blieb wegen Timeout der Label-Abfrage offen. Keines wurde erstellt oder gesetzt.

## Vorläufige Synthese und offene Schritte

- Keine Produktivänderung und keine Erfolgsbehauptung aus dieser Recherche ableiten.
- Als erste Untersuchung vorhandene Long-/Short-Signale gegen eine einfache, vorher festgelegte Momentum-Baseline testen; eine separate enge Konsolidierung als eigene Hypothese behandeln.
- Profile, MTF-Filter und Indikatoren jeweils nur auf inkrementellen Out-of-sample-Mehrwert prüfen; keine kumulierte Auswahl „bester“ Filter ohne Offenlegung aller Varianten.
- Crypto-Perpetuals und Stock-Perpetuals getrennt behandeln. Kosten, Funding, Datenlücken und tatsächlich erreichbare Preise pro Instrument nachweisen.
- Dashboard-Empfehlung (nicht implementiert): Treffer/Beobachtung von Bestätigung trennen; UTC-Signal- und Scanzeit, geschlossene Zeitrahmen, Datenalter/-abdeckung, verwendete Regel/Version, Trigger-/Strukturlevel sowie beobachteten Spread/Funding-Snapshot kenntlich machen. Das bleibt Beschreibung/Protokoll, keine Prognose.
- Manueller Feldtest (nicht durchgeführt): jedes qualifizierende Signal protokollieren – auch abgelehnte, verpasste und nicht gehandelte Setups samt Grund –, nicht nur tatsächlich ausgeführte Trades. Vorab Setup, Regelversion, Signalzeit und Entscheidung dokumentieren; danach bei Trades tatsächliche Ausführungszeit/-preise, Gebühren, Funding, Verzögerung und Ergebnis ergänzen. Ungehebelte Auswertung und getrennte, dokumentierte Margin-/Hebelszenarien halten Verlustverteilung und Liquidationsrisiko sichtbar. Das vorhandene Browserjournal verlangt positive Ein- und Ausstiegskurse (`dist/field.js:11`) und kann Nicht-Trade-Signale derzeit nicht erfassen; die Empfehlung setzt eine gesonderte Entscheidung/Umsetzung voraus.
- Offen bleiben GitHub-Teilaufgaben/Labels, direkte Bitget-Dokumentationsprüfung, historische Datenbeschaffung, reproduzierbarer Test samt Ergebnissen und finale Gegenprüfung durch den unabhängigen Kritiker. Issue #3 bleibt offen, bis seine Akzeptanzkriterien tatsächlich erfüllt sind.
