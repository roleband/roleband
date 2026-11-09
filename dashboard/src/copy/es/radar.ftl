## Radar

## Barra de herramientas
radar-sort-best-fit = Mejor encaje
radar-sort-best-fit-unranked = Mejor encaje: más recientes
radar-sort-best-fit-unranked-why = Mejor encaje ordena los puestos según los que guardas y tu objetivo. Hasta que tengas alguno, van de más reciente a más antiguo.
radar-sort-newest = Más recientes
radar-field-location = Ubicación
radar-field-pay = Base
radar-field-pay-full = Salario base
radar-sort-age = Antigüedad
radar-field-level = Nivel
radar-field-company = Empresa
radar-field-title = Título
radar-search-label = Buscar en títulos y descripciones
radar-search-placeholder = Buscar en títulos y descripciones…
radar-count-not-for-me = que marcaste como No es para mí
radar-total-failed = No se pudo contar el total
radar-total-retry-aria = Volver a contar el total
radar-show-all-title = Volver a los puestos que no has marcado
radar-show-all = Mostrar todo
radar-reset-title = Quitar todos los filtros
radar-reset = Restablecer todo
radar-new-today-clear = Quitar nuevos
radar-new-today = Nuevos
radar-reposted-today-clear = Quitar republicado hoy
radar-reposted-today = Republicado hoy
radar-sort = Ordenar
radar-order-reverse = Invertir el orden
radar-sort-by = Ordenar por

## Interpretación de la búsqueda
radar-field-discipline = Disciplina
radar-field-workplace = Modalidad
radar-interp-pay-range = { $min }–{ $max }
radar-interp-pay-min = { $min }+
radar-interp-pay-max = < { $max }
radar-interp-aria = Filtros interpretados
radar-interp-label = Interpretado como

## Modos
radar-mode-open = Abiertos
radar-mode-closed = Cerrados

## Acciones del radar
radar-save-failed = No se pudo guardar { $title }. Inténtalo de nuevo.
radar-unsave-failed = No se pudo quitar { $title } de tu seguimiento. Inténtalo de nuevo.
radar-restore-failed = No se pudo restaurar { $title }. Inténtalo de nuevo.
radar-exclude-done = { $count ->
    [one] { $count } puesto con “{ $value }” salió de tu radar. Cámbialo en Perfil › Qué buscas.
    [many] { $count } de puestos con “{ $value }” salieron de tu radar. Cámbialo en Perfil › Qué buscas.
   *[other] { $count } puestos con “{ $value }” salieron de tu radar. Cámbialo en Perfil › Qué buscas.
}
radar-exclude-failed = No se pudo guardar eso para “{ $value }”. Inténtalo de nuevo.

## La lista
radar-loading = Cargando tu radar…
radar-load-failed = No se pudo cargar tu radar
radar-filters-load-failed = No se pudieron cargar los filtros
radar-board-fresh-more = { $count ->
    [one] { $count } { -role(num: "one") } más coincide desde que se cargó esta lista.
    [many] { $count } de { -role(num: "other") } más coinciden desde que se cargó esta lista.
   *[other] { $count } { -role(num: "other") } más coinciden desde que se cargó esta lista.
}
radar-board-fresh-changed = Esta lista ha cambiado desde que se cargó.
radar-board-fresh-show = Ver la actualización
radar-empty-not-for-me-title = Nada marcado como «No es para mí»
radar-empty-not-for-me = Lo que marques como No es para mí espera aquí, por si cambias de opinión.
radar-empty-closed-title = Aún no se ha cerrado nada
radar-empty-closed = Un puesto aparece aquí cuando ya no está en su página de empleo.
radar-empty-first-scan-finish = Terminar la configuración
radar-exact-head = Coincidencia exacta ({ $count })
radar-show-other = { $count ->
    [one] Mostrar { $count } coincidencia más
    [many] Mostrar { $count } de coincidencias más
   *[other] Mostrar { $count } coincidencias más
}
radar-other-head = Otras coincidencias ({ $count })
radar-truncated-other = Otras coincidencias muestra las { $shown } mejores de { $matched }. Ajusta los filtros para ver el resto.
radar-truncated = Se muestran los { $shown } mejores de { $matched } puestos que coinciden, primero el mejor encaje. Ordena por Más recientes o ajusta los filtros para ver el resto.
radar-level-not-placed-note = La oferta no indica nivel, o indica uno en los términos propios de la empresa que aún no está asignado.
radar-exclude-offer = No es para mí: todo “{ $value }”

## El registro de filtros
radar-field-career-track = Trayectoria
radar-field-world = Ámbito
radar-filter-company-aria = Filtrar por empresa
radar-filter-location-aria = Filtrar por ubicación
radar-filter-level-aria = Filtrar por nivel
radar-filter-discipline-aria = Filtrar por disciplina
radar-filter-track-aria = Filtrar por trayectoria
radar-filter-workplace-aria = Filtrar por modalidad
radar-filter-world-aria = Filtrar por ámbito
radar-filter-no-companies = Ninguna empresa coincide.
radar-filter-no-locations = Ninguna ubicación coincide.
radar-filter-more = Más filtros
radar-filter-listed-within = Publicado en los últimos
radar-filter-any = Cualquiera
radar-filter-days = { $count } d
radar-filter-discloses-pay = Publica un rango
radar-filter-pay-from = Base desde
radar-filter-pay-from-full = Salario base desde
radar-filter-pay-up-to = Base hasta
radar-filter-pay-up-to-full = Salario base hasta
radar-filter-min = Mín.
radar-filter-max = Máx.
radar-filter-pay-min-aria = Salario base más bajo
radar-filter-pay-max-aria = Salario base más alto
radar-filter-showing = Mostrar
radar-filter-unread-only = Solo no leídos

radar-empty-filtered-title = Ningún puesto coincide con estos filtros

radar-empty-filtered-clear = Quitar todos los filtros

radar-empty-few-title = { $count ->
    [one] Sigues { $count } empresa y aún no encaja ningún puesto
    [many] Sigues { $count } de empresas y aún no encaja ningún puesto
   *[other] Sigues { $count } empresas y aún no encaja ningún puesto
}

radar-empty-few = { $choice ->
    [counted] Se pueden escanear unas { $more } empresas más. Si sigues más, encontrarás más puestos que encajen.
   *[other] Si sigues más empresas, encontrarás más puestos que encajen.
}

radar-empty-follow-more = Sigue más empresas

radar-empty-change-looking-for = Cambia lo que buscas

radar-empty-fit-title = Aún no hay nada que encaje con lo que buscas

radar-empty-fit = { $choice ->
    [checking] Escaneando las demás empresas: { $checked } de { $total } por ahora. Los puestos que encajen aparecen aquí a medida que se encuentran.
   *[done] Aún no hay ningún puesto que encaje en las empresas que sigues. Cada una se vuelve a escanear cada pocas horas.
}

radar-first-scan-starting-title = Tu primer escaneo está a punto de empezar

radar-first-scan-starting = Empieza en unos minutos. Los puestos nuevos aparecen aquí a medida que se encuentran.

radar-first-scan-running-title = Tu primer escaneo está en marcha

radar-first-scan-progress = { $read } de { $total } empresas escaneadas. Los puestos nuevos aparecen aquí a medida que se encuentran.

radar-first-scan-progress-unknown = Los puestos nuevos aparecen aquí a medida que se encuentran.

radar-first-scan-nothing-yet = { $read } de { $total } empresas escaneadas, ninguna con un puesto que encaje con { $link } por ahora.

radar-first-scan-looking-for = lo que buscas

radar-first-scan-back = { $when ->
    [hour] Vuelve dentro de una hora, más o menos.
    [almost] Casi listo.
   *[soon] Vuelve dentro de unos minutos.
}

radar-first-scan-back-minutes = { $minutes ->
    [one] Vuelve dentro de { $minutes } minuto, más o menos.
    [many] Vuelve dentro de unos { $minutes } de minutos.
   *[other] Vuelve dentro de unos { $minutes } minutos.
}

radar-first-scan-held-title = Tu primer escaneo está en espera

radar-first-scan-held-count = { $read } de { $total } empresas escaneadas.

radar-first-scan-held = { $reason ->
    [waiting_for_mains] Tu ordenador funciona con batería. El escaneo continúa cuando lo enchufes.
    [waiting_for_wake] El escaneo continúa cuando tu ordenador se active.
    [schema_pending] Se está terminando una actualización. El escaneo continúa justo después.
    [dependencies_pending] Se está terminando una actualización. El escaneo continúa justo después.
    [setup_source] Ejecuta ./setup.sh en tu carpeta de código fuente para terminar la actualización. El escaneo continúa justo después.
    [busy_external] Hay otro escaneo en marcha. El tuyo empieza justo después.
    [supervisor_stale] El servicio en segundo plano no está en marcha. Reinicia la app para continuar.
    [backoff] Algunos sitios de empleo pidieron reducir el ritmo. El escaneo continúa por sí solo.
    [preflight_failed] El escaneo está en espera hasta que esta versión supere sus comprobaciones.
   *[other] El escaneo continúa por sí solo cuando esto se resuelva.
}

radar-first-scan-held-until = Algunos sitios de empleo pidieron reducir el ritmo. El escaneo continúa a las { $time }.

radar-first-scan-stopped-title = Tu primer escaneo está detenido

radar-first-scan-stopped = { $read } de { $total } empresas escaneadas. Si vuelves a escanear, continúa donde se detuvo.

radar-first-scan-scan-now = Escanear ahora

radar-first-scan-none-title = Aún no hay empresas que escanear

radar-first-scan-none = Sigue algunas empresas y empezará tu primer escaneo.

radar-first-scan-follow = Seguir empresas

radar-first-scan-filtered = Hay filtros activos, así que aquí se ven menos puestos.

radar-first-scan-line = Aún escaneando{ $dots } { $read } de { $total } empresas escaneadas. Aparecen más puestos a medida que se encuentran.

radar-end-scanning = { $count ->
    [one] Eso es todo por ahora. Queda { $count } empresa por escanear.
    [many] Eso es todo por ahora. Quedan { $count } de empresas por escanear.
   *[other] Eso es todo por ahora. Quedan { $count } empresas por escanear.
}

radar-end-few = Estos son todos los puestos que encajan en las empresas que sigues. ¿Falta algo? { $follow } o { $change }.

radar-end-change-looking-for = cambia lo que buscas

radar-end-fit = Estos son todos los puestos que encajan en las empresas que sigues. ¿Falta algo? { $change }.

radar-end-filtered = Eso es todo lo que coincide con estos filtros. { $clear } para ver más.
