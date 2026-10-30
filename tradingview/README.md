# TradingView-Strategien

Diese drei Pine-Script-v6-Dateien sind eigenständige `strategy()`-Skripte für den TradingView Strategy Tester. Sie ändern das Dashboard nicht. Maßgebliche Referenz für die Scannerregeln sind `dist/breakout.js`, `dist/pattern.js`, `dist/tradfi.js` und `dist/app.js`; die Strategien erfinden keine Trefferquote oder Profitabilität.

## Installation und Test

1. In TradingView ein verfügbares Symbol öffnen, zum Beispiel einen Bitget-USDT-Perpetual für BTC, ETH oder einen Altcoin. Für TradFi nur dann einen Aktien-Perpetual wählen, wenn TradingView dafür historische Kerzen anbietet. Symbole, Anbieter und Historientiefe unterscheiden sich.
2. Den Chart auf 1m, 5m oder 15m stellen. Die Skripte rechnen direkt auf den Chartkerzen: Die Dashboard-Standards sind 5m für Treppen & Konsolidierung, 1m oder 5m für Impuls & Gegenkerzen sowie 1m für Momentum-Pullback. Ein 15m-Test ist eine alternative Kerzengröße und keine Nachbildung dieser Scanner-Zeiträume.
3. In **Pine Editor** jeweils nur eine `.pine`-Datei öffnen/einfügen, speichern und **Add to chart** wählen. Im **Strategy Tester** Zeitraum und Trades prüfen. Die Signale verwenden abgeschlossene Chartkerzen, ohne `request.security()` oder Lookahead. Bei einer Bestätigung am Kerzenschluss wird die Market-Order standardmäßig frühestens am nächsten Kerzen-Open ausgeführt (`process_orders_on_close=false`); das ist keine Intrabar-Ausführung.
4. Im Tester einen konkreten historischen Start- und Endzeitpunkt wählen, der unterschiedliche Marktphasen umfasst, und diesen Zeitraum für Vergleichstests beibehalten. Dasselbe Symbol, dieselben Kosten, Positionsgrößen- und Exit-Einstellungen verwenden. Erst getrennte Entwicklungs- und Out-of-sample-Zeiträume prüfen; Ergebnisse nicht durch wiederholtes Optimieren auf denselben Zeitraum auswählen.

## Strategie-Regeln und Annahmen

### Treppen & Konsolidierung — `stairs_consolidation.pine`

- Dashboard-Referenz: `dist/breakout.js`, Standardprofil `stairs`. Sechs gerichtete Impulskerzen benötigen mindestens vier steigende Schlusskurs-Übergänge (Short gespiegelt). Darauf folgen vier Konsolidierungskerzen; der Rücklauf vom Impulshoch/-tief beträgt 5–50 % und die Konsolidierung verletzt den Impulsursprung nicht. Ihr Gegenextrem darf höchstens 0,2 % über das Impulsextrem hinausragen.
- Ein Einstiegssignal entsteht erst, wenn die nächste abgeschlossene Kerze gerichtet über das Konsolidierungshoch (Long) beziehungsweise unter das Konsolidierungstief (Short) schließt und ihr Volumen mindestens dem einstellbaren Faktor des Durchschnitts der vier Konsolidierungskerzen entspricht. Standardfaktor: 1,0. Die Datei enthält beide Richtungen; „Direction“ kann sie einzeln begrenzen.
- Dashboard-Standard ist 5m. Andere Chartzeiträume ändern die Dauer der sechs Impuls- und vier Konsolidierungskerzen entsprechend.

### Impuls & Gegenkerzen — `impulse_counter_candles.pine`

- Dashboard-Referenz: `dist/pattern.js`. Der Impuls umfasst 2–6 Kerzen, davon mindestens zwei Drittel in Impulsrichtung; sein Schluss liegt jenseits der Range der zehn vorherigen Kerzen. Die Gegenkerzen (Standard 3, einstellbar 2–4) schließen gegen die Impulsrichtung und ihre Schlusskurse laufen weiter zurück.
- Standardwerte: Mindestimpuls 1 %, Impulsvolumen mindestens 1,5× des Durchschnitts der vorherigen zehn Kerzen, Rücklauf 5–50 % und durchschnittlicher Gegenkerzenkörper kleiner als 80 % des Impulskörpers. Der optionale Volumenfilter für den Rücksetzer verlangt standardmäßig ein niedrigeres Durchschnittsvolumen als im Impuls. Bestätigung: eine abgeschlossene gerichtete Kerze schließt jenseits des Hochs/Tiefs der letzten Gegenkerze und hält das Rücksetzertief/-hoch.
- Der Dashboard-Scanner prüft automatisch alle Impulslängen von 2 bis 6. Die Strategie verwendet eine einstellbare feste Impulslänge (Standard 2), damit der Backtest regelbestimmt bleibt; dadurch können Scanner und Strategie abweichen. Dashboard-Kerzengrößen sind 1m und 5m.

### Momentum-Pullback / erstes neues Hoch — `momentum_first_new_high.pine`

- Dashboard-Referenz: `dist/tradfi.js`. Long-only: 2–6 überwiegend steigende Impulskerzen, danach 1–3 fallende Gegenkerzen; der Rücklauf beträgt höchstens 50 % und unterschreitet den Impulsursprung nicht. Mindestimpuls-Standard ist 0,5 %.
- Der Scanner prüft mehrere Impuls- und Rücksetzerlängen, die Strategie verwendet einstellbare feste Längen (Standard 2 Impuls- und 1 Rücksetzerkerze). Der Dashboard-Status „neues Hoch berührt“ kann schon durch ein Intrakerzen-Hoch entstehen. Für einen bestätigten, reproduzierbaren Backtest verlangt diese Strategie zusätzlich einen Schlusskurs über dem Triggerhoch; das ist absichtlich strenger. Es gibt keinen Volumenfilter.
- Die Dashboard-24h-Änderung ist ein laufender Futures-Tickerwert und kein historisch zuverlässig rekonstruierbarer Filter. Sie wird daher nicht simuliert. Ebenso fehlen Nachrichten, Free Float und relatives Aktienvolumen. Diese Strategie ist eine einfache Chart-Annahme für Krypto- und Aktien-Perpetuals, keine vollständige nachrichtenbasierte Aktienstrategie. Dashboard-Standard ist 1m.

### Momentum-Ranking — keine Strategie

`dist/app.js` ordnet die aktuell gescannten Symbole nach 1-, 5- oder 15-Minuten-Rendite und bei Gleichstand nach 24h-Volumen; Long/Short-Rang hängt vom gewählten Zeitfenster und der Richtung ab. Das ist eine relative Rangfolge eines dynamischen Mehrsymbol-Universums, kein eigenständiger Einstiegstrigger für einen einzelnen Chart. Ohne feste, sachlich begründete Schwellen für Einstieg und Ausstieg wäre eine Einzelchart-Strategie eine erfundene Entsprechung. Deshalb gibt es dafür bewusst keine Pine-Strategie.

## Kosten, Positionsgröße und Interpretation

Alle drei Dateien starten mit 10.000 Kontowährung, 10 % Eigenkapital je Position, 0,06 % Kommission und zwei Ticks Slippage. Das sind sichtbare, änderbare Startannahmen, keine Bitget-Gebührenzusage. Ändere Kommission, Slippage und Ordergröße im Strategy-Tester unter **Settings / Properties** passend zum Symbol und Gebührenmodell. Stop-Loss und Take-Profit sind in jeder Strategie Prozent-Eingaben (Standard 1 % / 2 %); sie werden in Tick-Abstände umgerechnet und an den Entry angehängt. Durch Rundung, Tickgröße und Kurslücken kann der tatsächliche Abstand vom Prozentwert abweichen.

Es wird kein 20×-Hebel eingestellt und keine Börsenliquidation simuliert. TradingViews Margin-/Kontraktspezifikationen, Positionsgrößen und Füllmodell sind nicht automatisch gleich Bitget. Pine-`volume` und historische Verfügbarkeit hängen vom TradingView-Datenanbieter und Symbol ab; Einheiten und Werte können vom in Bitgets Kline-Daten verwendeten Volumenfeld abweichen. Fehlende oder andere Volumendaten können insbesondere volumenabhängige Signale verändern. Orderbuch- und Newsfilter werden nicht simuliert.

Trefferquote ist nur der Anteil profitabler geschlossener Trades in der getesteten Stichprobe; sie sagt ohne Gewinn-/Verlustgröße wenig aus. Tradeanzahl und Profitfaktor hängen von Symbol, Zeitraum und Kosten ab. Drawdown zeigt historische Rückgänge, nicht eine Verlustobergrenze; Nettoergebnis ist keine Prognose. Kleine Stichproben, Kurslücken, Datenanbieter, Slippage, Funding und Überoptimierung können das Ergebnis erheblich verändern. Funding ist in diesen Skripten nicht nachgebildet. Keine der Kennzahlen beweist künftige Profitabilität.

## Nachvollziehbare Prüfschritte

Die folgenden Erwartungen sind Regelprüfungen, keine behaupteten TradingView-Ergebnisse. Pine-Laufzeit und TradingView Strategy Tester stehen in dieser Repository-Umgebung nicht zur Verfügung; eine erfolgreiche Kompilierung oder ein ausgeführter Backtest wird daher nicht behauptet.

| Skript | Prüffall | Erwartung |
| --- | --- | --- |
| Treppen | Auf einem lückenlosen 5m-Chart sechs Impulskerzen mit mindestens vier steigenden Schlusskurs-Übergängen, vier Kerzen mit 5–50 % Rücklauf und danach eine grüne Schlusskerze über dem Konsolidierungshoch; Ausbruchsvolumen mindestens 1,0× des Konsolidierungsdurchschnitts. | SETUP auf der letzten Konsolidierungskerze; TRIGGER am Ausbruchsschluss; Long-Order frühestens am nächsten Open. |
| Treppen | Spiegelbildlich fallender Impuls und Ausbruchsschluss unter dem Konsolidierungstief; Rücklaufgrenzen genau 5 % oder 50 % testen. | Short-Setup und Short-Order; beide Grenzwerte sind inklusiv. Ein Rücklauf unter 5 % oder über 50 %, weniger als vier steigende/fallende Impulsübergänge oder unzureichendes Volumen ergibt keinen Trigger. |
| Impuls & Gegenkerzen | Standardeinstellungen; gültiger 1m-/5m-Impuls über der vorherigen Zehn-Kerzen-Range, drei absteigende Gegenkerzen mit gültigem Rücklauf und Volumen, danach Schluss jenseits der letzten Gegenkerze bei intakter Struktur. | SETUP auf dem letzten Gegenkerzenschluss; bestätigter Long- oder Short-Trigger auf der Folgekerze. |
| Impuls & Gegenkerzen | Gegenrichtung spiegeln; alternativ Volumenfaktor über das gemessene Verhältnis oder maximalen Rücklauf unter den tatsächlichen Rücklauf setzen. | Short muss spiegelbildlich funktionieren; ein nicht erfüllter Filter unterdrückt den Trigger. Zwei bis vier Gegenkerzen sind zulässig, außerhalb dieses Bereichs nicht. |
| Momentum-Pullback | Auf einem 1m-Chart zwei überwiegend steigende Impulskerzen (mindestens 0,5 %), eine fallende Pullbackkerze und eine Folgekerze, die über dem Pullbackhoch schließt und das Pullbacktief hält. | SETUP, dann NEW HIGH und Long-Order frühestens am nächsten Open. |
| Momentum-Pullback | Folgekerze überschreitet das Pullbackhoch nur intrabar, schließt aber darunter. | Kein Entry (bewusst strenger als der Dashboard-Touch-Status). Ein Rücklauf über 50 % oder bis zum Impulsursprung verwirft das Setup. |

Für Long/Short-Grenzfälle auf neuen Symbolen zusätzlich ungültige Daten-/Volumenabschnitte und Zeitlücken prüfen. Die Pine-Regeln verwerfen nicht aufeinanderfolgende Chartkerzen innerhalb des jeweils geprüften Musters.
