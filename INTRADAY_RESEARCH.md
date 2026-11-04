# Intraday-Einstiege: Arbeitsstand zu Issue #3

**Status: offen, nicht entscheidungsreif.** Dieser Bericht dokumentiert eine Bestandsaufnahme und ein überprüfbares Forschungsdesign. Er belegt weder profitable Signale noch eine Trefferquote. Es wurden keine produktiven Dashboard-Regeln geändert und keine Orders ausgelöst. Die Akzeptanzkriterien von [Issue #3](https://github.com/totosan/tokendashboard/issues/3) sind nicht erfüllt.

## Was in dieser Sitzung tatsächlich geprüft wurde

- Der aktuelle Default-Branch und die Implementierungen, Hilfetexte und TradingView-Dateien wurden geprüft. Die drei eigenständigen Pine-Strategien aus Issue #1 sind vorhanden; ihre Regeln sind Backtest-Annahmen, keine Wirksamkeitsbelege.
- `node --check` bestand für alle acht `dist/*.js`-Dateien. Das Repository hat keine vorhandene Test-/Build-Konfiguration oder Backtest-Datensätze; die inzwischen 21 Unit-Tests decken Signalsyntax, HTF-Zeitkausalität, Lückentrennung, Splitzuordnung und Bootstrap-Fälle ab. Sie prüfen keine realen Signaleffekte.
- Es wurden keine vorhandenen Artefakte zum in Issue #3 erwähnten Test mit acht Coins/45 Tagen gefunden. Der dort berichtete negative Befund ist nicht reproduziert und mangels Code, Auswahl, Daten und Kostenannahmen nicht unabhängig prüfbar.
- Die öffentlichen Bitget-APIs waren erreichbar. Für 12 ausgewählte USDT-Perpetuals wurden 5m- und 15m-Kerzen vom 2026-09-17 00:00 UTC bis 2026-11-01 00:00 UTC abgerufen: 12.960 vollständige 5m-Bars und 4.320 vollständige 15m-Bars je Symbol, keine fehlenden Bars in diesen Fenstern. Die Zeitrahmen wurden getrennt ausgewertet.
- Der TradFi-Bericht (#9) verglich die aktuellen öffentlichen Bitget-Instrumentenlisten: 307 online `stock`-RWA-USDT-Perpetuals in der geprüften Schnittmenge; davon 256 US-, 16 KR-, 11 JP-, 22 HK- und 2 CN-Region-Klassifikationen, 58 ohne ISIN. Das ist ein aktueller Snapshot, keine historische oder eindeutige Underlying-Zuordnung.
- Der TradFi-Bericht verifizierte begrenzte 1m-Kerzenproben für AAPLUSDT bis Juni 2026 sowie fünf jüngste Fundingereignisse, nicht aber lückenlose Archive. Er dokumentiert, dass der bestehende TradFi-Scanner ausschließlich Perp-Kerzen nutzt: long-only, Impuls/Pullback-/Dochttrigger, ohne zwingenden Schlusskurs über Trigger oder Mindestvolumen. Aktien-RVOL, Premarket, News/Float-Historie, historischer Spread und tatsächliche Ausführbarkeit sind nicht belegt; vollständige Details und Reproduktionsparameter stehen in [Issue #9](https://github.com/totosan/tokendashboard/issues/9).
- Der Profilbericht (#13) bestätigte, dass das Dashboard das sechste Candle-Feld als Volumen nutzt und es gleichmäßig über 24 Preis-Bins verteilt; die siebte Quote-Volumen-Spalte wird ignoriert. Live-Trade-Endpunkte waren erreichbar, aber Langzeithistorie, Retention und Einheiten wurden nicht geprüft; POC/Value-Area/RVOL-Vergleiche bleiben Hypothesen.
- Der begrenzte Bitget-Follow-up prüfte 25 öffentliche GETs; der gehashte, selektierte Antwort-/Dokumentbeleg liegt in [`bitget-followup-feasibility-2026-11-01.json`](research/data/bitget-followup-feasibility-2026-11-01.json). Für BTCUSDT und AAPLUSDT wurden je 135/135 achtstündige Funding-Zeitpunkte im Testfenster gefunden; das sind veröffentlichte Raten, keine Kontobuchungen. Je Symbol liegen außerdem sechs historische Trade-Prints vor; Cursor-Paginierung ist wegen widersprüchlicher Request-/Response-Paare nicht verifiziert. Historische Quotes/Depth wurden nicht erlangt. Vier Stock-Perps haben aktuelle US-/ISIN-/Issuer-Metadaten, aber keinen verifizierten Börsenkalender. Ein historisches Point-in-time-Krypto-Universum wurde nicht gefunden.
- GitHub-Schreibzugriff ist verfügbar: neun native Child-Issues und Topic-/State-Labels bestehen. Alle acht Fachreports und zwei unabhängige Reviews sind eingegangen. #6 ist für das Inventar geschlossen; #7/#9/#10 sind für eng begrenzte historische Datenabhängigkeiten blockiert; #11–#14 stehen nach der begrenzten Zusatz-Auswertung in Review. Die Follow-up-Reviewbefunde sind korrigiert; die Gesamt-Akzeptanzkriterien sind weiterhin nicht erfüllt.
- Keine Produktionsregeln wurden geändert und keine Orders ausgelöst. Die Akzeptanzkriterien sind nicht erfüllt; Issue #3 bleibt offen.

## Bestandsaufnahme des Dashboards

| Bereich | Aktuelle Implementierung | Aussagegrenze |
|---|---|---|
| Treppen-/Ausbruchprofil | `dist/breakout.js:3-20`: drei gerichtete Kerzen, eine Gegenkerze, 5–50 % Rücklauf und optionaler bestätigender Schlusskurs jenseits der Gegenkerze mit Volumenfilter. | Das Gegenkerzenhoch/-tief ist kein Nachweis einer eigenständigen vorherigen Seitwärtszone. Keine gemessene Fortsetzungswahrscheinlichkeit. |
| Impuls & Gegenkerzen | `dist/pattern.js:6-24`: 2–6 Impulskerzen, 2–4 fallende Gegenkerzen, Rücklauf- und Volumenbedingungen; 1m/5m, Long/Short, abgeschlossene Kerzen. | Bruch eines vorangegangenen 10-Kerzen-Hochs/-Tiefs bedeutet nicht automatisch enge Konsolidierung. Parameter sind Heuristiken. |
| Momentum-Ranking / Universum | `dist/app.js:56-59`: aktuell nach 24h-Quotevolumen gefilterte und gegebenenfalls auf Top-N begrenzte Kontrakte; Renditen aus jüngsten abgeschlossenen 1m-Kerzen. Standard laut README: Top 100 mit mindestens 10 Mio. USDT 24h-Volumen (`README.md:31`). | Die heutige Volumenauswahl ist kein historisches Point-in-time-Universum. Inaktive/fehlende Symbole und fehlgeschlagene Candle-Abfragen können die Stichprobe zusätzlich verzerren. Ranking ist kein Backtest und kein eigenständiger Entry-Nachweis. |
| TradFi-/Coin-Pullback | `dist/tradfi.js:3-19`: dieselbe Long-Musterfunktion wird auf abgeschlossenen 1m-Kerzen in beiden Ansichten genutzt. TradFi-Auswahl: API-Klassifizierung `isRwa=YES`, `instrumentType=stock`, online; sie wird mit normalen, perpetualen, USDT-quotierten Verträgen abgeglichen (`dist/app.js:56-58`). | Der Code prüft die Futures-Daten, nicht den Preis der zugrunde liegenden Aktie. Keine Nachrichten, Aktien-Relativvolumina, Float- oder Premarket-Historie. Die README nennt es eine Annäherung, keinen vollständigen Strategietest (`README.md:52-58`). Der aktuelle Status ausgewählter API-Klassifikationen wurde geprüft; Historie und Bedeutung außerhalb dieses Snapshots sind offen. |
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
| Volumen | Bestehendes Kerzenprofil/Relativvolumen als Zusatzmerkmal einzeln gegen unveränderte Baseline testen. POC/VAH/VAL erst dann vergleichen, wenn Berechnung und Datenquelle definiert sind. | Das Dashboard nutzt das Basisvolumenfeld und verteilt es gleichmäßig über Bins; das ist keine Trade-Verteilung. Live-Trade-Antworten wurden nur als erreichbar/strukturell nutzbar geprüft, nicht auf historische Abdeckung oder Kontrakteinheiten. |
| 1h-/4h-Regime | Gleiche 5m-/15m-Signale ohne Filter und mit vorher festgelegtem, ausschließlich aus bereits geschlossenen 1h-/4h-Kerzen gebildetem Regime vergleichen. | 1h-Kontext wird aktuell nur angezeigt, 4h fehlt. Unvollständige Balken und zeitliche Fehlzuordnung können Lookahead erzeugen. |
| Weitere Ansätze | EMA/Trend, Tagesniveaus, VWAP und Mean-Reversion (z. B. Bollinger/RSI) als getrennte, kausale Testarme mit benannten Marktregimen untersuchen. | Ein Indikatorname ist kein Evidenzbeleg. Trends können Reversion überrollen; Ranges können Breakouts scheitern lassen. |
| Krypto-Universum | Dieselben Regeln/Kosten auf BTC, ETH, vorab definierte Altcoin-/Liquiditätsgruppen und ein breites Universum anwenden; historische Listings und Auswahlzeitpunkt erfassen. | Aktuelles Volumen-Ranking kann Survivorship-/Auswahlbias erzeugen; korrelierte gleichzeitige Signale sind keine unabhängigen Beobachtungen. |
| TradFi-Übertragbarkeit | Aktien-Perpetuals separat je Instrument und Handelszeitabschnitt evaluieren; Derivatepreis/-volumen nicht mit Aktienkurs/-volumen gleichsetzen. | Ein aktueller Snapshot listet 307 Stock-Perps, aber nur begrenzte historische Minuten-/Fundingproben wurden überprüft. Börsenkalender, Underlying-Mapping, historische Referenzpreise, Quotes/Fills und produktspezifische Kosten bleiben offen. |
| Daten und Ausführung | Erst Candle-Zeitstempel, Kerzenschluss, Lücken, Volumeneinheiten und Instrumentlisten verifizieren. Entry frühestens am nächsten plausiblen Quote/Trade nach Scan- und manueller Verzögerung modellieren. | Live-Ticker/Orderbuch sind keine historischen Spreads, Fills oder Depth. Funding muss als zeitlich passende Kostenreihe behandelt werden. |

### Zusätzliche feste Hypothesentests (explorativ)

Nach Eingang des ersten Kritikerberichts wurden getrennte, für diesen explorativen Folgelauf fixierte Arme mit denselben bereits betrachteten Bitget-Snapshots untersucht; eine zeitlich unabhängig belegte Präregistrierung liegt nicht vor. Das ist ausdrücklich keine unberührte OOS-Prüfung. Das Skript `research/hypothesis_eval.py` speichert exakte Regeln, Parameter, Hashes, Development/OOS-Zellen, beide Seiten und alle Gruppen; alle Outcomes nutzen Signal nach Kerzenschluss und Entry am nächsten Bar-Open, danach nur einen Bar Forward.

| Arm (OOS, ereignisgewichtet über Gruppen/Richtungen) | 5m N | 5m Ø brutto / netto 12 bp | 15m N | 15m Ø brutto / netto 12 bp |
|---|---:|---:|---:|---:|
| Bestehender Treppen-Ausbruch | 304 | -1,43 / -13,43 bp | 102 | -0,32 / -12,32 bp |
| 3-Schlusskurs-Momentum | 23.167 | 0,02 / -11,98 bp | 8.136 | 0,00 / -12,00 bp |
| Momentum + RVOL ≥1,5× vorherige 20 Bars | 5.459 | 0,44 / -11,56 bp | 1.837 | 0,08 / -11,92 bp |
| Momentum + abgeschlossene 1h EMA20-Richtung | 11.337 | -0,01 / -12,01 bp | 4.260 | -0,16 / -12,16 bp |
| Momentum + abgeschlossene 4h EMA20-Richtung | 11.363 | -0,13 / -12,13 bp | 4.038 | -0,27 / -12,27 bp |
| EMA20/50-Crossover | 976 | -0,21 / -12,21 bp | 338 | 5,52 / -6,48 bp |
| UTC-Session-VWAP-Reclaim (HLC3 × Basisvolumen) | 3.124 | -0,48 / -12,48 bp | 1.646 | 0,32 / -11,68 bp |
| 12-Bar-Box, max. 2% Range, Close-Ausbruch plus Retest | 7.347 | -0,10 / -12,10 bp | 1.777 | -0,17 / -12,17 bp |

Je Zeitrahmen sind sechs OOS-Gruppen-/Richtungszellen pro Arm getrennt: 48 OOS-Zellen und 48 Entwicklungszellen, insgesamt 96 OOS-Zellen über beide Zeitrahmen. Nur eine dieser 96 OOS-Zellen liegt über dem 12-bp-Szenario: 15m EMA20/50-Crossover, Stock-Perps Long, N=46, im Mittel +0,26 bp netto; das ist eine einzelne, nachträglich betrachtete Subgruppe ohne Multiple-Testing-Korrektur oder unabhängige Bestätigung. Sie ändert nicht die übergreifende Aussage. Keine der obigen Zahlen enthält gemessenen Spread, Slippage, Funding, Liquidation oder tatsächliche Fills. 1h/4h Filter nutzen ausschließlich vollständig abgeschlossene, lückenlose UTC-Bins mit EMA20 und 20-Bin-Warmup. Fehlende abgeschlossene HTF-Bins dürfen keinen alten Kontext fortschreiben; UTC-VWAP benötigt lückenlose Bars ab Mitternacht. RVOL, EMA-Crossover, VWAP und Boxparameter sind Hypothesen, nicht reproduzierte Produktivregeln. Tageslevel, RSI/Bollinger, echtes Trade-Volumenprofil, vollständige Regime- oder Walk-forward-Tests bleiben offen.

Reproduktion: `python3 research/hypothesis_eval.py --granularity 5m --input research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz --output research/results/hypotheses-5m.json` (analog `15m`). Acht Testfälle in `research.test_hypothesis_eval` prüfen insbesondere HTF-Vollständigkeit/Warmup, veralteten HTF-Kontext, unvollständige VWAP-Sessions, Lücken und Long/Short-Boxfälle.

### Statusmatrix der Domänenberichte

Diese Matrix beschreibt den ursprünglichen Berichtsstand. Spätere Lieferungen
und heutige Issue-Stati stehen in den Fortschreibungen und der Label-Tabelle
weiter unten; insbesondere Trade-Profile und ein aktueller CHD-Replay sind
inzwischen als begrenzte Piloten vorhanden.

| Paket | Bericht / belegter Umfang | Empirischer Status |
|---|---|---|
| 1.1 Bestand | Codepfade, lokale Grenzen und bestehende Dashboard-Hypothesen in #6 inventarisiert. | Inventar-Akzeptanzkriterium erfüllt; #6 geschlossen. |
| 1.2 Breakout | Regeldefinitionen/Quellen plus bestehender Treppen-Arm und neue 12-Bar-Box-/Retest-Kandidaten auf gespeicherten Bitget 5m/15m. | Retest-Kandidat 5m N=7.347, Ø brutto -0,10 bp; 15m N=1.777, -0,17 bp. Explorativ, keine Portfolio-/Ausführbarkeitsvalidierung. |
| 1.3 Volumen/Profile | #13 beschreibt die Basisvolumen-15m-Bin-Näherung; zusätzlich wurde ausschließlich Momentum mit RVOL≥1,5× des vorherigen 20-Bar-Mittels verglichen. | Kein echtes Trade-Profil/VAH/VAL; RVOL-Arm hat negative Nettomittel unter Kosten-Szenarien, keine Mehrfachtestkorrektur. Trade-Abdeckung bleibt begrenzt. |
| 1.4 Regime/MTF | #12 prüft den Anzeige-Code; Zusatztest mit 1h/4h abgeschlossenen UTC-Bins, EMA20 und 20-Bin-Warmup als einzelne Filterarme. | Kein vollständiger Regime-/Walk-forward-Test; je 45-Tage-Fenster und schon eingesehenes OOS. Volatilitätsregime fehlt. |
| 1.5 Indikatoren | #11 lieferte kausale Vorschläge; zusätzlich EMA20/50-Crossover und UTC-HLC3/Basisvolumen-VWAP-Reclaim als getrennte Event-Arme. | EMA 15m Stock-Perp Long hat eine einzelne positive Fee-Sensitivitätszelle (N=46); unbestätigt, gruppenweise sonst keine robuste Aussage. Tageslevel, RSI/Bollinger nicht getestet. |
| 1.6 Krypto-Universum | #10 dokumentiert PIT-/Survivorship-Grenzen; aktuelle 8 Krypto-Perps wurden nur als festes Pilotpanel benutzt. | Breiter/verzerrungskorrigierter Vergleich blockiert: keine vollständige datierte Membership-/Delistinghistorie durch die geprüften Quellen belegt. |
| 1.7 TradFi | #9 dokumentiert aktuelle Stock-RWA-Perps; Zusatzprobe bestätigt vier konkrete aktuelle US-Issuer/ISIN-Mappings und AAPL/BTC-Fundingraten. | Kein offizieller Underlying-Handelskalender oder historische Börsen-/Underlying-Abbildung; ausgeführt wird nur Perp-Preis, keine Aktie. |
| 1.8 Daten/Risiko | #7 dokumentiert Bitget-Endpunkte/Limits; Zusatzprobe paginierte BTC/AAPL-Funding (135/135 Zeitpunkte) und je sechs historische Trade-Prints über kleine 1-Minuten-Proben. | Fundingrate ist kein eigener Account-Cashflow; historische Bid/Ask/Depth fehlt. Realistische Ausführung/Impact blockiert bis archivierte Quotes/Tiefe validiert werden. |
| 1.9 Kritiker | Zwei unabhängige Prüfungen in #8 reproduzierten Ergebnisse und fanden Split-/Abhängigkeitsgrenzen sowie unbelegte Trade-Paginierung; Befunde korrigiert. | Review liegt vor; Gesamtvalidierung bleibt wegen Datenblockern, kurzer Stichprobe und fehlender unabhängiger Bestätigung offen. |

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

## Explorative Bitget-Auswertung

Dies ist eine begrenzte, deskriptive Vorwärtsbewegungs-Auswertung, kein Portfolio-Backtest und keine Wirksamkeits- oder Gewinnbestätigung. Der Lauf verwendet `research/intraday_eval.py`, sieben Unit-Tests, den gespeicherten Candle-Snapshot und den zugehörigen Ereignis-/Ergebnisexport unter `research/data/` und `research/results/`. Snapshot und Ergebnisdateien sind mit SHA-256 prüfbar; der Code kann dieselben Kennzahlen offline aus dem Snapshot erzeugen.

| Merkmal | Festlegung |
|---|---|
| Quelle/Zeitraum | Bitget `/api/v2/mix/market/history-candles`, USDT-FUTURES, `kLineType=market`; 2026-09-17 00:00 bis 2026-11-01 00:00 UTC. 12 derzeit gelistete Kontrakte, 8 Krypto (BTC/ETH plus SOL/BNB/XRP/DOGE/ADA/LINK) und 4 Aktien-Perpetuals (TSLA/NVDA/AAPL/COIN); 12.960/12.960 5m-Bars und 4.320/4.320 15m-Bars je Symbol, keine Lücken im angefragten Intervall. |
| Zeitaufteilung | Chronologisch: erste 30 Tage Entwicklung, letzte 15 Tage OOS ab 2026-10-17 00:00 UTC. Ereignisse werden nach Entry-Bar-Zeit klassifiziert, nicht nach Signalzeit; so werden grenzüberschreitende Folgekerzen nicht in die Entwicklungsmetriken übernommen. Keine Parametersuche; ein vorab fixierter Treppen-Ausbruch mit Standard-Volumenfilter 1,0× und eine 3-Schlusskurs-Momentum-Baseline. |
| Ausbruch | Drei gerichtete Kerzen mit steigenden orientierten Schlusskursen, eine Gegenkerze, 5–50 % Rücklauf, Struktur über dem Impulsursprung und Gegenkerzenhoch höchstens 0,2 % über Impulshoch; bestätigende abgeschlossene Kerze schließt gerichtet über dem Gegenkerzenhoch/-tief und ihr Quotevolumen erreicht mindestens das der Gegenkerze. Das spiegelt die Standardregeln aus `dist/breakout.js`; echte vorausgehende Seitwärtskonsolidierung wird nicht verlangt. |
| Ausführung/Metriken | Signal erst nach Schluss der Bestätigungskerze; angenommener Einstieg zum Open der nächsten 15m-Kerze und Ausstieg zu deren Close. MFE/MAE beziehen sich auf dieselbe Folgekerze. Überlappende Ereignisse bleiben enthalten; es gibt keine Portfolio-/Drawdown-Simulation und keine Unsicherheitsintervalle. |
| Kosten | 12 bp Round Trip = zwei aktuelle Taker-Gebühren von je 6 bp aus dem beigefügten Instrument-Snapshot. Zusätzlich werden 22/37 bp mit angenommenen 10/25 bp Round-Trip-Spread-/Slippage-Aufschlag ausgewiesen. Historische Gebühren und historische Spread-/Slippage-Daten fehlen; die Zusatzkosten sind Sensitivitätsszenarien, keine Messwerte. |

OOS-Richtungsergebnisse der **15m-Auswertung**, ausgerichtete Renditen in Basispunkten (bp). „Netto 12 bp“ zieht den angenommenen Round-Trip-Kostenwert von jedem Ereignisergebnis ab. Ein positiver Bruttowert oder eine Trefferquote ist kein Beleg für positive Nettoerwartung:

| Ansatz | Gruppe | Richtung | N | Ø / Median brutto | Treffer brutto | Ø netto bei 12 bp |
|---|---|---:|---:|---:|---:|---:|
| Treppen-Ausbruch | BTC/ETH | Long | 7 | -7,67 / -4,66 | 14,3 % | -19,67 |
| Treppen-Ausbruch | BTC/ETH | Short | 11 | -5,57 / 0,75 | 63,6 % | -17,57 |
| Treppen-Ausbruch | Altcoins | Long | 22 | 2,50 / -0,07 | 50,0 % | -9,50 |
| Treppen-Ausbruch | Altcoins | Short | 27 | -4,27 / -5,27 | 25,9 % | -16,27 |
| Treppen-Ausbruch | Aktien-Perpetuals | Long | 20 | 6,45 / 4,62 | 65,0 % | -5,55 |
| Treppen-Ausbruch | Aktien-Perpetuals | Short | 15 | 0,89 / 0,26 | 53,3 % | -11,11 |
| 3-Schlusskurs-Baseline | BTC/ETH | Long | 656 | -1,74 / -1,38 | 44,7 % | -13,74 |
| 3-Schlusskurs-Baseline | BTC/ETH | Short | 736 | 0,43 / -0,18 | 49,7 % | -11,57 |
| 3-Schlusskurs-Baseline | Altcoins | Long | 1.961 | -0,80 / -1,37 | 46,1 % | -12,80 |
| 3-Schlusskurs-Baseline | Altcoins | Short | 2.041 | 0,85 / -1,32 | 46,1 % | -11,15 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Long | 1.299 | 0,06 / -0,58 | 45,6 % | -11,94 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Short | 1.443 | 0,41 / -0,00 | 49,4 % | -11,59 |

OOS-Richtungsergebnisse der **5m-Auswertung**, gleiche Definitionen, Universe und Kostenannahmen:

| Ansatz | Gruppe | Richtung | N | Ø / Median brutto | Treffer brutto | Ø netto bei 12 bp |
|---|---|---:|---:|---:|---:|---:|
| Treppen-Ausbruch | BTC/ETH | Long | 22 | -3,61 / 0,68 | 54,5 % | -15,61 |
| Treppen-Ausbruch | BTC/ETH | Short | 26 | 1,88 / -0,00 | 50,0 % | -10,12 |
| Treppen-Ausbruch | Altcoins | Long | 72 | -2,37 / -1,53 | 41,7 % | -14,37 |
| Treppen-Ausbruch | Altcoins | Short | 85 | -0,87 / -0,49 | 43,5 % | -12,87 |
| Treppen-Ausbruch | Aktien-Perpetuals | Long | 36 | 1,34 / 0,00 | 41,7 % | -10,66 |
| Treppen-Ausbruch | Aktien-Perpetuals | Short | 63 | -3,28 / -0,81 | 42,9 % | -15,28 |
| 3-Schlusskurs-Baseline | BTC/ETH | Long | 2.045 | -0,14 / -0,38 | 48,0 % | -12,14 |
| 3-Schlusskurs-Baseline | BTC/ETH | Short | 2.093 | 0,06 / -0,49 | 46,9 % | -11,94 |
| 3-Schlusskurs-Baseline | Altcoins | Long | 5.710 | -0,29 / -0,86 | 45,2 % | -12,29 |
| 3-Schlusskurs-Baseline | Altcoins | Short | 5.962 | 0,41 / -0,00 | 47,0 % | -11,59 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Long | 3.569 | 0,04 / 0,00 | 45,9 % | -11,96 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Short | 3.788 | -0,09 / -0,00 | 46,4 % | -12,09 |

In beiden einzelnen 15-Tage-OOS-Fenstern liegt der mittlere Netto-Ereignisertrag jeder Tabellenzeile unter null bereits unter der günstigen 12-bp-Gebührenannahme. Der unabhängige Review fand grenzüberschreitende Events, die zuvor anhand der Signalzeit dem Entwicklungsfenster zugeschlagen wurden; die Auswertung wurde korrigiert, nun anhand der Entry-Bar klassifiziert und beide Ergebnisdateien/-tabellen neu berechnet. Die 15m-Treppen-Signale sind selten (N=7–27 pro Gruppe/Richtung); die 5m-Stichprobe ist größer, bleibt aber eine kurze, gezielt ausgewählte Stichprobe. Selbst die häufigere Baseline erzeugt korrelierte Ereignisse. Die unten ergänzte Tagesblock-Sensitivität liefert explorative Perzentilintervalle, keine Mehrfachtestkorrektur oder Point-in-time-Symbolhistorie. Die 4 TradFi-Symbole bleiben Futures-Perpetuals, keine Aktienkurs-/Aktienvolumentests. Keine Schlussfolgerung über andere Zeiträume oder Symbole ist daraus zulässig.

Für Offline-Wiederholung: `python3 -m unittest research.test_intraday_eval -v`. Bei gespeicherten Snapshots muss `--granularity` explizit gesetzt werden; Event-Exporte können komprimiert als `.csv.gz` geschrieben werden. Die Ergebnis-JSONs enthalten außerdem den SHA-256-Hash des ausgewerteten Snapshots:

```sh
python3 -m unittest research.test_intraday_eval -v
python3 research/intraday_eval.py --granularity 5m --input research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz --summary research/results/bitget-5m-2026-09-17_2026-11-01.json --events research/results/bitget-5m-2026-09-17_2026-11-01-events.csv.gz
python3 research/intraday_eval.py --granularity 15m --input research/data/bitget-15m-2026-09-17_2026-11-01.csv.gz --summary research/results/bitget-15m-2026-09-17_2026-11-01.json --events research/results/bitget-15m-2026-09-17_2026-11-01-events.csv.gz
```

## Nacharbeit: Abhängigkeit und Unsicherheit

`research/event_uncertainty.py` ergänzt die bestehende Event-Studie um eine
reproduzierbare Sensitivitätsanalyse: 2.000 Bootstrap-Ziehungen ganzer UTC-Tage,
Seed 20261101, synchron über Symbole und beide Vergleichsarme. Auch Tage ohne
Signale bleiben enthalten. Der Schätzer ist der ereignisgewichtete Mittelwert,
nicht der Mittelwert gleichgewichteter Tagesmittel. Die 95%-Perzentilintervalle
und die Differenz Treppen minus Momentum-Baseline stehen für Entwicklung/OOS,
Gruppe, Richtung und Zeitrahmen in `research/results/uncertainty-{5m,15m}.json`.
Die Eingabe-Hashes und Zellhäufigkeiten werden festgehalten bzw. geprüft.

Das ist eine explorative Wiederverwendung des bereits betrachteten OOS-Fensters,
keine neue unangetastete Validierung. Die Intervalle sind nicht für Mehrfachtests
korrigiert; Abhängigkeit über Tagesgrenzen bleibt unmodelliert. Nur 15 OOS-Tage
und wenige aktive Breakout-Tage machen die Intervalle instabil. Zudem
werden leere Bootstrap-Ziehungen ausgelassen: das 15m-BTC/ETH-Long-Breakout-OOS-Intervall
und seine Paardifferenz basieren auf 1.996 von 2.000 Ziehungen und sind damit
auf nichtleere Ziehungen konditioniert. Beispielsweise
enthält das 5m-BTC/ETH-Short-Nettointervall unter 12 bp auch null
(-17,07 bis 0,27 bp), obwohl der Punktschätzer negativ bleibt. Die positive
relative 15m-Stock-Long-Differenz zur Baseline ist weder ein positiver
Nettoerwartungswert noch ein korrigierter Evidenznachweis. Ein-Bar-Returns je
Symbol/Arm liegen in aufeinanderfolgenden, nicht zwingend überlappenden
Haltefenstern; gemeinsame Lookbacks und zeitgleiche Symbole/Arme erzeugen dennoch
Abhängigkeit. Es gibt weiterhin keine Portfolio-/Margin-/Fill-Simulation.

```sh
python3 -m unittest research.test_hypothesis_eval research.test_event_uncertainty research.test_intraday_eval -v
python3 -m research.event_uncertainty --events research/results/bitget-5m-2026-09-17_2026-11-01-events.csv.gz --summary research/results/bitget-5m-2026-09-17_2026-11-01.json --output research/results/uncertainty-5m.json
python3 -m research.event_uncertainty --events research/results/bitget-15m-2026-09-17_2026-11-01-events.csv.gz --summary research/results/bitget-15m-2026-09-17_2026-11-01.json --output research/results/uncertainty-15m.json
```

## Externe Evidenz und Datenstatus

### Bitget – direkt beobachtete öffentliche API-Antworten

- Der direkte Aufruf von [`/api/v2/mix/market/history-candles`](https://api.bitget.com/api/v2/mix/market/history-candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=15m&limit=200) lieferte `code=00000`. Die Antwortzeilen enthalten Zeitstempel, OHLC und zwei Volumenfelder; die lokal genutzte `dist/orderbook.js`-Implementierung verwendet das sechste Datenfeld (API-Antwortindex 5) als Volumen-Näherung, während die Ausbruchsauswertung das siebte Feld (Index 6, Quotevolumen in der beobachteten Antwort) verwendet. Abdeckung und Volumensemantik sind im Snapshot dieser Stichprobe dokumentiert, aber nicht mit historischen Trades abgeglichen.
- Die eingefrorenen 5m- und 15m-Datensätze enthalten 155.520 beziehungsweise 51.840 Bars über dieselben 12 Symbole. Reproduzierbare Rohdaten-Exporte: [`5m CSV.GZ`](research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz) und [`15m CSV.GZ`](research/data/bitget-15m-2026-09-17_2026-11-01.csv.gz); Kennzahlen und Ereignisse stehen im `research/results/`-Verzeichnis. Die Resultate beziehen sich nur auf diese gezielt ausgewählte Stichprobe.
- Der öffentliche [`/api/v3/market/instruments?category=USDT-FUTURES`](https://api.bitget.com/api/v3/market/instruments?category=USDT-FUTURES)-Abruf meldete für ausgewählte Kontrakte `status=online`, `type=perpetual`; die vier Aktien-Perpetuals wurden als `instrumentType=stock`, `isRwa=YES` klassifiziert. Der gespeicherte Snapshot vom 2026-11-01 15:07:38.919 UTC enthält die 12 tatsächlich verwendeten Symbole und Felder: [`bitget-instruments-2026-11-01.json`](research/data/bitget-instruments-2026-11-01.json).
- Dieser Snapshot zeigt für die ausgewählten 12 Instrumente `makerFeeRate=0.0002`, `takerFeeRate=0.0006`, `fundInterval=8`. Das sind zeitpunktbezogene Produktmetadaten, keine bestätigten individuellen Kontogebühren oder historischen Sätze. Die Auswertung nutzt ausschließlich den 6-bp-Taker-Satz als klare Kostenannahme; Finanzierung wurde für den ursprünglichen Eventlauf nicht als zeitlich passender Cashflow verrechnet.
- Ein separat datierter Follow-up speichert 25 öffentliche GET-Abfragen, ausgewählte Antworten/Dokumentation und Hashes in [`bitget-followup-feasibility-2026-11-01.json`](research/data/bitget-followup-feasibility-2026-11-01.json). Für BTCUSDT und AAPLUSDT wurden jeweils 200 paginierte Funding-Historien-Zeilen eingelesen; im festgelegten Fenster [2026-09-17 00:00, 2026-11-01 00:00) UTC ergeben sich 135 von 135 8h-Gridpunkten ohne Lücken oder Duplikate. Bei AAPL sind 13 der 135 Sätze ungleich null; der BTC-Snapshot hat 135 nicht-null Werte. Das sind veröffentlichte Fundingraten, nicht Kontobuchungen und kein Nachweis anderer Symbole.
- `fills-history` lieferte für je einen konkreten BTCUSDT- und AAPLUSDT-Minutenabschnitt zwei Antworten mit je drei Prints, sechs eindeutige IDs pro Symbol. Die gespeicherten Request-Paare wiederholen denselben `idLessThan`-Cursor; einige Antwort-IDs widersprechen ihm. Deshalb ist Cursor-Paginierung hier nicht verifiziert; die ursprünglichen Belege bleiben unverändert erhalten, die Schlussfolgerungen wurden eingeschränkt. Kein historischer BBO oder Depth-Snapshot wurde zurückgewonnen. Bitgets Depth-Dokumentation verweist auf öffentliche historische Archive, aber die dokumentierten Seiten-/GET-Probes lieferten keine Datei; das beweist nicht, dass die Archive fehlen oder Login erfordern. Roh-HTTP-Hashes sind ohne die nicht gespeicherten Bytes nicht nachrechenbar; kanonische Hashes vollständiger gespeicherter JSON-Antworten sind überprüfbar.
- Aktuelle V3-Metadaten ordnen AAPLUSDT (Apple, US, ISIN US0378331005), TSLAUSDT (Tesla, US, US88160R1014), NVDAUSDT (Nvidia, US, US67066G1040) und COINUSDT (Coinbase Global, US, US19260Q1076) als Stock-Perps ein; für diese vier zeigen die gespeicherten `launchTime`-Werte den 02.02.2026 UTC. Das ist Bitget-Instrumentmetadaten, keine unabhängig bestätigte Primärbörse/Session. Felder zu Börsen-MIC, Zeitzone, Handelszeiten, Feiertagen/verkürzten Sitzungen oder Historien-Mapping wurden nicht geliefert.
- Der aktuelle BTC-USDT-Perpetual-Eintrag hat `launchTime="0"`; die geprüften V3-Instruments-/V2-Contracts-Endpunkte dokumentieren aktuelle Zustände, aber kein vollständiges datiertes Point-in-time-Listing-/Delistingarchiv. Historische Universe-Mitgliedschaft lässt sich nicht aus heute aktiven Symbolen, leeren Werten oder Candle-Lücken rekonstruieren.
- Ergebnis: #7 ist für historische ausführbare Quote-/Depth-Kosten blockiert, nicht für öffentliche Fundingraten oder kleine Trade-Probes. #9 ist für Börsenkalender-gekoppelte Aktien-Sessionvergleiche blockiert; Perp-only-Daten bleiben auswertbar. #10 ist für einen survivorship-korrigierten breiten PIT-Universumstest blockiert. Diese klar begrenzten Blocker und nächste Schritte stehen in den jeweiligen Issues.

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

**Abgeglichen am 2026-11-03:** Issue [#3](https://github.com/totosan/tokendashboard/issues/3) ist offen, mit `topic:research` und `state:in-progress`. Die folgenden nativen GitHub-Child-Issues wurden mit direktem Parent #3 erstellt:

| Nummer | Arbeitspaket / direktes Child-Issue | Topic / tatsächlicher Status |
|---|---|---|
| 1.1 | [#6 Bestandsaufnahme](https://github.com/totosan/tokendashboard/issues/6) | `topic:inventory` · `state:done` · Bericht mit Codezeilen/Abgrenzung eingereicht; geschlossen |
| 1.2 | [#14 Breakout, Konsolidierung und Pullback](https://github.com/totosan/tokendashboard/issues/14) | `topic:breakout` · `state:review` · fester Box-/Retest-Kandidat plus Treppen-Ausbruch getestet; keine Nettowirksamkeitsbehauptung |
| 1.3 | [#13 Volumen und Profile](https://github.com/totosan/tokendashboard/issues/13) | `topic:volume-profile` · `state:blocked` · Trade-Minuten-/Stundenprofile und 5m-Candle-Abgleich vorhanden; Open-Differenzen, breitere Ledger-Abdeckung und Validierung offen |
| 1.4 | [#12 Marktregime und MTF](https://github.com/totosan/tokendashboard/issues/12) | `topic:regime-mtf` · `state:review` · UTC-HTF-Filter und kausale Regime/Breakoutdiagnostik explorativ getestet, #18 begrenzt akzeptiert; frische Validierung offen |
| 1.5 | [#11 Trend, VWAP und Mean Reversion](https://github.com/totosan/tokendashboard/issues/11) | `topic:indicators` · `state:review` · EMA/VWAP sowie Tageslevels/RSI/Bollinger explorativ getestet, #17 begrenzt akzeptiert; frische Validierung offen |
| 1.6 | [#10 Krypto-Universum](https://github.com/totosan/tokendashboard/issues/10) | `topic:crypto-universe` · `state:blocked` · geprüfte Bitget-Endpunkte lieferten kein vollständiges PIT-Listing-/Delistinguniversum; Pilotpanel ist current-survivor |
| 1.7 | [#9 TradFi-Übertragbarkeit](https://github.com/totosan/tokendashboard/issues/9) | `topic:tradfi` · `state:blocked` · vier aktuelle Issuer/ISIN-Mappings und AAPL-Fundingproben; Underlying-Kalender/Mapping für Sessiontest fehlt |
| 1.8 | [#7 Daten, Ausführung und Risiko](https://github.com/totosan/tokendashboard/issues/7) | `topic:execution-risk` · `state:blocked` · CHD-Trades, separater aktueller sequenzkonsistenter Book-Pilot und öffentlicher REST-Sampler vorhanden; ursprüngliche historische Ausführungsabdeckung bleibt offen |
| 1.9 | [#8 Validierung, Synthese und unabhängiger Review](https://github.com/totosan/tokendashboard/issues/8) | `topic:validation` · `state:blocked` · Kandidat #24 unabhängig geprüft und als begrenzte Lieferung akzeptiert; neue Inferenz INCONCLUSIVE, bisherige Kalibrierung FAIL, frische Validierung offen |

Die acht Domänenberichte 1.1–1.8 liegen vor. Nach dem ersten unabhängigen Review wurde die Split-Zuordnung korrigiert; anschließend wurden feste Hypothesenarme, Tagesblock-Sensitivität und begrenzte Bitget-Feasibility-Proben ergänzt. Der zweite Review wurde am 02.11.2026 direkt in #8 veröffentlicht und ist nicht mehr ausstehend; er fand insbesondere die damals unbelegte Trade-Cursor-Paginierung. Die Aussage wurde zunächst auf kleine Print-Stichproben eingeschränkt. Inzwischen akzeptiert #15 einen begrenzten Zwei-Seiten-/Cursor-Test, nicht die Vollständigkeit des Ledgers; #25 ergänzt CHD-Handelsdaten und einen separaten aktuellen Book-Replay. Zusätzlich wurden veralteter HTF-Kontext nach fehlenden Bins und unvollständige VWAP-Sessions durch Regressionstests abgesichert. #7 bleibt für die ursprünglich benötigte historische Quotes-/Tiefenabdeckung und das Ausführungsmodell blockiert. #9 ist für einen Börsenkalender/Underlying-Sessionvergleich blockiert, nicht für Perp-only-Daten. #10 ist für ein vollständiges point-in-time Delisting-Universum blockiert; das 12-Symbol-Panel bleibt ein heutiger Survivor-Pilot. #11–#14 haben getrennte Hypothesentests und Resultate; die OOS-Zeitspanne war bereits betrachtet, daher keine unberührte Validierung. #8 bleibt nach Integration der begrenzten Reviews offen. Die Stati sind genau ein `state:*`-Label pro Issue; keine Gesamtvalidierung wird allein aus erfolgreichen Code-/Testläufen abgeleitet.

**Tatsächlich erstellte Labels:** Topics `topic:research`, `topic:inventory`, `topic:breakout`, `topic:volume-profile`, `topic:regime-mtf`, `topic:indicators`, `topic:crypto-universe`, `topic:tradfi`, `topic:execution-risk`, `topic:validation`; States `state:pending`, `state:in-progress`, `state:blocked`, `state:review`, `state:done`. Die Konvention ist ein `topic:*`-Label für den Arbeitsbereich plus genau ein `state:*`-Label für den aktuellen Status. Statusangaben hier sind der zuletzt verifizierte GitHub-Snapshot, keine Erfolgsaussage.

### Umsetzung nach steigendem Aufwand

Die erste Ausführungswelle besteht aus zwei nativen Kindern von #7: 1.8.1
[#15](https://github.com/totosan/tokendashboard/issues/15) prüft sequenzielle
Trade-Cursor; danach erweitert 1.8.2
[#16](https://github.com/totosan/tokendashboard/issues/16) die Funding-Abdeckung.
Der zweite Schritt benötigt ein begrenztes Ergebnis oder einen dokumentierten
Blocker des ersten Schritts, nicht dessen Erfolg. Der historische
Quotes-/Impact-Blocker des Elternpakets verhindert diese Teilaufgaben nicht.

1.8.1 hat inzwischen zwei sequenzielle 3-Print-Seiten je BTCUSDT/AAPLUSDT mit
vier öffentlichen GETs ohne Retry geprüft. Neue, separate Evidenz:
[`bitget-trade-pagination-2026-11-02T160432.624978Z.json`](research/data/bitget-trade-pagination-2026-11-02T160432.624978Z.json).
`research/trade_pagination.py` speichert unveränderliche Requestparameter,
Originalbytes (Base64), decodierte Antworten und nachrechenbare Hashes;
`research.test_trade_pagination` prüft zwölf Fälle inklusive ungültiger
Cursor-Grenzen, Duplikate und Fensterverletzungen. Das verifiziert nur
Cursor-Konsistenz dieser Stichprobe, keine vollständige Trade-Abdeckung und
keine historische Ausführbarkeit. Der frühere widersprüchliche Beleg bleibt
unverändert und wird dadurch nicht rückwirkend validiert.
Reproduktion: `timeout 140s python3 -m research.trade_pagination`;
Offline-Prüfung: `python3 -m unittest research.test_trade_pagination -v`.
1.8.2 hat anschließend mit 25 öffentlichen GETs neue Funding-Antworten für
alle zwölf Pilotsymbole gespeichert:
[`bitget-funding-history-2026-11-02T160715.916809Z.json`](research/data/bitget-funding-history-2026-11-02T160715.916809Z.json).
Die 1.620 Fensterzeilen zeigen keine Lücken gegenüber dem aus aktuellen
Metadaten abgeleiteten **provisorischen** Settlementraster. Ohne historische
Schedule-Änderungen ist das kein vollständiger historischer Abdeckungsnachweis.
Öffentliche Raten sind keine Kontobuchungen. Eine Zuordnung zu hypothetischen
Halteintervallen `[entry, exit)` wäre eine Szenariokonvention, keine verifizierte
Bitget-Ownership-Regel; Funding-P&L wird hier nicht berechnet.
Reproduktion: `timeout 300s python3 research/funding_history.py`;
zehn Offline-Fälle: `python3 -m unittest research.test_funding_history -v`.
Der unabhängige Kritiker hat diese neue Datenwelle in #8 ohne verifizierte
handlungsrelevante Befunde geprüft; 22 gezielte Offline-Tests sowie Raw-/
Canonical-Hashes wurden nachgerechnet. Der Koordinator bestätigt insgesamt
45 bestandene Research-Tests. Damit sind die begrenzten Lieferumfänge von
#15/#16 abgeschlossen, nicht die historischen Vollständigkeitsfragen.
Die breiteren Blocker
von #7/#9/#10 und die explorative Natur der bisherigen Eventtests bleiben bestehen.

Die folgende begrenzte Fachagentenaufgabe ist 1.5.1
[#17](https://github.com/totosan/tokendashboard/issues/17), natives Kind von #11:
feste kausale Prior-UTC-Day-Level-, Wilder-RSI14- und Bollinger20-Reentry-Arme,
ausschließlich offline auf den vorhandenen Snapshots. Der Fachagent hat den
Protokollbeleg `research/results/indicator-protocol.json`, zwei
`indicators-{5m,15m}.json` und 14 neue Tests geliefert. Je Zeitrahmen stehen
36 Indikatorzellen und 24 unverändert übernommene Baselinezellen bereit;
60 Gesamtzellen sind nicht 60 OOS-Zellen. Der Gesamt-Testlauf umfasst nun
59 Tests. Der unabhängige Kritiker hat in #8 keine verifizierten
handlungsrelevanten Befunde gemeldet: alle 14 gezielten Tests bestanden,
beide Ausgaben mit je 60 Zellen exakt reproduziert und Hashes geprüft.
Der begrenzte Lieferumfang von #17 ist damit akzeptiert; die breitere
Validierung von #11/#8 bleibt offen.

| Neuer Arm, OOS ereignisgewichtet | 5m N / Ø brutto | 15m N / Ø brutto |
|---|---:|---:|
| Vorheriges vollständiges UTC-Tageshoch/-tief, Close-Ausbruch | 769 / +1,84 bp | 454 / -3,49 bp |
| Wilder RSI14, Reclaim 30/70 | 1.368 / -0,46 bp | 503 / -2,15 bp |
| Bollinger20, 2 Populations-Standardabweichungen, Reentry | 3.082 / -0,23 bp | 1.025 / -0,73 bp |

Alle 18 Indikator-OOS-Gruppen-/Richtungszellen je Zeitrahmen sind nach
12 bp Kostenannahme im Mittel negativ; 22/37 bp sind zusätzliche Szenarien.
Die Protokollregeln fixieren Gleichheiten, Warmup, Lücken und vollständige
Vortage. UTC-Derivatelevels sind keine Underlying-Börsensessions. Neue
Fundingdaten werden nicht als Cashflows in diese Ereignisrenditen gemischt.
Das bereits eingesehene Fenster bleibt explorativ, ohne Mehrfachtestkorrektur
oder unabhängige Wirksamkeitsbestätigung.

Nach Akzeptanz von #17 bearbeitet der Regime-Fachagent 1.4.1
[#18](https://github.com/totosan/tokendashboard/issues/18), natives Kind von #12
mit Bezug zu #14. Der Auftrag trennt kausale Volatilitäts-/Trendmerkmale von
retrospektiven Box-Ausbruch-Fehl-/Verzögerungsdiagnosen. Die Lieferung enthält
`research/results/regime-protocol.json`, `regimes-{5m,15m}.json` und sieben
neue Tests; der Gesamt-Testlauf umfasst 68 Tests. Features verwenden
vergangenheitsbasierte TR/Close-Volatilität, vorherige 100 Featurewerte für
Terzile und ER20 mit fester 0,30-Grenze. Baseline-Exporte wurden mit Snapshots
abgeglichen (69.752 5m- und 24.627 15m-Ereignisse).
Bei vollständigen, nicht über die Splitgrenze reichenden Boxfenstern wurden
11.677/22.733 (5m) beziehungsweise 3.011/5.955 (15m) retrospektiv als FAILED
markiert. Das sind keine prädiktiven Inputs, Erfolgsquoten oder Portfoliozahlen.
Der unabhängige Review fand zunächst fehlende Erstfehler-Zeitpunkte trotz
Protokollanforderung. Die Korrektur ergänzt disjunkte Offset-1/2/3-/Kein-Fehler-
Zähler: 5m 6.913/2.943/1.821/11.056, 15m 1.845/745/421/2.944. Ihre Nenner
sind die genannten vollständigen, nicht über die Splitgrenze reichenden
Fenster. Wiederholte Reentries zählen nur beim ersten Fehler.
Neun gezielte Tests prüfen nun auch diese Zeitpunkte. Die unabhängige
Nachprüfung in #8 akzeptiert die Korrektur ohne verbleibende Befunde:
beide Replays/Hashes stimmen exakt; Timingzähler und Verzögerungszuordnung
gleichen sich aggregiert und in allen 120 Regimezellen ab. Der begrenzte
Lieferumfang von #18 ist akzeptiert, nicht die breitere Regimevalidierung.

Als nächste Daten-Gate-Aufgabe bearbeitet ein Fachagent 1.7.1
[#19](https://github.com/totosan/tokendashboard/issues/19) unter #9:
autoritative Underlying-/Session-Zuordnung für die vier Stock-Perps mit maximal
zwölf öffentlichen Quellabfragen. Ein ehrlicher Nichtverifizierungsbeleg ist
ein zulässiges Feasibility-Ergebnis, aber keine Entsperrung von #9.
Die Lieferung
[`bitget-session-feasibility-2026-11-02.json`](research/data/bitget-session-feasibility-2026-11-02.json)
umfasst sechs öffentliche GET-URLs bzw. sieben HTTP-Transaktionen inklusive
einer Weiterleitung. Vier aktuelle Bitget-Kontraktmetadaten und offizielle
Nasdaq-/NYSE-Kalenderseiten sind belegt; keine Börse, MIC, Zeitzone oder
historische Zuordnungskontinuität ist damit einem Perp autoritativ zugeordnet.
Ohne Bitgets symbolbezogene Referenzmarkt-Spezifikation und deren
Änderungshistorie wird kein Kalender angewendet. Der unabhängige Review in #8
meldet keine wesentlichen Befunde und bestätigt das Transaktionsbudget.
Die Raw-Hashes sind ohne nicht gespeicherte Originalbytes nicht nachrechenbar;
ausgewählte Belege sind entsprechend gekennzeichnet. Der begrenzte
Feasibility-Lieferumfang ist akzeptiert; #9 bleibt blockiert.
1.8.3 [#20](https://github.com/totosan/tokendashboard/issues/20) unter #7
lieferte anschließend
[`bitget-archive-feasibility-2026-11-02.json`](research/data/bitget-archive-feasibility-2026-11-02.json):
zwei frische öffentliche GETs mit 218.184 Responsebytes, ohne Archivsample.
Der Client nennt einen Listingpfad, aber dessen unterstützter Vertrag/Methode
und Produkttypcodes bleiben unbestätigt; der GET liefert HTML 404.
Der frühere 405-Probe beweist keinen notwendigen Nicht-GET-Zugriff.
Originalbytes der ausgewählten neuen Belege sind nicht gespeichert und deren
Raw-Hashes deshalb nicht offline nachrechenbar. Der unabhängige Kritiker in
#8 fand keine verifizierten handlungsrelevanten Befunde und bestätigte
JSON-Struktur sowie Byte-Summen gegen die zitierten Vorbelege.
Der begrenzte Feasibility-Lieferumfang ist akzeptiert; #7 bleibt blockiert;
fehlende Datei bedeutet weder Archiv-Abwesenheit noch Loginpflicht.

Empirische Tradeprofile (#13, Aufwandsposition 7) bleiben mangels vollständiger
Tradefenster blockiert. Als unabhängiges nächstes Gate ist 1.6.1
[#21](https://github.com/totosan/tokendashboard/issues/21) unter #10
vorbereitet: begrenzte offizielle Quellenprüfung für historische
Universumsmitgliedschaft, keine breite Rekonstruktion aus heutigen Survivors.
Die Lieferung
[`bitget-universe-feasibility-2026-11-02.json`](research/data/bitget-universe-feasibility-2026-11-02.json)
speichert sechs öffentliche GETs mit 164.725 Responsebytes einschließlich
Originalbytes und Hashes. Drei datierte Announcement-Abfragen für Listings,
Delistings und Wartung wurden mit HTTP 400/API 70010 zurückgewiesen:
der Zeitraum liege nicht innerhalb der letzten 30 Tage. Das ist eine
Beschränkung dieser Abfragen, kein Nachweis fehlender älterer Mitteilungen.
Selbst vollständige Publikationszeit-Suchen wären kein vollständiges
Effective-Date-Lifecycle-Ledger. Manifest-Schema, sechs Vollständigkeits-Gates
und eine konkrete offizielle Datenanforderung sind festgehalten.
Der unabhängige Kritiker in #8 meldet keine handlungsrelevanten Befunde.
Damit ist der begrenzte Quellencheck akzeptiert; historische Vollständigkeit
und Identität bleiben unverifiziert und #10 bleibt blockiert.

Als Aufwandsposition 9 bearbeitet ein Validierungsmethodik-Fachagent 1.9.1
[#22](https://github.com/totosan/tokendashboard/issues/22) unter #8:
ein eingefrorenes Fixed-Panel-Walk-forward-Protokoll mit Offline-Readiness-
Audit. Die vorhandenen Fenster sind bereits eingesehen und dürfen nicht
nachträglich zum frischen Holdout erklärt werden. Reservierte zukünftige
Prüfperioden benötigen noch Daten, Warmup-/Outcome-Grenzen, purged Splits und
eine vorab definierte Abhängigkeits-/Mehrfachtestbehandlung. Ein
`NOT_READY`-Beleg ist keine durchgeführte Walk-forward-Validierung.
Diese begrenzte Vorbereitung autorisiert weder einen Bulkdownload noch
Portfolio-/Liquidationssimulationen ohne deren Datenvoraussetzungen.
Der Fachagent hat `research/results/walkforward-protocol.json`,
`walkforward-readiness.json`, Auditmodul und sechs Tests geliefert. Der
Gesamt-Testlauf umfasst nach der Korrektur 75 Tests; die gemeldeten 53 beziehen sich auf einen
Teilsatz ohne die 22 Trade-/Funding-Tests. Bestehende Snapshots bestehen die
Integritätsprüfung, aber alle drei reservierten 28-Tage-Folds vom
01.02. bis 26.04.2027 sind mangels künftiger Beobachtungen samt 96h-Warmup
`NOT_READY`; der Audit beendet sich erwartungsgemäß mit Exitcode 2.
Ereignisrenditen und Inferenz bleiben `NOT_RUN`. Der unabhängige Kritiker fand
eine unbegründete Auslassung der drei separat getesteten Indikatorarme in
der ursprünglichen Acht-Arm-Familie. Protokoll v2 nimmt nun alle elf bereits
getesteten Signal-Arme auf (132 primäre Hypothesen), pinnt die zusätzlichen
Regeln an den Indikator-Protokollhash und dokumentiert die v1-Scope-Lücke ohne
rückwirkende Präregistrierungsbehauptung. Die unabhängige Nachprüfung in #8
bestätigt die Korrektur ohne verbleibende Befunde: elf Arme, 132 Hypothesen,
Regeln/Hashes und Report-Replay (bis auf Generierungszeit) stimmen überein;
sieben gezielte Tests bestanden, tatsächlicher Audit-Exitcode 2.
Der begrenzte Protokoll-/Readiness-Lieferumfang von #22 ist akzeptiert.
Die eigentliche Walk-forward-Validierung bleibt `NOT_READY`/`NOT_RUN`.

Die höchste Aufwandsstufe (ausführbares Portfolio-/Margin-/Liquidationsmodell)
wird nicht durch diese Readiness-Prüfung freigegeben: historische Quotes,
verifizierte Kontrakt-/Marginregeln sowie vorab fixierte Sizing-/Overlap-
Annahmen fehlen weiterhin. Ebenso bleiben vollständige Tradeprofile,
historische Underlying-Sessions und PIT-Universumsvergleiche datenabhängig.
Diese Aufgaben bleiben in #7/#9/#10/#13/#8 offen; die abgeschlossenen
Feasibility-Kinder dürfen nicht als Erfüllung dieser Elternkriterien gelten.

| Reihenfolge | Paket / zuständiges Issue | Evidenz-Gate |
|---|---|---|
| 1, klein | Trade-Paginierung, #15 unter #7 | Sequenzielle Cursor, IDs, Duplikate und Zeitfenster anhand gespeicherter Antworten prüfen; maximal acht öffentliche GETs. |
| 2, klein | Funding-Pilotuniversum, #16 unter #7 | Raten, Zeitraster und Lücken je Symbol; Settlement-Grenzkonvention explizit, keine Kontobuchungsbehauptung. |
| 3, mittel | Tageslevel/RSI/Bollinger, #11 | Feste kausale Long-/Short-Regeln, Baselines und vollständige Ergebniszellen; bestehendes Fenster bleibt explorativ. |
| 4, mittel | Volatilitätsregime und Fehl-/Spätausbrüche, #12/#14 | Vergangenheitsbasierte Labels und nachvollziehbare Nenner; keine Auswahl nur positiver Zellen. |
| 5, mittel | Aktien-Sessionmapping, #9 | Autoritative Börsen-/Zeitzonen-/Feiertagszuordnung vor Sessiontests. |
| 6, groß | Historische Quotes/Depth, #7 | Erst eine kleine Archivdatei samt Timestamp-/Symbol-/Depth-Semantik validieren, dann Abdeckung erweitern. |
| 7, groß | Tradebasierte Profile, #13 | Verifizierte Trade-Abdeckung nötig; sechs Prints und reine Cursor-Verfügbarkeit reichen nicht. |
| 8, sehr groß | Historisches Krypto-Universum, #10 | Vollständigkeitsprüfung datierter Listings/Delistings vor breitem PIT-Vergleich. |
| 9, sehr groß | Längere Walk-forward-Prüfung, #8 | Regeln vor neuen Prüfperioden einfrieren; Daten-Gates je Teiluniversum, Abhängigkeit und Mehrfachtests behandeln. |
| 10, höchster Aufwand | Ausführbares Portfolio/Risiko, #7/#8 | Historische Quotes, explizite Sizing-/Overlap-/Marginregeln und unabhängiger Review vor Drawdown-/Liquidationsaussagen. |

Die Reihenfolge beschreibt relativen Implementierungsaufwand, keine garantierte
Laufzeit. Je Paket erhält ein Fachagent einen begrenzten Auftrag mit exklusiven
Dateien, Request-Budget, Netzwerk- und Kommando-Timeouts, Offline-Fehlertests und
einem Ergebnisbericht im zugeordneten Issue. Der Koordinator prüft Artefakte und
Reproduktion; ein unabhängiger Kritiker folgt auf die tatsächlich gelieferte
Welle. Keine unbeschränkten Polling-/Downloadschleifen. Nicht reagierende Agenten
werden gemäß #3 einmal erneut angefragt und nur bei belegtem wiederholtem
Ausfall als verloren markiert. Spätere Pakete sind noch nicht gestartet;
fehlende externe Daten werden nicht als implementierbar ausgegeben.

### Recovery-Welle am 02.11.2026

Die Live-Prüfung vor Reaktivierung fand keine Hintergrundagenten und kein
`Lost Repeat`-Label. Frühere Fachagenten lieferten ihre akzeptierten Ergebnisse;
ein nicht mehr verfügbarer Runtime-Handle belegt keinen verlorenen Auftrag.
Die abgeschlossenen Kinder #15–#22 bleiben geschlossen.

Vier neue, dateiseitig getrennte Fachaufträge bearbeiten engere offene
Voraussetzungen statt identische fehlgeschlagene Quellenproben zu wiederholen:
Endpunkt-Erschöpfung eines festen AAPL-Minutenfensters und bedingtes Tradeprofil
(#13/#7); offizieller Download-HTTP-Helper sowie aktuelle Margin-/Risk-Tier-
Spezifikation (#7); gültige rezente Announcement-Abfrage und offizielle
Referenzmarkt-Spezifikation ohne historische Inferenz (#9/#10); synthetische
Nullkalibrierung synchroner Tagesblöcke und der 132-Test-Familie (#8).

Öffentliche Quellabfragen haben endliche Request-/Bytebudgets, zehn Sekunden
pro HTTP-Anfrage und 180 Sekunden pro Live-Kommando; Offline-Kommandos sind
auf 120 Sekunden begrenzt. Jeder Auftrag liefert Artefakte, Tests oder einen
präzisen Blocker im zugeordneten Issue. Ein unabhängiger Review folgt erst
auf die tatsächlich gelieferte Welle. Historische Quotes, vollständige
PIT-/Session-Ledger und künftige Validierungsbeobachtungen werden dadurch
nicht implizit als verfügbar erklärt. Keine Produktivänderungen oder Orders.

Die vier Recovery-Fachagenten haben geliefert; der unabhängige Wellenkritiker
in #8 meldet keine handlungsrelevanten Befunde. Er bestätigt 37 gezielte Tests
und deterministischen Replay unter den dokumentierten Offline-Evidenzgrenzen.
Die begrenzten Implementierungs-/Diagnoselieferungen sind akzeptiert,
nicht die historischen Vollständigkeits- oder Inferenz-Gates.
Gesamt-Teststand: 100 Tests.
Das AAPL-Minutenfenster wurde mit zwei GETs bis zu einer leeren Terminalseite
abgefragt (elf eindeutige Trades): Endpunkt-Erschöpfung, keine unabhängige
Ledger-Vollständigkeit. Ein fixes 20-Bin-Profil liegt vor; der Vergleich mit
einer echten identischen Minutenkerze wurde mangels Beleg nicht erfunden.
Gültige rezente Announcement-Abfragen liefern acht Listing- und zwei
Delisting-Mitteilungen, jedoch kein historisches Opening-Inventar.
Publikationszeit-Konflikte von acht Stunden bleiben sichtbar.

Der offizielle Download-Helper liefert einen POST-Default und `/v1`-Prefix;
der Host ist aus dem Seitenursprung abgeleitet, nicht explizit konfiguriert.
Nach zwölf Quellrequests wurde kein POST mehr gesendet; die Depth-Parameter-
Zuordnung bleibt offen. Aktuelle BTC-/AAPL-Margintiers sind keine historischen
Liquidationsregeln.

Die synthetische Block-Nullkalibrierung ist ausdrücklich **FAIL**:
medianer marginaler Typ-I-Fehler über der fixierten Toleranz in allen vier
Szenarien; 14 von 120 Sparse-Familien sind ungültig. Mit 199 Bootstrap-Draws
ist der minimale p-Wert 0,005, gröber als die erste Holm-Schwelle für 132 Tests.
Null Holm-Rejektionen validieren deshalb keine Familienkontrolle.
Kein Tuning zum Bestehen, keine Marktdaten und keine Bestätigung der
zukünftigen Readiness. Inferenz darf mit diesem Ergebnis nicht freigegeben
werden; die implementierte synthetische Diagnose ist kein erfolgreicher
Kalibrierungsnachweis.

### Verknüpfte Fortsetzungen nach Statusprüfung

Nach erneuter Prüfung aller neun Domänen und nativen Beziehungen wurden
zwei offene Fortsetzungen angelegt und tatsächlich an Fachagenten vergeben:
1.8.4 [#23](https://github.com/totosan/tokendashboard/issues/23) unter #7
prüft offizielle Depth-Filter und höchstens eine nachweislich anonyme,
rein lesende POST-Listing-Anfrage. 1.9.2
[#24](https://github.com/totosan/tokendashboard/issues/24) unter #8
spezifiziert vor Simulation einen einzelnen Kalibrierungs-Neuentwurf mit
expliziten Null-/Abhängigkeitsannahmen und ausreichender p-Wert-Auflösung.
Vorherige FAIL-Artefakte und das zukünftige Protokoll bleiben unverändert;
ein Kandidatenresultat ändert keine reservierten Prüfregeln automatisch.

Die Lieferungen beider Kinder wurden wiederhergestellt, unabhängig geprüft
und für ihren begrenzten Umfang akzeptiert (`state:done`). Beim Archive-Agenten war der alte Laufzeithandle nicht mehr
verfügbar; es lief kein zu beendender Forschungsprozess. Die gespeicherten
Dateien und die fehlende Übergabe in #23 wurden ohne neue HTTP-Anfrage
wiederhergestellt. Der unabhängige Review in #8 bestätigte nach Bereinigung
gespeicherter Response-Header keine weiteren belastbaren Befunde.
Regressionen prüfen sowohl neue Captures als auch das gespeicherte Artefakt;
die vollständige Research-Suite besteht mit 122 Tests.
#7 bleibt für historische ausführbare Abdeckung blockiert; #8 bleibt wegen
offener Kalibrierung und fehlender reservierter Beobachtungen blockiert,
nicht in laufender Marktvalidierung. #13 bleibt für fehlende Daten blockiert. Die akzeptierten
Kinder #15–#22 bleiben geschlossen.

`research/archive_listing_probe.py` bewahrt zwei offizielle JavaScript-GETs
mit unveränderten Body-Hashes; Cookie-/Authorization-Header werden vor der
Speicherung entfernt. Numerische Futures-Depth-Filter, POST-Standard und
`/v1`-Präfix sind belegt. Die Laufzeit-Interceptors lassen endgültigen Host,
Payload und anonyme Header-Anforderungen jedoch offen:
`BLOCKED_ANONYMOUS_WIRE_CONTRACT_UNPROVED`, null POSTs, kein Quote-Sample.
Der Blocker beweist weder fehlende Archive noch erforderlichen Privat-Zugang.

`research/inference_redesign.py` liefert einen vorher spezifizierten
Known-Covariance-Gaussian-Oracle, keinen Markt-Schätzer. Analytische p-Werte
vermeiden die grobe Bootstrap-Auflösung; 600 Panels je Szenario unterschreiten
aber die vorab verlangten 2.000 vollständigen Familien:
`INCONCLUSIVE`. Unvollständige Sparse-Familien werden verweigert; absichtlich
falsche IID-Kovarianz bei AR1 ergibt `FAIL`. Ursprüngliche FAIL-Artefakte und
das reservierte Walk-forward-Protokoll bleiben unverändert. Budgetgrenzen
und präzise Blocker ersetzen weder historische Daten noch valide Inferenz.

### Alternative Archivquelle: CryptoHFTData (03.11.2026)

Die verifizierten offiziellen Setup-Anweisungen von
<https://www.cryptohftdata.com/agent-setup/prompt.md> wurden ausgeführt:
Agent-Paket 0.2.0 mit SHA-256-Prüfung und sicherer Archivextraktion,
vollständiger Skill unter `~/.copilot/skills/chd`, SDK `cryptohftdata==0.8.0`
in einer isolierten Umgebung unter `~/.local/share/cryptohftdata/venv`.
Projekt-Abhängigkeiten bleiben unverändert. Die aktuelle Skill-Registry erkennt
die Neuinstallation noch nicht; automatische Aktivierung ist bis zu einer
neuen Sitzung ausstehend. Die installierten Anweisungen wurden direkt gelesen,
SDK-/API-Prüfungen funktionierten bereits ohne Schlüssel oder Anmeldung.

Für `bitget_futures` meldete die API je 1.213 registrierte Trade- und
Orderbook-Symbole, darunter BTCUSDT und AAPLUSDT. Zwei Dateien aus dem
bisherigen Forschungsfenster wurden tatsächlich geladen und mit PyArrow
gelesen, nicht nur anhand konstruierter URLs vermutet:

| Objekt unter `bitget_futures/2026-09-17/14/` | Bytes | Zeilen |
| --- | ---: | ---: |
| `AAPLUSDT_trades.parquet` | 31.212 | 1.720 |
| `AAPLUSDT_orderbook.parquet` | 1.666.571 | 318.807 |

Die vollständigen Schemas, Hashes, lokalen Pfade und Abrufbefehle stehen in
`research/data/chd-setup-verification-2026-11-03.json`. Rohdateien verbleiben
lokal unter `~/.local/share/cryptohftdata/samples/2026-11-03-bitget/`.
Für 14:30–14:31 UTC stimmen alle elf Trade-Tupel
(ID, Zeit, Preis, Menge) mit der zuvor gesicherten offiziellen Bitget-Antwort
überein; das ist Quellenkonsistenz in einer Minute, kein vollständiger Ledger.

**Der Zugangstransport ist damit für diese zwei Samples gelöst, der
Gesamtblocker nicht.** CHD ist eine Drittanbieterquelle und umgeht den weiterhin
ungeklärten offiziellen Bitget-Website-Request. Das Orderbook-Sample enthält
ausschließlich Updates, keinen initialen Snapshot; von den Sequenzfeldern ist
nur `final_update_id` befüllt. Vor historischen Spread-/Depth-/Slippage-Werten
brauchen wir belegte Update-/Reset-/Gap-Semantik und einen passenden Startzustand.
Danach folgen begrenzte Abdeckungsprüfungen je Symbol und Zeitraum. #7 bleibt
für diese Datenqualitäts-/Replay-Gates blockiert, nicht wegen fehlenden
anonymen CHD-Zugangs. Historische Vollständigkeit, Candle-Abgleich, valide
Inferenz und reservierte künftige Beobachtungen bleiben unbewiesen.

Ein anschließender begrenzter Snapshot-Recovery-Versuch lud die drei
vorhergehenden AAPLUSDT-Orderbook-Stunden 13, 12 und 11 UTC vom 17.09.2026
anonym (zusammen 3.837.654 Bytes). Einschließlich der vorhandenen Stunde
14 wurden 917.717 Zeilen geprüft: ausschließlich Updates, null Snapshot-Zeilen,
`prev_final_update_id` durchgehend leer. Deshalb wurde **kein Checkpoint
erzeugt**; ein aus leerem Zustand aufgebautes Buch würde unveränderte Levels
unterschlagen. Diese begrenzte Suche beweist keine archivweite Abwesenheit.
`research/data/chd-snapshot-search-2026-11-03.json` hält Pfade, Hashes,
Zeitgrenzen, Ergebnis und einen noch nicht versandten Support-Entwurf fest.
Nächster belastbarer Schritt: CHD nach einem konkreten kompatiblen historischen
Snapshot und verifizierbarer Sequenzkette beziehungsweise einem Replay-Bericht
fragen; alternativ einen belegten Snapshot-Zeitraum gesondert untersuchen.

### Umgesetzter Budget-Pfad: Trade-first und getrennte aktuelle Books

Der Umsetzungsplan ist als natives Kind #25 unter #7 verfolgt; #13 ist
fachlich beteiligt. Reihenfolge nach Aufwand: vorhandene Trades auswerten,
höchstens zwei aktuelle CHD-Book-Dateien prüfen, anschließend einen begrenzten
öffentlichen Snapshot-Recorder bauen. Es wurden weder kostenpflichtige Daten
beschafft noch die alte Stichprobe oder das reservierte Protokoll geändert.

1. **Trade-first umgesetzt:** `research/budget_chd_study.py` erstellt mit
   Dezimalarithmetik lokale 1m-OHLCV-/VWAP-Bars und das bereits eingefrorene
   deskriptive 20-Bin-Profil. Der AAPLUSDT-Trade-Stunde vom 17.09.2026
   14 UTC entsprechen 1.720 beobachtete Trades und 1.316,18 Basiseinheiten.
   Beim Vergleich aller zwölf 5m-Buckets mit den gespeicherten offiziellen
   Candles stimmen High, Low, Close, Basis- und Quote-Volumen exakt überein;
   alle zwölf Open-Werte unterscheiden sich. Diese Differenz bleibt sichtbar
   und ist vor Interpretation der Candle-Open-Konvention zu klären, kein
   Anlass, Rohtrades anzupassen. Fehlende Beobachtungen werden nicht als
   Nullvolumen aufgefüllt. Kosten 12/22/37 bp bleiben Annahmen; keine
   Strategie-Returns oder Inferenz wurden berechnet. Artefakt:
   `research/results/budget-trades-2026-11-03.json`.
2. **Aktueller separater Replay umgesetzt:** Bereits die erste geprüfte CHD-Datei
   `bitget_futures/2026-11-03/14/AAPLUSDT_orderbook.parquet`
   (2.962.734 Bytes, 623.967 Zeilen) enthält einen Checkpoint-Snapshot.
   Alle 39.163 folgenden Update-Nachrichten verketten sich innerhalb dieser
   Datei über `pseq/seq`; keine Kettenbrüche oder gekreuzten Books wurden
   beobachtet. Ein abgeleiteter Checkpoint am letzten beobachteten
   Receive-Zeitpunkt liegt lokal, nicht als Ersatz für September. Dies ist
   **dateiinterne Sequenzkonsistenz**, keine unabhängige Exchange-/Checksum-
   Zertifizierung oder Garantie vollständiger Levels. Gap-/Cross-Fälle
   verwerfen den Zustand bis zum nächsten Snapshot. Readiness und Replay:
   `research/results/budget-recent-book-2026-11-03.json` und
   `research/results/budget-recent-replay-2026-11-03.json`. Spread-Zusammenfassungen
   sind nach Nachrichten gewichtet, nicht nach Zeit und keine Fill-Kosten.
3. **Vorwärts-Erfassung umgesetzt:** `research/bitget_snapshot_recorder.py`
   nutzt nur den dokumentierten öffentlichen REST-GET
   `/api/v3/market/orderbook`, ohne Schlüssel. Jede Beobachtung ist ein
   eigenständiges aktuelles Top-N-Book; dies ist bewusst **Polling, kein
   kontinuierlicher WebSocket-/Delta-Recorder**. So sind Snapshot-Start und
   Replay-Ketten für diese einzelnen Beobachtungen nicht nötig. Grenzen:
   höchstens eine Stunde pro Aufruf, 3.600 Requests, 1 Request/s,
   10 Sekunden pro Request, 1 MiB pro Antwort und 20 MiB JSONL.
   Neue Ausgabeverzeichnisse verhindern Überschreiben. Fehler, veraltete oder
   gekreuzte Books führen zu expliziten Partial-/Failure-Manifests, nie zu
   einer Vollständigkeitsbehauptung. Drei echte Top-50-AAPL-Snapshots wurden
   erfolgreich aufgenommen und rehashiert; der Prozess endete normal.
   `research/data/budget-recorder-smoke-2026-11-03.json` verweist auf lokale
   Rohbytes.

Reproduktion im Repository-Root (neue Output-Namen verwenden):

```sh
CHD_PY="$HOME/.local/share/cryptohftdata/venv/bin/python"
SAMPLES="$HOME/.local/share/cryptohftdata/samples"
timeout 90s "$CHD_PY" -m research.budget_chd_study trades \
  --source "$SAMPLES/2026-11-03-bitget/AAPLUSDT-2026-09-17-14-trades.parquet" \
  --candles research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz \
  --output /tmp/aapl-trades-replay.json
timeout 90s "$CHD_PY" -m research.budget_chd_study replay \
  --source "$SAMPLES/2026-11-03-budget/AAPLUSDT-2026-11-03-14-orderbook.parquet" \
  --checkpoint /tmp/aapl-current-derived-checkpoint.json \
  --output /tmp/aapl-current-book-replay.json
timeout 60s python3 -m research.bitget_snapshot_recorder \
  --directory "$SAMPLES/new-aapl-recording" --samples 3 --interval 2 --depth 50
timeout 120s python3 -m unittest research.test_budget_chd_study \
  research.test_bitget_snapshot_recorder
```

**Manuelle Voraussetzung:** Für diese begrenzten Piloten war keine nötig.
Nur für dauerhaft laufende Erfassung muss der Nutzer später einen stabilen,
eingeschalteten Rechner/VPS und dessen Speicher-/Betriebsbudget bereitstellen;
hier läuft kein unbeaufsichtigter Dauerdienst. Kein kostenpflichtiges Abo,
Support-Kontakt oder API-Key ist Voraussetzung des implementierten Pfads.
Der aktuelle CHD-Skill konnte inzwischen direkt geladen werden; die zuvor
ausstehende Aktivierung ist damit für diese Sitzung bestätigt.
#7 bleibt für die ursprüngliche historische Ausführungsabdeckung offen,
#13 für umfassendere Profil-/Candle-/Ledger-Validierung; #8 bleibt hinsichtlich
praktikabler Inferenz und künftiger reservierter Beobachtungen blockiert.
Ein unabhängiger Code-Review des Budget-Pfads fand keine belastbaren
Implementierungsfehler; 16 gezielte Tests und der aktuelle Book-Replay wurden
dabei geprüft. Die vollständige Research-Suite besteht mit 138 Tests.

## Vollständiger Zustands- und Lückenabgleich vom 2026-11-03

Maßgeblich für den jetzigen Stand ist dieser Abgleich, nicht frühere
Warteschlangen-Kommentare. Die maschinenlesbare Bestandsaufnahme
[`research/results/state-audit-2026-11-03.json`](research/results/state-audit-2026-11-03.json)
enthält alle 23 Issues, die native Hierarchie, Evidenz-Hashes und die folgenden
16 Restarbeiten mit Zuständigkeit und Abhängigkeiten. Geprüfter Implementierungsstand:
`bb21d18`; die Audit-Dokumentation selbst implementiert keine dieser Restarbeiten.

**Agenten und Übergaben:** Es war kein Research-Shell-/Download-/Recorder-Prozess
aktiv und keine sichtbare Sitzung wartete auf Eingabe oder Planfreigabe. Der
einzige sichtbare Child-Agent war der bereits fertig ausgelieferte, ruhende
Budget-Reviewer; sein Ergebnis ist integriert. Ältere nicht mehr erreichbare
Handles sind kein Beleg für verlorene Arbeit. Die früher geborgenen Lieferungen
sind über Commits und Akzeptanzkommentare nachvollziehbar. Kein aktueller
`Lost Repeat`-Fall und kein fehlender bereits beauftragter Review wurde gefunden;
dies ist keine Zusicherung über unsichtbare historische Prozesse.

| Bereich | Tatsächliche Lieferung | Was noch nicht erledigt ist |
|---|---|---|
| #1, getrennte frühere Arbeit | Drei Pine-Skripte/README über den gemergten PR #2 vorhanden; #1 geschlossen. | TradingView-Kompilierung/Strategy-Tester-Lauf ausdrücklich nicht verifiziert; optionaler manueller Provider-Runtime-Check, kein verlorener Agent. |
| #3 / #6 | Inventar akzeptiert; alle neun Domänen nativ zugeordnet; #6 geschlossen. | Gesamtakzeptanz des Research-Epics nicht erreicht. |
| #7 | #15/#16/#20/#23/#25 begrenzt akzeptiert; Funding-/Trade-Evidenz, CHD-Pilot, aktueller Replay und REST-Sampler vorhanden. | Vollständige historische Ausführungsabdeckung, übergreifende Replay-/Abdeckungsprüfung, historische Kosten-/Risiko- und Portfoliomodelle. |
| #8 | #22/#24 Vorbereitung/Diagnostik und mehrere unabhängige Teilreviews geliefert. | Echter Future-Evaluator, praktikable kalibrierte Inferenz, frische Daten und abschließender Gesamt-Review. |
| #9 / #10 | #19/#21 Feasibility sowie aktuelle Referenzen und neuere Bekanntmachungen geliefert. | Historische Session-/Underlying-Referenzkette bzw. vollständiges PIT-Universum; Eltern bleiben blockiert. |
| #11 / #12 | #17 Tageslevels/RSI/Bollinger und #18 kausale Regime/Fehlausbruch-Timing akzeptiert; EMA/VWAP/HTF-Vergleiche vorhanden. | Explizite Eltern-Akzeptanz/Synthese und frische Wirksamkeitsvalidierung, nicht erstmalige Implementierung. |
| #13 | Trade-Minuten-/Stundenprofile und zwölf offizielle 5m-Vergleiche vorhanden. | Alle zwölf Opens weichen ab; kausale rollierende Profile/VAH/VAL/HVN/LVN und breitere Abdeckung nicht fertig. |
| #14 | Treppen-Arm, feste Box-/Retest-/Fehlausbruch-/Verzögerungsdiagnostik vorhanden. | Vollständige Abdeckung weiterer Originalscanner und Eltern-Akzeptanz; keine frische Wirksamkeitsevidenz. |
| #26, separat | Ausgearbeitete, zurückgestellte Idee. | Kein Pi-Dienst, Dauerbetrieb, WebSocket-Recorder oder Analyse-Frontend implementiert/beauftragt. Kein Blocker für #3. |

`state:review` bei #11/#12/#14 bedeutet hier **offene Eltern-Akzeptanz**, nicht
einen aktuell laufenden Agenten. Geschlossene #15–#25 gelten nur für die in
ihren Akzeptanzkommentaren genannten begrenzten Lieferungen; ältere ungepflegte
Checkboxen sind kein Gegenbeleg zu diesen Lieferungen. Insbesondere macht die
Schließung der Vorbereitung #22 den später gescheiterten Inferenzplan nicht
gültig: ursprüngliche Kalibrierung `FAIL`, synthetischer Oracle-Kandidat
`INCONCLUSIVE`, empirische Validierung `NOT_RUN`.

### Gesammelte Restarbeit, nach relativem Aufwand

Die IDs sind dauerhaft zitierbare Einträge dieses Backlogs, keine neuen
Issue-Nummern. Die jeweiligen offenen Eltern besitzen die Arbeit; es werden
keine parallelen Doppelaufträge erzeugt.

| ID / Aufwand | Zuständig | Konkreter nächster Schritt / Abhängigkeit |
|---|---|---|
| G01 / klein, jetzt möglich | #13 | Die zwölf 5m-Open-Abweichungen anhand unveränderter Rohdaten erklären; Candle-Konvention und benachbarte Empfangsstunden/Ereigniszeit prüfen, Regression ergänzen. |
| G02 / klein, jetzt möglich | #11/#12/#14, #8 | Elternkriterien explizit gegen akzeptierte Lieferungen prüfen; verbleibende Fachanforderungen von der Gesamtvalidierung trennen. Keine laufenden Reviewer unterstellen. |
| G03 / mittel, jetzt möglich | #7 | Reproduzierbaren begrenzten CHD-Download-/Cache-/Manifest- und Umgebungsablauf erstellen, auf frischer Umgebung prüfen. Lokale Rohdateien und venv sind nicht portabel gesichert; es gibt keine CI. |
| G04 / mittel | #13 | Nach G01/G03 kausale rollierende POC/VAH/VAL/HVN/LVN-/Profilwechselregeln und fairen Baselinevergleich festlegen. 20-Bin-Trade- und 24-Bin-Kerzenprofile sind noch kein solcher Vergleich. |
| G05 / mittel | #14/#9 | Originale Gegenkerzen-/First-new-high-Regeln aus `dist/pattern.js`/`dist/tradfi.js` mit Paritätstests und nötigen 1m-Daten als gesonderte explorative Studie abdecken. Nicht still in die eingefrorenen elf Arme aufnehmen. |
| G06 / mittel | #7 | Nach G03 weitere Symbole/Tage, Empfangsgrenzen und Mehrdatei-Replay prüfen; validierten Checkpoint-Import ergänzen. Aktuell wird nur ein Checkpoint exportiert und eine Datei replayt. |
| G07 / mittel, jetzt möglich | #8 | Tatsächlichen Frozen-Protocol-Evaluator auf synthetischen/bereits inspizierten Fixtures bauen: elf Arme, Entry-Folds, 96h-Warmup, Purge/Embargo, 1/2/3-Bar-Horizonte und Mindestereignisse. Readiness ist kein Return-Evaluator. |
| G08 / groß, methodisch blockiert | #8 | Praktikablen Schätzer/Nullhypothese für abhängige Daten, Sparse-Cells und 132-fache Testfamilie spezifizieren und kalibrieren. Mehr Oracle-Simulationen allein lösen das nicht. |
| G09 / kalenderabhängig | #8 | Nach G07/G08 reservierte Folds 01.02.–26.04.2027 exklusiv samt Warmup beschaffen und auswerten. Diese Beobachtungen existieren noch nicht; Termine nicht nachträglich verschieben. |
| G10 / groß, Quellenblocker | #10 | Historisches Anfangsinventar und effektives Listing-/Delisting-/Halt-/Identitätsledger beschaffen, Zeitkonflikte auflösen; danach PIT-Vergleich. |
| G11 / groß, Quellenblocker | #9 | Historische Underlying-/Referenzvenue-/Zeitzonen-/Kalender-/Halt-Zuordnung belegen; heutige ISINs und Feednamen reichen nicht. |
| G12 / groß, Daten/Modell | #7 | Nach G06 zeitlich passende Spread-/Tiefe-, Latenz-, Gebühren- und Fundingannahmen belegen. Separate aktuelle Buchstunde und 12/22/37-bp-Szenarien sind keine September-Fills. |
| G13 / höchster Aufwand | #7/#8 | Nach G12/G08 Overlap, Sizing, Allokation, historische Margin-/Liquidationsregeln und Account-Cashflows modellieren, bevor Drawdown-/Hebelzahlen berichtet werden. |
| G14 / mittel, nach Voraussetzungen | #8/#3 | Nach Fachakzeptanz und Validierung bzw. explizit eingegrenztem Endumfang Gesamtvergleich/Review durchführen und Integration von Draft-PR #5 entscheiden. |
| G15 / später, ausdrücklich zurückgestellt | #26 | Erst bei Aktivierung Host/Budget wählen; Rotation, Persistenz, Rate-Limits, Neustart/SIGTERM/Disk-full, ARM64-Dauertest und optionales WebSocket-Replay entwickeln. |
| G16 / separate Produktentscheidung | #3/#26 | Integriertes Analyse-UI und Journal auch für verworfene/nicht gehandelte Signale sind nicht konkret beauftragte Lieferungen. Erst Produktumfang entscheiden, nicht als bereits vorhandene Funktion darstellen. |

**Empfohlener erster Implementierungsschritt:** G01, anschließend G03/G06.
Das baut auf dem kostenlosen vorhandenen Pfad auf, benötigt keinen
Hardwarekauf und verringert konkrete Datenunsicherheit. G07 kann unabhängig
mit vorhandenen/synthetischen Fixtures entwickelt werden; G08 darf nicht
durch ein erfolgreiches Test-Suite-Ergebnis übersprungen werden.

**Abgleichbelege:** Die Research-Suite besteht erneut mit 138 Tests. Die
Readiness-Prüfung mit tatsächlichen vorhandenen Inputs liefert erwartungsgemäß
Exit 2, `NOT_READY` / `NOT_RUN`, bei passenden eingefrorenen Source-Versionen.
Lokale CHD-Rohdateien und Hashes wurden geprüft. PR #5 bleibt offen und Draft;
Teilreviews sind keine auf GitHub eingereichten Approvals, und es wurden keine
CI-Checks gemeldet. Die bisherigen Budget-Implementierungen sind somit auf
dem PR-Head, nicht im gemergten Default-Branch.

### Wiederverwendbare Skills

Für künftige Arbeiten liegen drei GitHub-Copilot-Skills unter `.github/skills/`:
[`market-data-reliability`](.github/skills/market-data-reliability/SKILL.md)
für API-/Zeit-/Replay-/Prozess- und Reproduzierbarkeitsfehler,
[`crypto-perpetual-research`](.github/skills/crypto-perpetual-research/SKILL.md)
für Marktdateninterpretation, Bias, Kosten und Inferenz, sowie
[`research-epic-orchestration`](.github/skills/research-epic-orchestration/SKILL.md)
für Agenten-, Issue-, Review- und Recovery-Koordination. Sie verallgemeinern
die hier beobachteten Fehlerklassen, nicht die persönlichen Annahmen oder
temporären lokalen Pfade dieses Projekts.

Der Startprompt und die präzisen Grenzen für die nächste frische Epic-Sitzung
stehen in [`EPIC-3-SESSION-HANDOFF.md`](EPIC-3-SESSION-HANDOFF.md).

## Vorläufige Synthese und offene Schritte

- Keine Produktivänderung und keine Erfolgsbehauptung aus dieser Recherche ableiten.
- Als erste Untersuchung vorhandene Long-/Short-Signale gegen eine einfache, vorher festgelegte Momentum-Baseline testen; eine separate enge Konsolidierung als eigene Hypothese behandeln.
- Profile, MTF-Filter und Indikatoren jeweils nur auf inkrementellen Out-of-sample-Mehrwert prüfen; keine kumulierte Auswahl „bester“ Filter ohne Offenlegung aller Varianten.
- Crypto-Perpetuals und Stock-Perpetuals getrennt behandeln. Kosten, Funding, Datenlücken und tatsächlich erreichbare Preise pro Instrument nachweisen.
- Dashboard-Empfehlung (nicht implementiert): Treffer/Beobachtung von Bestätigung trennen; UTC-Signal- und Scanzeit, geschlossene Zeitrahmen, Datenalter/-abdeckung, verwendete Regel/Version, Trigger-/Strukturlevel sowie beobachteten Spread/Funding-Snapshot kenntlich machen. Das bleibt Beschreibung/Protokoll, keine Prognose.
- Manueller Feldtest (nicht durchgeführt): jedes qualifizierende Signal protokollieren – auch abgelehnte, verpasste und nicht gehandelte Setups samt Grund –, nicht nur tatsächlich ausgeführte Trades. Vorab Setup, Regelversion, Signalzeit und Entscheidung dokumentieren; danach bei Trades tatsächliche Ausführungszeit/-preise, Gebühren, Funding, Verzögerung und Ergebnis ergänzen. Ungehebelte Auswertung und getrennte, dokumentierte Margin-/Hebelszenarien halten Verlustverteilung und Liquidationsrisiko sichtbar. Das vorhandene Browserjournal verlangt positive Ein- und Ausstiegskurse (`dist/field.js:11`) und kann Nicht-Trade-Signale derzeit nicht erfassen; die Empfehlung setzt eine gesonderte Entscheidung/Umsetzung voraus.
- Der unabhängige Review 1.9 liegt vor; offen bleiben Validierung weiterer Regime/Indikator-/Profilhypothesen, historische Orderbuch-/Spread-/Fill-Daten sowie weiter reichende Point-in-time-Universen. Für Aktien-Perps fehlen insbesondere vollständige historische Abdeckung, Kalender- und Underlying-Abgleich sowie historische ausführbare Preise; die begrenzten 1m-Proben und 5m-/15m-Stichproben ersetzen diese Arbeit nicht. Die Forschungsberichte sind kein Nachweis profitabler Einstiege; die Eltern-Akzeptanzkriterien sind weiterhin nicht erfüllt. Issue #3 bleibt offen.
