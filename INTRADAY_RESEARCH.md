# Intraday-Einstiege: Bestandsaufnahme und Evaluationsplan

**Status: vorläufig, nicht entscheidungsreif.** Dieses Dokument ist eine Recherche- und Statusnotiz zu Issue [#3](https://github.com/totosan/tokendashboard/issues/3), kein Nachweis profitabler Signale und keine Empfehlung zum Handel. Es wurden keine produktiven Dashboard-Regeln geändert und keine Orders ausgelöst. Issue #3 bleibt offen; die Akzeptanzkriterien sind nicht erfüllt.

## Umfang, Stand und Grenzen

- Referenz ist `main` bei `42b4eb0594589e486452589610d102d959b9acd8`. Die für diese Bestandsaufnahme maßgeblichen Dateien stimmen mit dem Arbeitszweig überein.
- Das Repository enthält statische Dashboard-Dateien, aber keine Tests, Backtest-Daten, Test-/Build-Konfiguration oder Abhängigkeitsmanifestdatei. `node --check` besteht für die vorhandenen JavaScript-Dateien; das prüft Syntax, nicht die Marktdaten oder Signalqualität.
- Im Repository wurden keine Artefakte des in Issue #3 erwähnten Tests mit acht Coins und 45 Tagen gefunden. Diese negative Beobachtung ist keine Reproduktion: Testdaten, Code, Kosten und Ergebnisse sind hier nicht unabhängig überprüfbar.
- Bitget-Dokumentation und API-Aufrufe konnten in dieser Sitzung nicht verlässlich abgerufen werden; Web- und GitHub-Inhaltsanfragen liefen in Timeouts oder DNS-Fehler. Wo Angaben nicht aus dem lokalen Quellcode hervorgehen, stehen sie deshalb ausdrücklich als **unverifiziert/offen**. Die Links unter „Quellen zur Nachprüfung“ sind Prüfziele, keine hier bestätigten API-Spezifikationen.
- Wegen fehlender dauerhafter historischer Kurs-, Trade-, Orderbuch-, Spread-, Gebühren- und Funding-Daten wurde kein reproduzierbarer Backtest und keine Performance-Messung durchgeführt. Es werden daher keine Trefferquoten, Profitabilität oder Signifikanz behauptet.

## Bestand des Dashboards

| Bereich | Tatsächliche Regel/Daten | Aussage und wesentliche Grenze |
|---|---|---|
| Treppenprofil | `dist/breakout.js:3-20` verarbeitet drei gerichtete Kerzen, eine Gegenkerze und optional eine bestätigende Kerze. Rücklauf: 5–50 %; Bestätigung: Schluss jenseits der Gegenkerze und Volumenfaktor. | Mustererkennung, keine Wahrscheinlichkeit. Der Ablauf misst keinen eigenständigen vorausgehenden Seitwärtszustand. |
| Gegenkerzen-/Impulsprofil | `dist/pattern.js:6-24` sucht 2–6 Impulskerzen, 2–4 Gegenkerzen, mindestens zehn vorherige Kerzen als Volumen-/Hoch-Basis und einen Ausbruch über deren Hoch (Short analog). Unterstützt 1m und 5m, abgeschlossene Kerzen und Long/Short. | Der Bruch eines vorangegangenen Hochs ist kein Nachweis einer engen Konsolidierung. Es gibt keine eigene Seitwärtsdefinition über Rangebreite, Volatilität oder Dauer. Parameter sind Heuristiken. |
| TradFi-/Coin-Pullback | `dist/tradfi.js:3-13` erkennt einen Long-Impuls auf abgeschlossenen 1m-Kerzen, 1–3 fallende Gegenkerzen und optional ein neues Hoch. | Nur Long und 1m; keine Aktiennachrichten, Aktien-Relativvolumina, Float- oder Premarket-Daten. Der README-Text beschreibt es als Annäherung, nicht als validierte Aktienstrategie (`README.md:49-55`). |
| Momentum-Ranking | `dist/app.js:19,24-25,56-59` sortiert abgeschlossene 1m-Kerzen nach 1/5/15m-Rendite. Das Universum wird anhand aktueller 24h-Quotevolumina gewählt; Standard ist Top 100 mit mindestens 10 Mio. USDT. | Momentaufnahme und Rangliste, keine Einstiegsevaluation. Die heutige Auswahl ist keine historische, über die Zeit konstante Coin-Stichprobe. |
| API- und Scanfenster | `dist/app.js:56-59` lädt pro Kontrakt bis zu 185 jüngste 1m-Kerzen (für den Scan werden maximal 180 Minuten verwendet), scannt fortlaufend bei geöffnetem Dashboard und markiert unvollständige Scans. Der Ticker-/Kontraktabruf erfolgt am Scanstart. | Kurzes Live-Fenster, nicht die für Entwicklungs-/Out-of-sample-Tests erforderliche Historie. Scan- und manuelle Einstiegsverzögerung sowie erreichbarer Ausführungskurs sind nicht historisch gespeichert. |
| Marktüberblick | `dist/context.js:6-13` verwendet abgeschlossene 1h-Kerzen für EMA 20/50 sowie Vortages- und 24h-Hoch/Tief aus 1h-/15m-Kerzen. | Kontextansicht, kein 4h-Kontext und kein Ein-/Ausschlussfilter des Scanners. Keine Aussage über die spätere Bewegung. |
| Volumenprofil | `dist/orderbook.js:25` übernimmt das sechste Feld der Candle-Antwort; `:12,18-22` verteilt diesen Wert aus abgeschlossenen 15m-Kerzen anteilig über deren gesamte Preisspanne in 24 Zonen (4/12/24 Stunden). Die maximale Zone ist als POC markiert. Das README bezeichnet die Menge als Basisvolumen. | Näherung aus OHLCV; Preisverteilung innerhalb der Kerze und die API-Semantik des Felds sind nicht verifiziert. Value Area (VAH/VAL) wird nicht berechnet. README sagt ausdrücklich, dass ein Filter-Nutzen nicht nachgewiesen ist (`README.md:63-65`). |
| Orderbuch | `dist/orderbook.js:26-30` lädt einen aktuellen Snapshot und sammelt bei geöffneter Ansicht etwa alle fünf Sekunden bis zu 15 Minuten flüchtige Snapshots. | Kein historisches Orderbuch. Die Kaufwirkung ist eine Momentaufnahme für 1.200 USDT und schließt Spread und Gebühren aus (`README.md:57-61`). |
| Kosten und Protokoll | Ticker-Spread, Funding und Open Interest sind Snapshots (`dist/app.js:25`); das lokale Feldprotokoll berechnet aus manuell eingegebenen Kursen/Positionswerten und Gebühren (`dist/field.js:8-14`). | Keine historische Kostenreihe und kein automatischer Kostenabzug im Scanner. Das Feldprotokoll berücksichtigt Funding nicht; Slippage nur, soweit sie in den eingegebenen Kursen steckt (`README.md:53-55`). Hebel liefert keinen statistischen Vorteil und vergrößert Verluste/Margin-Risiko. |

### Bezug zu Issue #1

Issue [#1](https://github.com/totosan/tokendashboard/issues/1) behandelt separat kopierbare TradingView-Strategie-Skripte zu ähnlichen Mustern. In diesem Repository liegen keine Pine-Skripte oder TradingView-Backtest-Ergebnisse. Daher werden dort genannte Entry-/Exit- und Parameterannahmen nicht als gemessene Evidenz für den Dashboard-Scanner übernommen; Abweichungen sind anhand der aktuellen `main`-Implementierung oben zu beurteilen. Ein späterer Pine-Backtest kann eine weitere unabhängige Implementierung liefern, ersetzt aber weder Bitget-spezifische Daten-/Ausführungstests noch die hier geforderte Cross-Symbol-Validierung.

### Was echte Konsolidierung für einen Test bedeuten müsste

Eine testbare Konsolidierungsdefinition muss ausschließlich vergangene, am Signalzeitpunkt verfügbare Daten benutzen und vor dem Test festgelegt werden. Beispielsweise könnten Dauer, Rangebreite relativ zur vorherigen ATR/Volatilität und Überlappung der Kerzen gemeinsam eine Zone definieren; ein Ausbruch wäre ein abgeschlossener Schluss außerhalb der Zone mit vorab festgelegtem Volumenvergleich. Ein Retest muss zeitlich begrenzt, räumlich definiert und vom späteren Fortsetzungstrigger getrennt sein. Diese Varianten sind **Hypothesen für Tests**, keine vorgeschlagenen produktiven Regeln. Fehl- und Spätausbrüche gehören in die Ergebnismessung, nicht in eine nachträgliche Auswahllogik.

## Vergleich der Ansätze und vorläufige Priorität

| Ansatz | Was er hier messen könnte | Typisches Scheitern / offene Prüfung | Status |
|---|---|---|---|
| Bestehender Ausbruch bzw. Impuls-Rücksetzer | Richtungskonditionierte Forward-Renditen und MFE/MAE nach einem abgeschlossenen Trigger; separat für Long/Short. | Fehl-/Spätausbruch, sprunghafte Rückkehr in die Zone, Scanlatenz und Kosten. Der Bestand enthält keine explizite enge Seitwärtsphase. | **Erste Testhypothese**, noch nicht getestet. Gegen bestehende Scanner und eine einfache Momentum-Baseline vergleichen. |
| POC/Value Area/Volumenprofile | Inkrementeller Nutzen gegenüber derselben Baseline; erst Kerzenapproximation, dann Trade-Level nur falls historische Einzeltrades verfügbar und überprüft sind. | Candle-Volumenverteilung ist unbekannt; POC/Value Area können von Bin-Größe, Fenster und Markt abhängen. | POC-Näherung vorhanden; VAH/VAL und Mehrwert ungeprüft. Nicht als Filter einsetzen, bevor ein Out-of-sample-Mehrwert gemessen ist. |
| 1h-/4h-Regime | Prüfen, ob ein vorab festgelegtes Regime 5m-/15m-Ergebnisse nach Kosten verbessert, ohne die Abdeckung unangemessen zu reduzieren. | Lookahead durch unvollständige Balken, Parameterwahl nach Ergebnis, Regimewechsel. | 1h-Kontext wird angezeigt, 4h fehlt; kein MTF-Filter und kein Test. |
| EMA/Trend, Tagesniveaus, Support/Resistance | Je Feature denselben Signalbestand mit/ohne Filter vergleichen. | Seitwärtsmärkte, schnell wechselnde Regime, subjektive/überlappende Niveaudefinitionen. | 1h-EMA und Tages-/24h-Niveaus sind Kontext, nicht validierte Signale. |
| VWAP, Bollinger, RSI/Mean Reversion | Als getrennte, präregistrierte Trendfolge-/Reversionshypothesen in klar definierten Regimen testen. | Trendfortsetzung kann Reversionseinstiege überrollen; starke Ausbrüche können Mean-Reversion-Signale lange verschlechtern. | Im Dashboard nicht implementiert; Daten- und Wirksamkeitstest offen. Nicht durch Indikatornamen begründen. |
| Breites Coin-Universum vs. BTC/ETH/Altcoin- oder Eigenschaften-Gruppen | Gleiche Signalregeln und Kosten nach BTC/ETH, Altcoins und Liquiditätsgruppen getrennt sowie gepoolt vergleichen. | Aktuelles Volumen-Ranking erzeugt Auswahl-/Survivorship-Verzerrung; korrelierte Coin-Signale und wiederholte Varianten machen Unsicherheit größer. | Kein historisch point-in-time korrektes Universum und kein separater Test im Repository. |
| TradFi-Aktien-Perpetuals | Nur separat, pro Instrument und Zeitsegment; Futures-Perpetualpreis und -volumen getrennt von zugrunde liegender Aktie behandeln. | Referenzpreis, Handelszeiten, Funding, Datenverfügbarkeit und Verhalten außerhalb der Aktienhandelssitzung sind nicht verifiziert. | Vorhanden ist nur die Long-1m-Futures-Heuristik. Aktuelle Instrumente, Aktienvolumen, Float, Premarket und Nachrichten sind hier nicht bestätigt. |

Die frühere Stichprobe aus Issue #3 (acht Coins, 45 Tage, 15m-Folgekerzen-Exit, nach Kosten durchschnittlich negativ; einfache Seitwärtsfilter verbesserten sie nicht) ist ein **vom Issue berichteter, hier nicht reproduzierter Befund**. Er ist weder ein allgemeiner Gegenbeweis für jede Variante noch ein Beleg für eine andere Variante.

## Mindestprotokoll für eine reproduzierbare Untersuchung

1. **Vorab fixieren:** Signaldefinition, Long/Short, Zeitzone, nur abgeschlossene Bars, Coin-/TradFi-Universum mit point-in-time Mitgliedschaft, Regime, 5m/15m Einstieg und 1h/4h Kontext, Parameter und alle getesteten Varianten.
2. **Signalzeitpunkt realistisch setzen:** Der Scanner erkennt erst nach Kerzenschluss und einem periodischen Scan. Nicht automatisch zum Schlusskurs dieser Kerze ausführen; Einstieg frühestens zum nächsten plausiblen Quote/Trade nach Scan- und manueller Verzögerung modellieren.
3. **Einstiegsqualität getrennt von Handelsregeln messen:** vorab gewählte Forward-Renditen über mehrere Horizonte, günstige/ungünstige maximale Bewegung (MFE/MAE), Zeit bis zu Schwellen sowie Abdeckung. Für einen vollständigen Handel Exit, Stop, Ziel und Haltedauer ausdrücklich als Testannahmen ausweisen.
4. **Kosten parametrisieren:** maker/taker Gebühren nach Instrument/Konto, Spread, Slippage/Markteinfluss, Funding über die tatsächliche Haltezeit und Signal-/Ausführungsverzögerung. Mit ausführbaren Preisen statt Kerzenschluss rechnen. Sensitivität und Break-even-Kosten zeigen; die für ein Produkt geltenden Werte müssen aus datierten Primärquellen/API-Antworten stammen. Gaps und Kerzen, in denen Stop und Ziel zugleich berührt werden, konservativ und dokumentiert behandeln.
5. **Vergleiche fair halten:** auf denselben Signalzeitpunkten Baseline gegen je einen Zusatzfilter testen; keine Auswahl nur der besten Coins/Zeiten. Ergebnisse getrennt für BTC/ETH, Altcoins, Liquiditätsgruppen und TradFi ausweisen. Überlappende Trades und zeitgleiche Coin-Korrelation berücksichtigen.
6. **Zeitlich prüfen:** chronologische Entwicklungs-, Validierungs- und unberührte Out-of-sample-Abschnitte oder Walk-forward-Fenster; Parameterwahl und Zahl aller Versuche protokollieren. Missing Data, Delistings, Auswahlbias und Lookahead offenlegen.
7. **Verteilen statt nur mitteln:** Stichprobengröße/Abdeckung, brutto und netto, Mittelwert/Median, Trefferquote, durchschnittlicher Gewinn und Verlust, Profitfaktor, Drawdown, Unsicherheit und Ergebnisspanne berichten, soweit die Methode sie trägt. Trefferquote allein oder ein einzelner guter Coin/Zeitraum reicht nicht.
8. **Reproduzierbar veröffentlichen:** Quell- und Abrufzeit, Symbolbestand, Kerzen-/Signal-/Ausführungszeitstempel in UTC, rohe Daten- oder Abrufparameter, fehlende Werte, Kostenparameter, Codeversion, Exit-Annahmen und alle Varianten als Ereignisexport/Artefakte festhalten.

**Ausdrücklich nicht als Erfolgskriterium übernehmen:** 55 % Trefferquote. Sie sagt ohne durchschnittliches Gewinn-/Verlustverhältnis, Kosten und Unsicherheit nichts über Nettoerwartung oder Drawdown aus.

## Vorläufige Synthese und Empfehlungen

1. **Keine Regel als wirksam einstufen und keine produktive Filter-/Automationsänderung ableiten**, bis die Daten- und Out-of-sample-Lücken geschlossen sind. Die vorhandenen Treffer sind beschreibende Setups.
2. **Als erste überprüfbare Hypothese** die vorhandenen Long-/Short-Ausbruch- und Impuls-Rücksetzer-Signale nach einem fixierten, geschlossenen 5m-/15m-Trigger vergleichen. Eine echte Konsolidierung separat definieren und gegen dieselben Baselines testen; ihr Nutzen ist unbewiesen.
3. **Erst messen, dann ergänzen:** 1h/4h-Regime, Profil-/Relativvolumen und weitere Indikatoren jeweils einzeln auf inkrementellen Out-of-sample-Nutzen prüfen. Das aktuelle Kerzenprofil bleibt bis dahin Kontext, kein Handelsfilter.
4. **Dashboard verständlich halten:** Kandidaten weiterhin von Bestätigungen unterscheiden; bei einem Test mindestens Signalzeit in UTC, verwendete geschlossene Kerzen, Preisniveau, Datenabdeckung/Alter und Spread-Snapshot sichtbar protokollieren. Keine Trefferzahl als Trefferwahrscheinlichkeit oder Prognose darstellen.
5. **Manuelle Feldtests nur als Beobachtung protokollieren:** vor dem möglichen Einstieg Setup/Regeln und Signalzeit festhalten, tatsächliche Ein-/Ausstiegskurse, Gebühren, Finanzierung und Verzögerung nachtragen und das Ergebnis separat nach Symbolgruppe/Regime auswerten. Vorhandenes lokales Protokoll ist kein Backtest und seine Einträge belegen keine künftige Erfolgsquote.

Diese Punkte sind Forschungs- und Dokumentationsempfehlungen, keine Handelsanweisungen. Es wird keine Hebel- oder Positionsgrößenempfehlung abgeleitet; eine Trefferquoten- oder Gewinnzusage gibt es nicht.

## Orchestrierung, Labels und Agenten

### Vorgeschlagene Struktur (alle direkten Eltern wären Issue #3)

Die Nummerierung ist eine **Vorschlagsstruktur für GitHub-Sub-Issues**. Keines dieser Child-Issues wurde erstellt oder zugewiesen; `has_children=false` wurde bei der verfügbaren Issue-Abfrage gemeldet.

| Nummer | Vorgeschlagenes Thema | Abhängigkeit / messbares Lieferobjekt | Intern beauftragte Recherche |
|---|---|---|---|
| 1 | Bestand und Dashboard-Daten | Scannerregeln, Code-/Datenquellen, Einschränkungen und Wiederverwendung mit Zeilenreferenzen. | `dashboard-audit` – abgeschlossen, lokaler Code-Audit. |
| 2 | Breakout, Konsolidierung und Pullback | Operationalisierte Zone/Trigger/Retest-Varianten und Vergleich zum bestehenden Scanner; Testdaten/Code sofern verfügbar. | `breakout-pullback` – Recherche aktiv; kein Backtest. |
| 3 | Volumen/Volumenprofil | Candle-Näherung gegen Trade-Daten, POC/VAH/VAL und Relativvolumen; Datenverfügbarkeit nachweisen. | `volume-profile` – abgeschlossen, Code-Audit; offizielle Datensemantik und alternative Historie unverifiziert. |
| 4 | MTF und Marktregime | Kausale 1h/4h-Kontextdefinitionen und inkrementeller 5m/15m-Vergleich. | `timeframe-regimes` – abgeschlossen, Methodikvorschlag, keine Quellenprüfung oder Messung. |
| 5 | Zusätzliche Signal-Familien | Präregistrierte EMA/Niveaus/VWAP/Mean-Reversion-Hypothesen samt Ausfallbedingungen. | `alternative-approaches` – abgeschlossen, Hypothesen und Ausfallbedingungen; Quellenzugriff blockiert. |
| 6 | Krypto-Universum | Gleiche Methodik für BTC/ETH, Altcoins, breite und Eigenschaftsgruppen; Bias- und Kostenbericht. | `crypto-universe` – Recherche noch aktiv; kein Ergebnis zum Zeitpunkt dieses Berichts. |
| 7 | TradFi-Übertragbarkeit | Aktuelle Instrumente/Produktspezifikationen und getrennte, quellengestützte Untersuchung. | `tradfi-transfer` – abgeschlossen, Verfügbarkeit/Marktdetails bleiben unverifiziert. |
| 8 | Daten, Ausführung und Risiko | Historien-/Zeitstempel-/Gebühren-/Funding-/Spread-/Slippage-Abdeckung je Instrument belegen. | `bitget-data` – abgeschlossen; API-Historienlimits, Zeitstempel und konkrete aktuelle Kosten unverifiziert. |
| 9 | Validierung, Synthese und Review | Reproduzierbare Ergebnisse, Vergleichsmatrix, Unsicherheit und unabhängige Kritik aller Teilergebnisse. | `methodology-review` – abgeschlossen, Testmethodik; unabhängiger Schlusskritiker erst nach Abschluss der laufenden Recherche. |

Die Agenten liefen als interne Rechercheaufgaben, nicht als GitHub Issue-Assignees. Keine GitHub-Issue-Erstellung, Zuweisung, Label-Erstellung, Kommentar- oder Statuspflege ist über die verfügbaren Schreibwerkzeuge möglich. Es wurden keine fehlgeschlagenen Agenten, Status-Wiederholungen oder `Lost Repeat`-Labels dokumentiert; Nichterreichbarkeit eines Issue-Endpunkts ist kein Agentenausfall.

### Label-Konvention

Vorgeschlagene Topic-Labels: `topic:baseline`, `topic:breakout`, `topic:volume-profile`, `topic:timeframe`, `topic:indicators`, `topic:crypto-universe`, `topic:tradfi`, `topic:data-costs`, `topic:validation`.

Vorgeschlagene Statuslabels: `state:pending`, `state:in-progress`, `state:blocked`, `state:review`, `state:done`. `Lost Repeat` wäre ausschließlich nach den im Issue beschriebenen wiederholten Nichtantworten anzuwenden.

Die abgefragten Repository-Labels sind die GitHub-Standardlabels (`bug`, `enhancement`, `documentation`, `question`, `help wanted`, etc.); keines der vorgeschlagenen Topic-/State-Labels oder `Lost Repeat` war vorhanden. Mangels Label-Schreibzugriff wurde keines erstellt oder gesetzt. Die oben dokumentierten Zustände sind Berichtstext und keine GitHub-Labelzustände.

## Quellenlage

### Im Repository tatsächlich überprüfte Primärdaten

- Implementierung und Hilfetexte auf dem Default-Branch: `dist/breakout.js`, `dist/pattern.js`, `dist/tradfi.js`, `dist/app.js`, `dist/orderbook.js`, `dist/context.js`, `dist/field.js`, `dist/index.html`, `README.md` (Details und Zeilen oben).
- Issue #3 und die vorhandenen Labels konnten über Issue-/Label-Abfragen eingesehen werden. Die GitHub-Inhaltsabfragen für den Default-Branch liefen später in Timeouts; der lokale `main`-Stand wurde daher per Fetch geladen und mit den genannten Dateien verglichen.

### Quellen zur Nachprüfung, hier nicht vollständig abrufbar

- [Bitget API-Dokumentationskatalog](https://www.bitget.com/docs/classic/catalog) und [Market-Data-Katalog](https://www.bitget.com/docs/catalog/market/market-data) – vom Recherche-Agenten als offizielle Einstiegspunkte identifiziert. Die Endpunktdetails, Historienfenster, Pagination, Zeitstempel, Rate Limits, Instrumentabdeckung und die Semantik des von `dist/orderbook.js:25` übernommenen Candle-Volumenfelds konnten hier nicht geprüft werden.
- Bitget Produktseiten: [Stock Perps – Complete Guide](https://www.bitget.com/support/articles/12560603847519), [Quick Guide](https://www.bitget.com/support/articles/12560603835927), [FAQ](https://www.bitget.com/support/articles/12560603847596), [Trading Fees FAQ](https://www.bitget.com/support/articles/12560603892734), [Funding Rate explainer](https://www.bitget.com/support/articles/12560603817108). Sie wurden in Suchergebnissen als relevante Primärquellen gefunden, aber nicht geladen. Produktmarketing oder Suchausschnitte gelten hier nicht als bestätigte Vertrags-/Gebührendaten.
- Methodische Fachliteratur, zur eigenständigen Prüfung und nicht als Beleg dieser Dashboard-Regeln: Lo, Mamaysky & Wang, “Foundations of Technical Analysis” ([DOI](https://doi.org/10.1111/0022-1082.00265)) beschreiben eine statistische Prüfung formalisierter Chartmuster in US-Aktien; Sullivan, Timmermann & White, “Data-Snooping, Technical Trading Rule Performance, and the Bootstrap” ([DOI](https://doi.org/10.1111/0022-1082.00163)) behandeln Mehrfachtests technischer Regeln; Gao et al., “Market Intraday Momentum” ([DOI](https://doi.org/10.1016/j.jfineco.2018.05.009)) untersuchen Intraday-Momentum in einem anderen Markt; Harvey, Liu & Zhu, “‘…and the Cross-Section of Expected Returns” ([DOI](https://doi.org/10.1093/rfs/hhv059)) behandeln Mehrfachtests in der empirischen Finanzforschung; Bailey et al., “The Probability of Backtest Overfitting” ([DOI](https://doi.org/10.21314/JCF.2016.322)) schlagen ein Verfahren zur Beurteilung von Backtest-Überanpassung vor. Osler, “Support for Resistance: Technical Analysis and Intraday Exchange Rates” ([Publikationsseite](https://www.newyorkfed.org/research/epr/00v06n2/0007osle.html)) untersucht veröffentlichte Support-/Resistance-Niveaus im FX-Markt; Bertsimas & Lo, “Optimal Control of Execution Costs” ([DOI](https://doi.org/10.1016/S1386-4181(97)00012-8)) behandeln Ausführungskosten, nicht Vorhersagekraft des VWAP. Die genannten Resultate sind auf andere Märkte/Fragen begrenzt und belegen keine Wirksamkeit für diese Crypto-/Stock-Perpetual-Regeln. Volltexte und Detailaussagen wurden in dieser Sitzung nicht unabhängig abgerufen.

## Offene Aufgaben und nächster Schritt

- [ ] GitHub-Child-Issues unter #3 anlegen, Beziehungen/Assignees setzen und Topic-/State-Labels erstellen/setzen; nötig ist eine Sitzung mit GitHub-Schreibzugriff.
- [ ] Den unabhängigen Schlusskritiker nach Abschluss der noch laufenden internen Recherche beauftragen; Quellen, Methodik, Auswahl-/Lookahead-Bias und Aussagen prüfen. Bis dahin kein unabhängiger Review behaupten.
- [ ] Offizielle Bitget-Endpunktdokumentation und Live-Instrumente erneut abrufen; pro Instrument Historienumfang, Zeitstempel, Kosten/Funding und Markthandelszeiten anhand datierter Primärquellen verifizieren.
- [ ] Historische OHLCV- und gegebenenfalls Trade-/Quote-/Orderbuchdaten reproduzierbar sichern; wenn passende Daten nicht abrufbar sind, Datenlücke und nächsten Zugangsschritt dokumentieren.
- [ ] Erst danach vorab definierte Out-of-sample-Tests mit Baseline, realistischen Kosten und Ergebnissen je BTC/ETH, Altcoin-Gruppe und verifiziertem TradFi-Instrument durchführen.
- [ ] Haupt-Issue mit verlinkter Synthese, tatsächlichem Status und unabhängiger Kritik aktualisieren. Bis alle Akzeptanzkriterien erledigt sind bleibt #3 offen.
