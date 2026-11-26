## Destacados

## La pantalla
picks-loading = Cargando tus destacados…
picks-load-failed = No se pudieron cargar tus destacados
picks-not-set-up = Destacados no está configurado
picks-host = { $host ->
    [claude-code] Claude Code
    [codex] Codex
   *[other] Tu asistente
}

## La lista vacía
picks-empty-title = Nada ha superado tu listón todavía
picks-empty-read = { $count ->
    [one] Esta semana se leyó { $count } { -role(num: "one") }. El siguiente que lo merezca aparecerá aquí.
    [many] Esta semana se leyeron { $count } de { -role(num: "other") }. El siguiente que lo merezca aparecerá aquí.
   *[other] Esta semana se leyeron { $count } { -role(num: "other") }. El siguiente que lo merezca aparecerá aquí.
}
picks-empty-filtered-title = Ningún destacado coincide con estos filtros
picks-empty-filtered = { $count ->
    [one] Los filtros ocultan { $count } destacado.
    [many] Los filtros ocultan { $count } de destacados.
   *[other] Los filtros ocultan { $count } destacados.
}
picks-empty-search-title = Ningún destacado coincide con esta búsqueda

## Avisos sobre la lista
picks-note-paused = Las revisiones están en pausa. No se lee nada hasta que se reanuden.
picks-resume = Reanudar revisiones
picks-resume-failed = No se pudieron reanudar las revisiones. Inténtalo de nuevo.
picks-note-asks = { $host } pide permiso antes de cada comando, así que una revisión no puede hacerse sola.
picks-note-fix = Cómo arreglarlo
picks-note-disconnected = { $host } ya no está conectado.
picks-note-connect = Conectarlo de nuevo

## Donde termina la lista
picks-end-checked = Revisado { $when } por { $host }.
picks-end-waiting = { $count ->
    [one] Espera { $count } { -role(num: "one") }.
    [many] Esperan { $count } de { -role(num: "other") }.
   *[other] Esperan { $count } { -role(num: "other") }.
}
picks-end-stopped = Se detuvo antes de tiempo: { $reason }. El resto se lee en la siguiente revisión.
picks-end-stopped-plain = Se detuvo antes de terminar. El resto se lee en la siguiente revisión.
picks-end-passed = { $count ->
    [one] { $count } { -role(num: "one") } descartado esta semana.
    [many] { $count } de { -role(num: "other") } descartados esta semana.
   *[other] { $count } { -role(num: "other") } descartados esta semana.
}
