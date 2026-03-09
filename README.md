Problem Summary: auto_unload.py – zwei Bugs
Bug 1: Timer startet zu früh

last_use im /api/v1/health wird beim Laden gesetzt und aktualisiert sich nach Requests nicht zuverlässig
Timer läuft ab Ladezeit statt ab letztem abgeschlossenem Request
last_use-Baseline-Ansatz scheitert daran

Bug 2: Timer resettet nicht bei erneutem Prompt

Wenn User vor Timeout nochmal promptet, müsste der Idle-Timer zurückgesetzt werden
Passiert nicht weil last_use sich nicht ändert – der Unloader "sieht" den neuen Request nicht
Beide Bugs haben dieselbe Wurzel: last_use ist unzuverlässig

Letzter Stand:

/api/v1/stats mit output_tokens-Fingerprint implementiert – löst theoretisch beide Bugs auf einmal weil jeder abgeschlossene Request output_tokens verändert und den Timer zurücksetzt
Noch ungetestet

Offene Frage an Lemonade-Team:

Ist last_use im Health-Endpoint intentionally nur der Ladezeit-Timestamp?
Gibt es einen zuverlässigen "letzter Request abgeschlossen"-Indikator?
Ändert sich output_tokens in /api/v1/stats nach jedem abgeschlossenen Request kumulativ?