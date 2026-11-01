# Intraday-Einstiege: Arbeitsstand zu Issue #3

**Status: offen, nicht entscheidungsreif.** Dieser Bericht dokumentiert eine Bestandsaufnahme und ein überprüfbares Forschungsdesign. Er belegt weder profitable Signale noch eine Trefferquote. Es wurden keine produktiven Dashboard-Regeln geändert und keine Orders ausgelöst. Die Akzeptanzkriterien von [Issue #3](https://github.com/totosan/tokendashboard/issues/3) sind nicht erfüllt.

## Was in dieser Sitzung tatsächlich geprüft wurde

- Der aktuelle Default-Branch und die Implementierungen, Hilfetexte und TradingView-Dateien wurden geprüft. Die drei eigenständigen Pine-Strategien aus Issue #1 sind vorhanden; ihre Regeln sind Backtest-Annahmen, keine Wirksamkeitsbelege.
- `node --check` bestand für alle acht `dist/*.js`-Dateien. Das Repository hat keine vorhandene Test-/Build-Konfiguration oder Backtest-Datensätze; zusätzlich wurden sechs neue Unit-Tests für den Forschungs-Backtest ausgeführt. Diese prüfen die Signalberechnung, nicht die Qualität realer Signale.
- Es wurden keine vorhandenen Artefakte zum in Issue #3 erwähnten Test mit acht Coins/45 Tagen gefunden. Der dort berichtete negative Befund ist nicht reproduziert und mangels Code, Auswahl, Daten und Kostenannahmen nicht unabhängig prüfbar.
- Die öffentlichen Bitget-APIs waren erreichbar. Für 12 ausgewählte USDT-Perpetuals wurden 5m- und 15m-Kerzen vom 2026-09-17 00:00 UTC bis 2026-11-01 00:00 UTC abgerufen: 12.960 vollständige 5m-Bars und 4.320 vollständige 15m-Bars je Symbol, keine fehlenden Bars in diesen Fenstern. Die Zeitrahmen wurden getrennt ausgewertet.
- Der TradFi-Bericht (#9) verglich die aktuellen öffentlichen Bitget-Instrumentenlisten: 307 online `stock`-RWA-USDT-Perpetuals in der geprüften Schnittmenge; davon 256 US-, 16 KR-, 11 JP-, 22 HK- und 2 CN-Region-Klassifikationen, 58 ohne ISIN. Das ist ein aktueller Snapshot, keine historische oder eindeutige Underlying-Zuordnung.
- Der TradFi-Bericht verifizierte begrenzte 1m-Kerzenproben für AAPLUSDT bis Juni 2026 sowie fünf jüngste Fundingereignisse, nicht aber lückenlose Archive. Er dokumentiert, dass der bestehende TradFi-Scanner ausschließlich Perp-Kerzen nutzt: long-only, Impuls/Pullback-/Dochttrigger, ohne zwingenden Schlusskurs über Trigger oder Mindestvolumen. Aktien-RVOL, Premarket, News/Float-Historie, historischer Spread und tatsächliche Ausführbarkeit sind nicht belegt; vollständige Details und Reproduktionsparameter stehen in [Issue #9](https://github.com/totosan/tokendashboard/issues/9).
- Der Profilbericht (#13) bestätigte, dass das Dashboard das sechste Candle-Feld als Volumen nutzt und es gleichmäßig über 24 Preis-Bins verteilt; die siebte Quote-Volumen-Spalte wird ignoriert. Live-Trade-Endpunkte waren erreichbar, aber Langzeithistorie, Retention und Einheiten wurden nicht geprüft; POC/Value-Area/RVOL-Vergleiche bleiben Hypothesen.
- Der Daten-/Risikobericht (#7) dokumentierte Bitgets öffentliche Candle-, Trade-, Funding-, Depth- und Fee-Endpunkte samt dokumentierten Limits. Kleine öffentliche GET-Stichproben waren erfolgreich; authentifizierte Kontogebühren, reale Fills, historische Tiefe und Latenz wurden nicht getestet. Die Kostenannahmen der Auswertung bleiben daher Szenarien, keine historischen Ausführungswerte.
- GitHub-Schreibzugriff ist verfügbar: Es wurden neun native Child-Issues und Topic-/State-Labels angelegt. Berichte für 1.1–1.8 liegen vor (#6 geschlossen; #14, #11, #13, #12, #10, #9 und #7 in Review). Der unabhängige Kritiker für 1.9 läuft; die Epic-Akzeptanzkriterien sind noch nicht erfüllt.
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

### Statusmatrix der Domänenberichte

| Paket | Bericht / belegter Umfang | Empirischer Status |
|---|---|---|
| 1.1 Bestand | Codepfade, lokale Grenzen und bestehende Dashboard-Hypothesen in #6 inventarisiert. | Inventar-Akzeptanzkriterium erfüllt; #6 geschlossen. |
| 1.2 Breakout | Regeldefinitionen/Quellen plus eigene Bitget 5m-/15m-Vorwärtsbewegungs-Auswertung in #14 und diesem Bericht. | Begrenzter OOS-Eventtest; keine Portfolio-, Ausführbarkeits- oder Robustheitsvalidierung. |
| 1.3 Volumen/Profile | #13 beschreibt das Basisvolumen-15m-Bin-Profil, fehlende VAH/VAL/RVOL sowie API-Stichproben und falsifizierbare OHLCV-/Trade-Profilvergleiche. | Keine Profil-/RVOL-Edge-Messung; historische Trade-Abdeckung und Einheiten offen. |
| 1.4 Regime/MTF | #12 prüft die Anzeigeimplementierung (1h EMA20/50 und Zonen); schlägt getrennte 1h-/4h-/Volatilitätsfilter-Tests vor. | Kein historischer Abruf, Backtest oder Statistiktest; Timestamp, 4h-Abdeckung und Kosten offen. |
| 1.5 Indikatoren | #11 liefert kausale Hypothesen und Baselines für Trend, VWAP, Tagesniveaus und Mean Reversion. | Keine empirische Indikatorvalidierung. |
| 1.6 Krypto-Universum | #10 dokumentiert Börsen-/Asset-Universen und einen vorab fixierbaren Vergleichsplan. | Kein Backtest; globale Point-in-time-Listings, Delistingvollständigkeit und Kostenregeln offen. |
| 1.7 TradFi | #9 dokumentiert 307 aktuelle Stock-RWA-Perpetuals, begrenzte 1m-/Funding-Proben, Scannerlogik und Underlying-Grenzen. | Kein vollständiger historischer/Underlying-Abgleich oder ausführbarer Aktienvergleich. |
| 1.8 Daten/Risiko | #7 dokumentiert öffentliche Bitget-Endpunkte/Limits, Kostenmethodik, Fee-/Funding-Abgrenzung und Hebelrisiken. | Keine persönlichen Gebühren, echten Fills, historischen Depth-Daten oder Latenzmessungen. |
| 1.9 Kritiker | Unabhängige Prüfung der Reports, Zahlen, Quellen, Methoden und Statuslage ist beauftragt. | Ergebnis ausstehend; erst danach finale Synthese/Statusprüfung. |

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

Dies ist eine begrenzte, deskriptive Vorwärtsbewegungs-Auswertung, kein Portfolio-Backtest und keine Wirksamkeits- oder Gewinnbestätigung. Der Lauf verwendet `research/intraday_eval.py`, sechs synthetische Unit-Tests, den gespeicherten Candle-Snapshot und den zugehörigen Ereignis-/Ergebnisexport unter `research/data/` und `research/results/`. Snapshot und Ergebnisdateien sind mit SHA-256 prüfbar; der Code kann dieselben Kennzahlen offline aus dem Snapshot erzeugen.

| Merkmal | Festlegung |
|---|---|
| Quelle/Zeitraum | Bitget `/api/v2/mix/market/history-candles`, USDT-FUTURES, `kLineType=market`; 2026-09-17 00:00 bis 2026-11-01 00:00 UTC. 12 derzeit gelistete Kontrakte, 8 Krypto (BTC/ETH plus SOL/BNB/XRP/DOGE/ADA/LINK) und 4 Aktien-Perpetuals (TSLA/NVDA/AAPL/COIN); 12.960/12.960 5m-Bars und 4.320/4.320 15m-Bars je Symbol, keine Lücken im angefragten Intervall. |
| Zeitaufteilung | Chronologisch: erste 30 Tage Entwicklung, letzte 15 Tage OOS ab 2026-10-17 00:00 UTC. Keine Parametersuche; ein vorab fixierter Treppen-Ausbruch mit Standard-Volumenfilter 1,0× und eine 3-Schlusskurs-Momentum-Baseline. |
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
| 3-Schlusskurs-Baseline | BTC/ETH | Short | 735 | 0,44 / -0,18 | 49,8 % | -11,56 |
| 3-Schlusskurs-Baseline | Altcoins | Long | 1.959 | -0,79 / -1,33 | 46,2 % | -12,79 |
| 3-Schlusskurs-Baseline | Altcoins | Short | 2.040 | 0,85 / -1,33 | 46,0 % | -11,15 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Long | 1.297 | 0,05 / -0,58 | 45,5 % | -11,95 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Short | 1.442 | 0,40 / -0,00 | 49,4 % | -11,60 |

OOS-Richtungsergebnisse der **5m-Auswertung**, gleiche Definitionen, Universe und Kostenannahmen:

| Ansatz | Gruppe | Richtung | N | Ø / Median brutto | Treffer brutto | Ø netto bei 12 bp |
|---|---|---:|---:|---:|---:|---:|
| Treppen-Ausbruch | BTC/ETH | Long | 22 | -3,61 / 0,68 | 54,5 % | -15,61 |
| Treppen-Ausbruch | BTC/ETH | Short | 26 | 1,88 / -0,00 | 50,0 % | -10,12 |
| Treppen-Ausbruch | Altcoins | Long | 71 | -2,29 / -1,30 | 42,3 % | -14,29 |
| Treppen-Ausbruch | Altcoins | Short | 85 | -0,87 / -0,49 | 43,5 % | -12,87 |
| Treppen-Ausbruch | Aktien-Perpetuals | Long | 35 | 1,17 / 0,00 | 40,0 % | -10,83 |
| Treppen-Ausbruch | Aktien-Perpetuals | Short | 62 | -3,43 / -0,89 | 41,9 % | -15,43 |
| 3-Schlusskurs-Baseline | BTC/ETH | Long | 2.045 | -0,14 / -0,38 | 48,0 % | -12,14 |
| 3-Schlusskurs-Baseline | BTC/ETH | Short | 2.093 | 0,06 / -0,49 | 46,9 % | -11,94 |
| 3-Schlusskurs-Baseline | Altcoins | Long | 5.710 | -0,29 / -0,86 | 45,2 % | -12,29 |
| 3-Schlusskurs-Baseline | Altcoins | Short | 5.959 | 0,41 / -0,00 | 47,0 % | -11,59 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Long | 3.569 | 0,04 / 0,00 | 45,9 % | -11,96 |
| 3-Schlusskurs-Baseline | Aktien-Perpetuals | Short | 3.787 | -0,09 / -0,00 | 46,4 % | -12,09 |

In beiden einzelnen 15-Tage-OOS-Fenstern liegt der mittlere Netto-Ereignisertrag jeder Tabellenzeile unter null bereits unter der günstigen 12-bp-Gebührenannahme. Die 15m-Treppen-Signale sind selten (N=7–27 pro Gruppe/Richtung); die 5m-Stichprobe ist größer, bleibt aber eine kurze, gezielt ausgewählte Stichprobe. Selbst die häufigere Baseline erzeugt korrelierte und teils überlappende Ereignisse. Es gibt keine Konfidenzintervalle, Korrektur für Mehrfachtests oder Point-in-time-Symbolhistorie. Die 4 TradFi-Symbole bleiben Futures-Perpetuals, keine Aktienkurs-/Aktienvolumentests. Keine Schlussfolgerung über andere Zeiträume oder Symbole ist daraus zulässig.

Für Offline-Wiederholung: `python3 -m unittest research.test_intraday_eval -v`. Bei gespeicherten Snapshots muss `--granularity` explizit gesetzt werden; Event-Exporte können komprimiert als `.csv.gz` geschrieben werden. Die Ergebnis-JSONs enthalten außerdem den SHA-256-Hash des ausgewerteten Snapshots:

```sh
python3 -m unittest research.test_intraday_eval -v
python3 research/intraday_eval.py --granularity 5m --input research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz --summary research/results/bitget-5m-2026-09-17_2026-11-01.json --events research/results/bitget-5m-2026-09-17_2026-11-01-events.csv.gz
python3 research/intraday_eval.py --granularity 15m --input research/data/bitget-15m-2026-09-17_2026-11-01.csv.gz --summary research/results/bitget-15m-2026-09-17_2026-11-01.json --events research/results/bitget-15m-2026-09-17_2026-11-01-events.csv.gz
```

## Externe Evidenz und Datenstatus

### Bitget – direkt beobachtete öffentliche API-Antworten

- Der direkte Aufruf von [`/api/v2/mix/market/history-candles`](https://api.bitget.com/api/v2/mix/market/history-candles?symbol=BTCUSDT&productType=USDT-FUTURES&granularity=15m&limit=200) lieferte `code=00000`. Die Antwortzeilen enthalten Zeitstempel, OHLC und zwei Volumenfelder; die lokal genutzte `dist/orderbook.js`-Implementierung verwendet das sechste Datenfeld (API-Antwortindex 5) als Volumen-Näherung, während die Ausbruchsauswertung das siebte Feld (Index 6, Quotevolumen in der beobachteten Antwort) verwendet. Abdeckung und Volumensemantik sind im Snapshot dieser Stichprobe dokumentiert, aber nicht mit historischen Trades abgeglichen.
- Die eingefrorenen 5m- und 15m-Datensätze enthalten 155.520 beziehungsweise 51.840 Bars über dieselben 12 Symbole. Reproduzierbare Rohdaten-Exporte: [`5m CSV.GZ`](research/data/bitget-5m-2026-09-17_2026-11-01.csv.gz) und [`15m CSV.GZ`](research/data/bitget-15m-2026-09-17_2026-11-01.csv.gz); Kennzahlen und Ereignisse stehen im `research/results/`-Verzeichnis. Die Resultate beziehen sich nur auf diese gezielt ausgewählte Stichprobe.
- Der öffentliche [`/api/v3/market/instruments?category=USDT-FUTURES`](https://api.bitget.com/api/v3/market/instruments?category=USDT-FUTURES)-Abruf meldete für ausgewählte Kontrakte `status=online`, `type=perpetual`; die vier Aktien-Perpetuals wurden als `instrumentType=stock`, `isRwa=YES` klassifiziert. Der gespeicherte Snapshot vom 2026-11-01 15:07:38.919 UTC enthält die 12 tatsächlich verwendeten Symbole und Felder: [`bitget-instruments-2026-11-01.json`](research/data/bitget-instruments-2026-11-01.json).
- Dieser Snapshot zeigt für die ausgewählten 12 Instrumente `makerFeeRate=0.0002`, `takerFeeRate=0.0006`, `fundInterval=8`. Das sind zeitpunktbezogene Produktmetadaten, keine bestätigten individuellen Kontogebühren oder historischen Sätze. Die Auswertung nutzt ausschließlich den 6-bp-Taker-Satz als klare Kostenannahme; historische Funding-Zahlungen, Gebührenänderungen, Spread, Slippage und Orderausführung wurden nicht rekonstruiert.
- Ein Live-Instrumentenabruf ist kein Nachweis der früheren Listungsdauer. Historische Trades, Quotes und Orderbuchtiefe sowie deren reproduzierbare Zeitabdeckung sind weiterhin offen; das aktuelle Dashboard-Orderbuch ist keine historische Ausführungssimulation. Dynamisch gerenderte Bitget-Dokumentationsseiten wurden nicht als Beleg für ungeprüfte Limits oder Datenhistorie verwendet.

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

**Stand 2026-11-01:** Issue [#3](https://github.com/totosan/tokendashboard/issues/3) ist offen, mit `topic:research` und `state:in-progress`. Die folgenden nativen GitHub-Child-Issues wurden mit direktem Parent #3 erstellt:

| Nummer | Arbeitspaket / direktes Child-Issue | Topic / tatsächlicher Status |
|---|---|---|
| 1.1 | [#6 Bestandsaufnahme](https://github.com/totosan/tokendashboard/issues/6) | `topic:inventory` · `state:done` · Bericht mit Codezeilen/Abgrenzung eingereicht; geschlossen |
| 1.2 | [#14 Breakout, Konsolidierung und Pullback](https://github.com/totosan/tokendashboard/issues/14) | `topic:breakout` · `state:review` · formale Definitionen/Quellen eingereicht; eigene 5m/15m-Treppen-Auswertung ergänzt; echte Box-/Retestvarianten bleiben offen |
| 1.3 | [#13 Volumen und Profile](https://github.com/totosan/tokendashboard/issues/13) | `topic:volume-profile` · `state:review` · aktuelle Approximation, API-Stichproben und falsifizierbare OHLCV-vs-Trade-Profiltests dokumentiert; keine Edge-Messung |
| 1.4 | [#12 Marktregime und MTF](https://github.com/totosan/tokendashboard/issues/12) | `topic:regime-mtf` · `state:review` · Code-Audit und präregistrierbare 1h-/4h-/Volatilitätstests; kein Backtest |
| 1.5 | [#11 Trend, VWAP und Mean Reversion](https://github.com/totosan/tokendashboard/issues/11) | `topic:indicators` · `state:review` · testbare Regeln, Grenzen und Quellen eingereicht; empirisch ungetestet |
| 1.6 | [#10 Krypto-Universum](https://github.com/totosan/tokendashboard/issues/10) | `topic:crypto-universe` · `state:review` · PIT-/Survivorship-Vergleich und Datenanforderungen dokumentiert; kein Backtest |
| 1.7 | [#9 TradFi-Übertragbarkeit](https://github.com/totosan/tokendashboard/issues/9) | `topic:tradfi` · `state:review` · aktuelles 307er-Universum, begrenzte 1m-/Funding-Proben und Scannersemantik dokumentiert; vollständige historische Validierung offen |
| 1.8 | [#7 Daten, Ausführung und Risiko](https://github.com/totosan/tokendashboard/issues/7) | `topic:execution-risk` · `state:review` · Bitget-Endpunkte/Limits, Kostenmodell und Hebelrisiken dokumentiert; historische Fills, Tiefe, Gebühren und Latenz offen |
| 1.9 | [#8 Validierung, Synthese und unabhängiger Review](https://github.com/totosan/tokendashboard/issues/8) | `topic:validation` · Review läuft · unabhängiger Kritiker nach Eingang der Berichte 1.1–1.8 beauftragt |

Je eines der acht verfügbaren Hintergrund-Rechercheaufträge ist den Issues 1.1–1.8 zugeordnet. 1.1 lieferte einen Bericht mit Codezeilen, tatsächlich verwendeten Daten und expliziten Nicht-Prüfungen; sein eigenes Inventar-Akzeptanzkriterium ist erfüllt, deshalb wurde #6 geschlossen und auf `state:done` gesetzt. 1.2 lieferte operationale Hypothesen und Quellen; die spätere 5m/15m-Auswertung wurde ergänzt und #14 auf `state:review` gesetzt. 1.3 dokumentierte die bestehende Approximation und falsifizierbare Daten-/Profiltests, ohne Performanceaussage; #13 ist auf `state:review`. 1.4 dokumentierte den MTF-Anzeigekontext und ein kausales Testdesign ohne historischen Lauf; #12 ist auf `state:review`. 1.5 lieferte testbare Regelentwürfe, Baselines, Kostenfragen und eng eingeordnete Literatur; #11 ist auf `state:review`, die Ansätze sind empirisch ungetestet. 1.6 dokumentierte Quellen-/Biasgrenzen für ein PIT-Universum und einen reproduzierbaren Vergleichsplan, ohne Backtest; #10 ist auf `state:review`. 1.7 dokumentierte aktuelle Instrumentklassifikation, begrenzte historische Proben und die Long-only-Perp-Scannersemantik; #9 ist auf `state:review`, während Underlying-Abgleich und vollständige Historienprüfung offen bleiben. 1.8 dokumentierte öffentliche Endpunkte/Limits sowie Kosten- und Hebelrisiken, aber keine persönlichen Gebühren, Ausführungen oder historischen Tiefendaten; #7 ist auf `state:review`. Alle acht Fachberichte sind eingegangen; der unabhängige Kritiker für 1.9 ist beauftragt. Bislang wurde kein Agent als ausgefallen dokumentiert; `Lost Repeat` ist daher weder erstellt noch gesetzt.

**Tatsächlich erstellte Labels:** Topics `topic:research`, `topic:inventory`, `topic:breakout`, `topic:volume-profile`, `topic:regime-mtf`, `topic:indicators`, `topic:crypto-universe`, `topic:tradfi`, `topic:execution-risk`, `topic:validation`; States `state:pending`, `state:in-progress`, `state:blocked`, `state:review`, `state:done`. Die Konvention ist ein `topic:*`-Label für den Arbeitsbereich plus genau ein `state:*`-Label für den aktuellen Status. Statusangaben hier sind der zuletzt verifizierte GitHub-Snapshot, keine Erfolgsaussage.

## Vorläufige Synthese und offene Schritte

- Keine Produktivänderung und keine Erfolgsbehauptung aus dieser Recherche ableiten.
- Als erste Untersuchung vorhandene Long-/Short-Signale gegen eine einfache, vorher festgelegte Momentum-Baseline testen; eine separate enge Konsolidierung als eigene Hypothese behandeln.
- Profile, MTF-Filter und Indikatoren jeweils nur auf inkrementellen Out-of-sample-Mehrwert prüfen; keine kumulierte Auswahl „bester“ Filter ohne Offenlegung aller Varianten.
- Crypto-Perpetuals und Stock-Perpetuals getrennt behandeln. Kosten, Funding, Datenlücken und tatsächlich erreichbare Preise pro Instrument nachweisen.
- Dashboard-Empfehlung (nicht implementiert): Treffer/Beobachtung von Bestätigung trennen; UTC-Signal- und Scanzeit, geschlossene Zeitrahmen, Datenalter/-abdeckung, verwendete Regel/Version, Trigger-/Strukturlevel sowie beobachteten Spread/Funding-Snapshot kenntlich machen. Das bleibt Beschreibung/Protokoll, keine Prognose.
- Manueller Feldtest (nicht durchgeführt): jedes qualifizierende Signal protokollieren – auch abgelehnte, verpasste und nicht gehandelte Setups samt Grund –, nicht nur tatsächlich ausgeführte Trades. Vorab Setup, Regelversion, Signalzeit und Entscheidung dokumentieren; danach bei Trades tatsächliche Ausführungszeit/-preise, Gebühren, Funding, Verzögerung und Ergebnis ergänzen. Ungehebelte Auswertung und getrennte, dokumentierte Margin-/Hebelszenarien halten Verlustverteilung und Liquidationsrisiko sichtbar. Das vorhandene Browserjournal verlangt positive Ein- und Ausstiegskurse (`dist/field.js:11`) und kann Nicht-Trade-Signale derzeit nicht erfassen; die Empfehlung setzt eine gesonderte Entscheidung/Umsetzung voraus.
- Offen bleiben der unabhängige Review 1.9, Validierung weiterer Regime/Indikator-/Profilhypothesen, historische Orderbuch-/Spread-/Fill-Daten sowie weiter reichende Point-in-time-Universen. Für Aktien-Perps fehlen insbesondere vollständige historische Abdeckung, Kalender- und Underlying-Abgleich sowie historische ausführbare Preise; die begrenzten 1m-Proben und 5m-/15m-Stichproben ersetzen diese Arbeit nicht. Die Forschungsberichte sind kein Nachweis profitabler Einstiege; die Eltern-Akzeptanzkriterien sind weiterhin nicht erfüllt. Issue #3 bleibt offen.
