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
picks-end-passed-only = { $passed }.
picks-end-passed = { $count ->
    [one] { $count } { -role(num: "one") } descartado esta semana
    [many] { $count } de { -role(num: "other") } descartados esta semana
   *[other] { $count } { -role(num: "other") } descartados esta semana
}

## Descartar una selección: la pregunta
picks-why-title = ¿Por qué no es para ti?
picks-why-role = { $title } · { $company }
picks-why-pay = Sueldo bajo
picks-why-level = Nivel equivocado
picks-why-work = Trabajo distinto
picks-why-company = No esta empresa
picks-why-place = Lugar equivocado
picks-why-other = Otra cosa
picks-why-note = Al pulsar un motivo, el puesto sale de Destacados y de tu Radar, y tu asistente sabe por qué.
picks-why-skip = Omitir el motivo
picks-why-keep = Conservarlo

## Descartados
picks-passed-heading = Descartados
picks-passed-loading = Cargando lo descartado…
picks-passed-load-failed = No se pudo cargar lo descartado
picks-passed-summary = { $count ->
    [one] { $count } { -role(num: "one") } descartado esta semana
    [many] { $count } de { -role(num: "other") } descartados esta semana
   *[other] { $count } { -role(num: "other") } descartados esta semana
}
picks-passed-back = Volver a Destacados
picks-passed-removed = Quitados por ti ({ $count })
picks-passed-close = Casi ({ $count })
picks-passed-read = Leídos y descartados ({ $count })
picks-passed-ruled = Excluidos por una regla estricta antes de leerlos ({ $count })
picks-passed-said = { $reason ->
    [pay_too_low] Dijiste que el sueldo es bajo.
    [wrong_level] Dijiste que el nivel no encaja.
    [wrong_role] Dijiste que el trabajo es distinto.
    [company] Dijiste que no esta empresa.
    [wrong_place] Dijiste que el lugar no es el adecuado.
    [wrong_domain] Dijiste que no es tu ámbito.
   *[other] Dijiste que es por otro motivo.
}
picks-passed-words = En tus palabras: «{ $words }».
picks-passed-put-back = Recuperarlo
picks-passed-put-back-failed = No se pudo recuperar «{ $title }». Inténtalo de nuevo.
picks-passed-show-all = Ver los { $count }
picks-pass-hard-rule = Incumple una regla estricta
picks-pass-hard-rule-named = Regla estricta: { $rules }
picks-pass-off-direction = Otra dirección
picks-pass-below-level = Bajo tu nivel
picks-pass-out-of-reach = Fuera de alcance
picks-pass-not-better = No supone un avance
picks-pass-not-real = Puesto no activo
picks-pass-other = Otros
picks-passed-empty-title = Nada descartado esta semana
picks-passed-empty = Aquí aparecen los puestos que el asistente lee y no elige, con el motivo.
