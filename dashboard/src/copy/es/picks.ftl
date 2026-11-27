## Destacados

## La pantalla
picks-loading = Cargando tus destacados…
picks-load-failed = No se pudieron cargar tus destacados
picks-refresh-failed = No se pudieron actualizar tus destacados. Se muestra el último resultado.
picks-fresh-more = { $count ->
    [one] { $count } destacado nuevo desde que se cargó esta lista.
    [many] { $count } de destacados nuevos desde que se cargó esta lista.
   *[other] { $count } destacados nuevos desde que se cargó esta lista.
}
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

## Presentación: Destacados antes de configurarlo
picks-onboard-headline = Tu asistente de IA
picks-onboard-line = Un modelo de IA de frontera aprende lo que quieres, lee cada { -role(num: "one") } nuevo y se queda con los pocos que merecen un cambio.
picks-onboard-count = { $count ->
    [one] { -role(num: "one") } nuevo, leído
    [many] de { -role(num: "other") } nuevos, todos leídos
   *[other] { -role(num: "other") } nuevos, todos leídos
}
picks-onboard-reason-work-lead = El trabajo que pediste
picks-onboard-reason-work = { $lead }, al nivel que fijaste.
picks-onboard-reason-more-lead = Más de lo que tienes hoy
picks-onboard-reason-more = { $lead }, en sueldo o en alcance.
picks-onboard-step-say = Di una frase a tu asistente
picks-onboard-step-arrive = Los destacados llegan aquí
picks-onboard-say = Dilo en tu asistente
picks-onboard-works-with = Funciona con Claude Code y Codex
picks-onboard-sentence = Ejecuta `roleband connect --apply` y luego configura mis destacados.
picks-onboard-sentence-connected = configura mis destacados
picks-onboard-waiting = Esperando a tu asistente
picks-onboard-connected = { $host } está conectado. Lo que guarde aparece aquí.
picks-onboard-terminal = O ejecuta el comando en Terminal
picks-onboard-footnote = Unos diez minutos, con el plan que ya tienes. Permite que tu asistente ejecute roleband sin preguntar. Tu CV y los { -role(num: "other") } que lee van al modelo de tu asistente.
picks-onboard-in-terminal = En Terminal, para
picks-onboard-terminal-host = Asistente
picks-onboard-in-host = En { $host }
picks-onboard-back = Volver a una sola frase
picks-onboard-access = Permite que tu asistente lea tus { -role(num: "other") } y guarde destacados.
picks-onboard-under-way = La configuración está en marcha
picks-onboard-under-way-line = { $host } pregunta. Lo que guarde aparece aquí.
picks-onboard-row = { $step ->
    [connect] { $host } está conectado
    [background] Tu trayectoria
    [situation] Dónde estás hoy
    [bar] Qué te haría cambiar
    [rules] Reglas firmes
    [tradeoffs] Qué estarías dispuesto a ceder
    [targets] Empresas que quieres y las que evitas
    [calibration] Un primer vistazo a { -role(num: "other") } reales
    [budget] Cada cuánto quieres tener noticias
    [confirm] Lo que buscas, dicho en voz alta
    [trial] Una primera prueba con { -role(num: "other") } abiertos hoy
   *[routine] Revisiones programadas cada día
}
picks-onboard-row-now = { $step ->
    [trial] Probándolo ahora
    [routine] Programándose ahora
   *[other] Preguntándose ahora
}
picks-onboard-row-waits = Espera al primer escaneo
picks-onboard-row-saved = Guardado
picks-onboard-resume = ¿Cerraste el chat? Cualquier chat lo retoma:
