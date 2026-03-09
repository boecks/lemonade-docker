TODO

Problem Summary: auto_unload.py – Idle Timer Race Condition
Ziel: Idle-Timer soll erst nach dem ersten abgeschlossenen Request starten, nicht ab Ladezeit.
Beobachtung:

last_use im /api/v1/health Response wird beim Laden des Modells gesetzt und aktualisiert sich nach abgeschlossenen Requests nicht zuverlässig – der Wert bleibt auf dem Ladezeit-Timestamp stehen
Dadurch kann nicht unterschieden werden ob last_use vom Ladevorgang oder von einem echten Request stammt
Lemonade schützt laufende Inferences vor Eviction (dokumentiert + bestätigt im Log) – der Unload wartet bis die Generation fertig ist, aber der Timer läuft trotzdem ab Ladezeit

Letzter Stand:

last_use-Baseline-Ansatz: funktioniert nicht weil last_use sich nicht verändert
/api/v1/stats mit output_tokens-Fingerprint: noch ungetestet, vielversprechend aber unklar ob output_tokens sich zuverlässig nach jedem Request ändert

Offene Frage an Lemonade:
Gibt es einen zuverlässigen API-Indikator für "Request gerade aktiv" oder "letzter Request abgeschlossen um Zeitpunkt X"? Der last_use-Wert im Health-Endpoint scheint broken zu sein.