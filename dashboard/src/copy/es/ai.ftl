## ai: traducción al español de en/ai.ftl

## features/intelligence/AimLine.tsx
ai-aim-line-your-aim-in-one-sentence = Tu objetivo, en una frase
ai-aim-line-roles-closest-to-it-come = Los { -role(num: "other") } más cercanos aparecen primero cuando el Radar se ordena por Mejor encaje. Nunca oculta ningún { -role(num: "one") }. Déjalo vacío para ordenar según lo que guardas y marcas como No es para mí.
ai-aim-line-couldn-t-save-your-aim = No se pudo guardar tu objetivo. Inténtalo de nuevo.
ai-aim-line-cancel = Cancelar
ai-aim-line-save = Guardar
ai-aim-line-open-roles-ranked-by-how = { $total ->
    [one] { $total } { -role(num: "one") } abierto, ordenado por lo bien que encaja
    [many] { $total } de { -role(num: "other") } abiertos, ordenados por lo bien que encajan
   *[other] { $total } { -role(num: "other") } abiertos, ordenados por lo bien que encajan
}
ai-aim-line-open-roles-ranked-by-what = { $total ->
    [one] { $total } { -role(num: "one") } abierto, ordenado según lo que guardas y marcas como No es para mí
    [many] { $total } de { -role(num: "other") } abiertos, ordenados según lo que guardas y marcas como No es para mí
   *[other] { $total } { -role(num: "other") } abiertos, ordenados según lo que guardas y marcas como No es para mí
}
ai-aim-line-open-roles-sorted-by-date = { $total ->
    [one] { $total } { -role(num: "one") } abierto, ordenado por fecha. Tu objetivo { $q } lo ordenará cuando la clasificación esté lista.
    [many] { $total } de { -role(num: "other") } abiertos, ordenados por fecha. Tu objetivo { $q } los ordenará cuando la clasificación esté lista.
   *[other] { $total } { -role(num: "other") } abiertos, ordenados por fecha. Tu objetivo { $q } los ordenará cuando la clasificación esté lista.
}
ai-aim-line-open-roles-sorted-by-date-2 = { $total ->
    [one] { $total } { -role(num: "one") } abierto, por fecha
    [many] { $total } de { -role(num: "other") } abiertos, por fecha
   *[other] { $total } { -role(num: "other") } abiertos, por fecha
}
ai-aim-line-your-aim = Tu objetivo
ai-aim-line-example = Diseño de producto en una empresa de tecnología climática, en remoto desde Europa
ai-aim-line-add-your-aim = { $choice ->
    [yes] Editar tu objetivo
   *[no] Añadir tu objetivo
}

## features/intelligence/AssistantsCard.tsx
ai-assistants-card-mcp-server = Apps de asistente (MCP)
ai-assistants-card-allowed-read-only = { $choice ->
    [yes] Permitido · lectura y cambios
   *[no] Permitido · solo lectura
}
ai-assistants-card-not-allowed-nothing-is-shared = No permitido · nada se comparte
ai-assistants-card-what-will-be-shared = Qué se compartirá
ai-assistants-card-what-will-not-be-shared = Qué no se compartirá
ai-assistants-card-set-up = Configurar
ai-assistants-card-allow-assistant-apps-to-connect = Permitir conectar apps de asistente
ai-assistants-card-allow-assistant-apps-to-update = Permitir que apps de asistente actualicen tu progreso
ai-assistants-card-stage-notes-next-action-audited = etapa · notas · siguiente paso · borradores de recetas · con registro
ai-assistants-card-it-can-then-read-what = Así podrá leer lo que indica esta tarjeta, nada más.
ai-assistants-card-run-this-once-in-a = Ejecuta esto una vez en una terminal y luego reinicia la app.
ai-assistants-card-most-apps-that-speak-mcp = La mayoría de las apps MCP lo aceptan. Añádelo a sus ajustes de MCP y luego reinicia la app.
ai-assistants-card-add-this-to-the-app = Añade esto a los ajustes de la app y luego reinicia la app.
ai-assistants-card-done = Listo
ai-assistants-card-anthropic = Anthropic
ai-assistants-card-set-up-the-claude-app = Configurar la app de Claude
ai-assistants-card-openai = OpenAI
ai-assistants-card-set-up-the-codex-app = Configurar la app de Codex
ai-assistants-card-any-client-that-speaks-mcp = Cualquier app compatible con MCP
ai-assistants-card-set-up-another-mcp-app = Configurar otra app MCP
ai-assistants-card-mcp-server-2 = Apps de asistente
ai-assistants-card-not-allowed-to-connect = { $choice ->
    [yes] · listo para configurar
   *[no] · sin permiso para conectarse
}
ai-assistants-card-allow-assistant-apps-to-connect-2 = Primero permite conectar apps de asistente
ai-assistants-card-off-nothing-leaves-this-computer = { $choice ->
    [yes] activado · solo se comparte con las apps que conectes
   *[no] desactivado · nada sale de este ordenador
}
ai-assistants-card-clipboard-access-was-blocked-select = No se pudo copiar. Selecciona el texto y cópialo tú.
ai-assistants-card-copy = { $choice ->
    [yes] Copiado
   *[no] Copiar
}

## features/intelligence/CapabilitiesCard.tsx
ai-capabilities-card-extended-capabilities = Funciones ampliadas
ai-capabilities-card-of-on = { $choice ->
    [yes] { $on } de { $capCount } activas · todo en este ordenador
   *[no] { $on } de { $capCount } activas
}
ai-capabilities-card-your-own-model = Tu propio modelo
ai-capabilities-card-finds-duplicate-job-posts-only = { $value } · encuentra ofertas duplicadas, solo cuando lo pides
ai-capabilities-card-apple-intelligence = Apple Intelligence
ai-capabilities-card-experimental-we-are-still-testing = { $value } · experimental
ai-capabilities-card-ready = listo
ai-capabilities-card-online-model-services = Proveedores de IA
ai-capabilities-card-none-connected = Ninguno añadido ·
ai-capabilities-card-add = Añadir
ai-capabilities-card-send-postings-to-online-services = Enviar { -posting(num: "other") }
ai-capabilities-card-the-example-says = el ejemplo dice
ai-capabilities-card-it-found = encontró
ai-capabilities-card-found-pay = { $band } · { $basis ->
    [base] salario base
    [total] compensación total
   *[unclear] base o total sin indicar
} · { $period ->
    [year] al año
    [month] al mes
    [hour] por hora
   *[unclear] periodo sin indicar
}
ai-capabilities-card-quote-from-the-posting = cita de la { -posting(num: "one") }
ai-capabilities-card-reason = motivo
ai-capabilities-card-no-connection-saved = ninguna conexión guardada
ai-capabilities-card-running-model-not-loaded = en marcha, modelo sin cargar
ai-capabilities-card-not-installed = sin instalar
ai-capabilities-card-server-stopped = servidor detenido
ai-capabilities-card-extended-capabilities-2 = Funciones ampliadas
ai-capabilities-card-use-your-own-model = Usar tu propio modelo
ai-capabilities-card-save-a-connection-first-then = { $choice ->
    [yes] Actívalo para iniciar tu servidor de IA local
   *[no] Guarda primero una conexión y luego actívalo
}
ai-capabilities-card-start = { $choice ->
    [v1] Procesando…
    [v2] Detener
   *[v3] Iniciar
}
ai-capabilities-card-configure-your-own-model = Configurar tu propio modelo
ai-capabilities-card-enable-apple-intelligence = Activar Apple Intelligence
ai-capabilities-card-test-apple-intelligence = Probar Apple Intelligence
ai-capabilities-card-turn-apple-intelligence-on-to = Activa Apple Intelligence para probarlo
ai-capabilities-card-test = { $choice ->
    [yes] Probando…
   *[no] Probar
}
ai-capabilities-card-nothing-is-sent = { $choice ->
    [yes] permitido cuando añadas un proveedor
   *[no] no se envía nada
}
ai-capabilities-card-off-nothing-is-sent = { $choice ->
    [yes] activado · los proveedores que actives reciben las { -posting(num: "other") }
   *[no] desactivado · no se envía nada
}
ai-capabilities-card-no-pay-range-found = { $choice ->
    [v1] La prueba falló
    [v2] La respuesta no coincide con la { -posting(num: "one") }
    [v3] Funciona
    [v4] Se encontró un rango publicado
   *[v5] No se encontró ningún rango publicado
}
ai-capabilities-card-on-device = en este ordenador
ai-capabilities-card-allow-sending-postings-to-online = { $choice ->
    [yes] Activa { $name } para usarlo
   *[no] Activa primero Enviar { -posting(num: "other") }
}
ai-capabilities-card-blocked-online-services-are-switched = { $choice ->
    [v1] en uso
    [v2] desactivado
   *[v3] bloqueado · el envío está desactivado
}
ai-capabilities-card-connection-ready-ms = conexión lista · { $latency_ms } ms
ai-capabilities-card-use = Usar { $name }
ai-capabilities-card-no-key = { $choice ->
    [yes] clave guardada
   *[no] sin clave
}
ai-capabilities-card-test-2 = Probar { $name }
ai-capabilities-card-configure = Configurar { $name }

## features/intelligence/CloudDialog.tsx
ai-cloud-dialog-a-direct-api-connection-billed = Usa tu propia clave de API, facturada aparte de cualquier plan de ChatGPT o Claude. Las { -posting(num: "other") } solo se envían cuando { $b } está activado.
ai-cloud-dialog-name = Nombre
ai-cloud-dialog-provider = Proveedor
ai-cloud-dialog-server-address-https = Dirección del servidor (HTTPS)
ai-cloud-dialog-model-id = ID del modelo
ai-cloud-dialog-api-key = Clave de API
ai-cloud-dialog-enable-this-connection = Activar este proveedor
ai-cloud-dialog-could-not-save = No se pudo guardar
ai-cloud-dialog-could-not-delete = No se pudo eliminar
ai-cloud-dialog-add-an-online-model-service = { $choice ->
    [yes] Configurar { $name }
   *[no] Añadir un proveedor de IA
}
ai-cloud-dialog-openai-api = API de OpenAI
ai-cloud-dialog-anthropic-api = API de Anthropic
ai-cloud-dialog-other-openai-compatible = Otro compatible con OpenAI
ai-cloud-dialog-required-to-test = { $choice ->
    [yes] Déjalo vacío para conservar la clave guardada
   *[no] Necesaria para probar
}
ai-cloud-dialog-delete = { $choice ->
    [yes] Sí, eliminar { $name }
   *[no] Eliminar
}
ai-cloud-dialog-delete-2 = { $choice ->
    [yes] Sí, eliminar
   *[no] Eliminar
}
ai-cloud-dialog-save = { $choice ->
    [yes] Guardando…
   *[no] Guardar
}

## features/intelligence/FitField.tsx
ai-fit-field-fit-of-open-roles-rising = Encaje de { $total } { -role(num: "other") } abiertos, de bajo a alto; { $join }. Selecciona un grado para ver sus { -role(num: "other") }.
ai-fit-field-roles = { $label }: { $count } { -role(num: "other") }

## features/intelligence/IntelligenceSection.tsx
ai-intelligence-section-the-board-keeps-working-meanwhile = el Radar sigue funcionando
ai-intelligence-section-preparing-matching-mb = preparando la clasificación: { $b }/{ $total_bytes } MB
ai-intelligence-section-new-roles-added-today = { $count ->
    [one] { $n } { -role(num: "one") } nuevo añadido hoy
    [many] { $n } de { -role(num: "other") } nuevos añadidos hoy
   *[other] { $n } { -role(num: "other") } nuevos añadidos hoy
}
ai-intelligence-section-no-new-roles-today = ningún { -role(num: "one") } nuevo hoy
ai-intelligence-section-fit-ranking = Orden por encaje
ai-intelligence-section-preview = Vista previa
ai-intelligence-section-the-strongest-of-roles = { $count ->
    [one] los más fuertes de { $label } · { $n } { -role(num: "one") }
    [many] los más fuertes de { $label } · { $n } de { -role(num: "other") }
   *[other] los más fuertes de { $label } · { $n } { -role(num: "other") }
}
ai-intelligence-section-your-best-matches = los que mejor encajan contigo
ai-intelligence-section-loading = cargando…
ai-intelligence-section-nothing-lands-in-right-now = ningún { -role(num: "one") } en { $value } ahora mismo
ai-intelligence-section-more = +{ $max } más ·
ai-intelligence-section-open-the-board = abrir el Radar
ai-intelligence-section-intelligence = IA
ai-intelligence-section-fit-ranking-2 = Orden por encaje
ai-intelligence-section-all-are-at-right-now = { $length ->
    [one] (está ahora mismo en { $top })
    [many] (los { $length } están ahora mismo en { $top })
   *[other] (los { $length } están ahora mismo en { $top })
}
ai-intelligence-section-this-band = este grado

## features/intelligence/LocalModelDialog.tsx
ai-local-model-dialog-your-own-model = Tu propio modelo
ai-local-model-dialog-a-model-server-you-run = Un modelo en tu servidor de IA local. Solo se usa cuando comparas dos { -posting(num: "other") }. Nada sale de este ordenador.
ai-local-model-dialog-server-type = Tipo de servidor
ai-local-model-dialog-server-address = Dirección del servidor
ai-local-model-dialog-generation-and-reasoning-parameters = Ajustes del modelo
ai-local-model-dialog-max-tokens = Tokens máximos
ai-local-model-dialog-temperature = Temperatura
ai-local-model-dialog-top-p = Top p
ai-local-model-dialog-timeout-s = Tiempo límite (s)
ai-local-model-dialog-thinking-budget = Presupuesto de razonamiento
ai-local-model-dialog-enable-model-thinking = Pensar antes de responder
ai-local-model-dialog-ms = { $wall_time_ms } ms
ai-local-model-dialog-could-not-switch-connection = Error al cambiar la conexión
ai-local-model-dialog-could-not-reach-the-model = No se pudo conectar con tu servidor de IA local
ai-local-model-dialog-configure-your-own-model = Configurar tu propio modelo
ai-local-model-dialog-saved-connections = Conexiones guardadas
ai-local-model-dialog-omlx-managed = oMLX, iniciado desde aquí
ai-local-model-dialog-optional = { $choice ->
    [yes] Déjalo vacío para conservar la clave guardada
   *[no] Opcional
}
ai-local-model-dialog-connection-incomplete = { $choice ->
    [yes] Conexión correcta
   *[no] Conexión incompleta
}
ai-local-model-dialog-test-connection = { $choice ->
    [yes] Probando…
   *[no] Probar conexión
}

## features/intelligence/MatchingModel.tsx
ai-matching-model-local-ai-model = Modelo de clasificación
ai-matching-model-downloading-of-mb = · descargando { $round }/{ $round2 } MB
ai-matching-model-roles-are-listed-newest-first = Los { -role(num: "other") } se muestran del más nuevo al más antiguo hasta que termine.
ai-matching-model-switching-to-the = Cambiando al { $nAME_LOWER }
ai-matching-model-of-roles-updated = { $done } de { $total } { -role(num: "other") } actualizados
ai-matching-model-you-can-keep-working-meanwhile = Puedes seguir trabajando mientras tanto.
ai-matching-model-not-downloaded = · sin descargar
ai-matching-model-the-could-not-be-downloaded = No se pudo descargar el { $value }.
ai-matching-model-could-not-be-downloaded = No se pudo descargar el modelo de clasificación.
ai-matching-model-check-your-internet-connection-and = Comprueba tu conexión a internet e inténtalo de nuevo.
ai-matching-model-use-the = Usar el { $nAME_LOWER }
ai-matching-model-current = · Actual
ai-matching-model-choose-automatically = Elegir automáticamente
ai-matching-model-switch-to-the = Cambiar al { $nAME_LOWER }
ai-matching-model-the-switch-to-the-is = El cambio al { $nAME_LOWER } está en pausa.
ai-matching-model-the-rest-finishes-tonight-on = El resto terminará esta noche por sí solo.
ai-matching-model-finish-now = { $choice ->
    [yes] Terminar ya, { $estimate }
   *[no] Terminar ya
}
ai-matching-model-go-back-to-the = Volver al { $nAME_LOWER }
ai-matching-model-the-small-model-is-built = El modelo pequeño está pensado para { $b } de RAM. Se desconoce la RAM de este ordenador, así que cualquiera de los dos modelos funciona.
ai-matching-model-gb = { $ramThresholdGb } GB
ai-matching-model-it-is-the-right-fit = Está pensado para los { $b } de RAM de este ordenador.
ai-matching-model-gb-2 = { $ramGb } GB
ai-matching-model-roles-re-ranked = { $corpusTotal } { -role(num: "other") } reordenados
ai-matching-model-roles = { $corpusTotal } { -role(num: "other") }
ai-matching-model-re-ranked = reordenados
ai-matching-model-keep-working-while-it-runs = Sigue trabajando mientras se ejecuta
ai-matching-model-stop-anytime-restart-anytime-nothing = Detenlo y reanúdalo cuando quieras. No se pierde nada.
ai-matching-model-keep-the-computer-awake-until = Mantén el ordenador activo hasta terminar
ai-matching-model-start-the-switch = Iniciar el cambio
ai-matching-model-big-model = Modelo grande
ai-matching-model-small-model = Modelo pequeño
ai-matching-model-big-model-2 = modelo grande
ai-matching-model-small-model-2 = modelo pequeño
ai-matching-model-under-a-minute = menos de un minuto
ai-matching-model-about-min = unos { $minutes } min
ai-matching-model-about-hr = unas { $round } h
ai-matching-model-matching-model = Modelo de clasificación
ai-matching-model-download-progress = Progreso de la descarga
ai-matching-model-stop-and-go-back-to = { $choice ->
    [yes] Deteniendo…
   *[no] Detener y volver al { $nAME_LOWER }
}
ai-matching-model-switching-progress = Progreso del cambio
ai-matching-model-text = { $choice ->
    [yes] { " " }· quedan { $left }
   *[no] { "" }
}
ai-matching-model-stop-and-go-back-to-2 = { $choice ->
    [yes] Deteniendo…
   *[no] Detener y volver al { $value }
}
ai-matching-model-other-model = otro modelo
ai-matching-model-roles-ranked = { $choice ->
    [yes] { $corpus_total ->
        [one] { $value } de { $corpus_total } { -role(num: "one") } actualizado
        [many] { $value } de { $corpus_total } de { -role(num: "other") } actualizados
       *[other] { $value } de { $corpus_total } { -role(num: "other") } actualizados
    }
   *[no] { $corpus_embedded ->
        [one] { $corpus_embedded } { -role(num: "one") } ordenado
        [many] { $corpus_embedded } de { -role(num: "other") } ordenados
       *[other] { $corpus_embedded } { -role(num: "other") } ordenados
    }
}
ai-matching-model-the-big-model-produces-better = El modelo grande da mejores resultados.
ai-matching-model-switch-only-if-you-want = Cambia solo si quieres liberar RAM.
ai-matching-model-small-model-is-built-for = Modelo pequeño pensado para
ai-matching-model-your-computer-has = Este ordenador tiene
ai-matching-model-local-ai-model-switch = Cambio del modelo de clasificación

## features/intelligence/OriginBadge.tsx
ai-origin-badge-cloud-connected = { $choice ->
    [yes] En este ordenador
   *[no] Sale de este ordenador
}

## features/intelligence/AssistantsCard.tsx (a mano)
ai-assistants-card-shares-role-titles-companies-locations-and-link = Títulos de { -role(num: "other") }, { -company(num: "other") }, ubicaciones y enlaces
ai-assistants-card-shares-pay-level-and-how-long-the-role-has-been = Compensación, nivel y cuánto tiempo lleva abierto el { -role(num: "one") }
ai-assistants-card-shares-the-full-posting-when-they-open-one = La { -posting(num: "one") } completa, al abrirla
ai-assistants-card-shares-your-progress-on-roles-stage-priority-no = Tu progreso en los { -role(num: "other") }: etapa, prioridad, notas, siguiente paso
ai-assistants-card-shares-public-pages-it-asks-roleband-to-open = Páginas web públicas que pide abrir desde este ordenador
ai-assistants-card-never-your-profile-and-intent-statement = Tu perfil y tu objetivo
ai-assistants-card-never-your-own-salary-or-contacts = Tu salario o tus contactos
ai-assistants-card-never-anything-from-your-other-apps = Nada de tus otras apps
ai-assistants-card-app-claude-app = App de Claude
ai-assistants-card-app-codex-app = App de Codex
ai-assistants-card-app-other-app = Otra app

## Nombres de conexión predeterminados (a mano)
ai-local-model-dialog-default-name = Tu propio modelo

## features/intelligence/CapabilitiesCard.tsx
ai-capabilities-card-ms = { $latency_ms } ms

## Los textos del servidor de la pantalla de IA
ai-availability-available = Listo.
ai-availability-disabled-by-flag = Desactivado.
ai-availability-sdk-absent = Apple Intelligence necesita macOS 26 o posterior en Apple silicon.
ai-availability-apple-intelligence-disabled = Apple Intelligence está desactivado. Actívalo en Ajustes del Sistema.
ai-availability-device-ineligible = Este ordenador no es compatible con Apple Intelligence.
ai-availability-model-not-ready = Aún no está listo. Puede que siga descargándose.
ai-availability-not-configured = No hay ningún modelo configurado. Añade uno en Ajustes › IA.
ai-availability-server-unreachable = Tu servidor de IA local no respondió. Inícialo y vuelve a probar.
ai-availability-egress-not-permitted = El envío de { -posting(num: "other") } a proveedores de IA está desactivado. Actívalo en Ajustes › IA.
ai-origin-none = No se ejecutó ningún modelo
ai-origin-on-device = En este ordenador: Apple Intelligence
ai-origin-this-mac = En este ordenador: tu propio modelo
ai-origin-cloud = Enviado a un proveedor de IA
ai-self-test-prefiltered = No se encontró compensación en el texto, así que no se llamó al modelo. Es lo normal en la mayoría de las { -posting(num: "other") }.
ai-self-test-model-failed = El modelo no dio una respuesta útil ({ $failure }).
ai-local-test-max-tokens = La respuesta se cortó en Tokens máximos. Auméntalo y vuelve a probar.
ai-local-test-succeeded = Conectado. El modelo respondió.
ai-local-server-action-failed = { $action ->
    [start] No se pudo iniciar tu servidor de IA local. Inícialo tú y luego prueba la conexión.
   *[stop] No se pudo detener tu servidor de IA local. Detenlo tú.
}

## El estado del servidor local cuando responde
ai-capabilities-card-running = en marcha

## Una lectura fallida, dicha.
ai-intelligence-section-matches-load-failed = No se pudieron cargar los puestos que mejor encajan contigo
ai-intelligence-section-band-load-failed = No se pudieron cargar los puestos de este grado
ai-egress-title = ¿Permitir el envío a proveedores de IA?
ai-egress-detail = El texto de las { -posting(num: "other") } solo se envía a los proveedores de IA que actives, incluidos los que añadas o actives más adelante.
ai-egress-destinations = Proveedores guardados
ai-egress-empty = No has añadido ningún proveedor de IA. No se envía nada hasta que añadas y actives uno.
ai-egress-allow = Permitir

ai-capabilities-card-apple-off = desactivado

ai-capabilities-card-apple-off-in-system-settings = desactivado en Ajustes del Sistema

ai-capabilities-card-apple-downloading = descargando

ai-capabilities-card-apple-needs-macos = necesita macOS 26 o posterior en Apple silicon

ai-capabilities-card-apple-not-supported = no compatible con este ordenador

ai-local-server-start-pending = Tu servidor de IA local aún se está iniciando. Vuelve a comprobarlo en un minuto.
