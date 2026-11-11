applications-board-summary = En curso: { $moving } · Decididos: { $decided } · Rechazados o cerrados: { $closed } · { $needNext }

applications-board-need-next = { $count ->
        [one] { $count } necesita
        [many] { $count } necesitan
       *[other] { $count } necesitan
    } un siguiente paso

applications-board-load-failed = No se pudo cargar tu seguimiento

applications-board-scroll-back = Mostrar columnas anteriores

applications-board-scroll-on = Mostrar columnas siguientes

applications-column-decided = Decididos

applications-column-closed = Rechazados o cerrados

applications-column-empty-saved = Guarda un { -role(num: "one") } de tu radar y aparecerá aquí.

applications-column-empty = Aún no hay nada aquí.

applications-column-count-of = { $count } de { $total }

applications-column-no-matches = Sin coincidencias.

applications-no-matches = Nada coincide con estos filtros.

applications-empty = Aún no hay nada en tu seguimiento

applications-empty-hint = Guarda un { -role(num: "one") } de tu radar para añadirlo aquí.

applications-empty-radar = Abrir Radar

applications-column-menu = Opciones de la columna { $column }

applications-column-hide = Ocultar columna

applications-column-hide-last = Siempre queda una columna en el tablero

applications-search-label = Buscar candidaturas por { -company(num: "one") } o título

applications-search-placeholder = Buscar { -company(num: "one") } o título…

applications-filter-highlight-instead = Resaltar en su lugar

applications-filter-reset = Restablecer todo

applications-filter-remove = Quitar el filtro { $filter }

applications-filter-menu = Filtrar candidaturas

applications-filter-quick = Filtros rápidos

applications-quick-overdue = Con retraso

applications-quick-due-week = Próximos 7 días

applications-quick-needs-next = Necesita un siguiente paso

applications-quick-quiet = Sin noticias

applications-quick-high-priority = Prioridad 4+

applications-filter-while = Al filtrar

applications-mode-only = Mostrar solo coincidencias

applications-mode-only-hint = Lo que no coincide se oculta.

applications-mode-highlight = Resaltar coincidencias

applications-mode-highlight-hint = Todo sigue visible y lo que no coincide se atenúa.

applications-columns = Columnas

applications-columns-hidden = { $count ->
        [one] Columnas, { $count } oculta
        [many] Columnas, { $count } ocultas
       *[other] Columnas, { $count } ocultas
    }

applications-columns-show = Mostrar columnas

applications-columns-show-all = Mostrar todas las columnas

applications-card-actions = Mover o cambiar { $title }

applications-card-due-interview = { $offset ->
        [0] Entrevista hoy
        [1] Entrevista mañana
       *[other] Entrevista el { $date }
    }

applications-card-due-step = { $offset ->
        [0] Vence hoy
        [1] Vence mañana
       *[other] Vence el { $date }
    }

applications-card-overdue = { $days ->
        [one] { $days } día de retraso
        [many] { $days } de días de retraso
       *[other] { $days } días de retraso
    }

applications-card-posting-closed = Oferta cerrada

applications-card-comments = { $count ->
        [one] { $count } comentario
        [many] { $count } de comentarios
       *[other] { $count } comentarios
    }

applications-card-priority = Prioridad { $priority } de 5

applications-card-days-short = { $days } d

applications-card-days-in-stage = { $days ->
        [one] { $days } día en esta etapa
        [many] { $days } de días en esta etapa
       *[other] { $days } días en esta etapa
    }

applications-card-quiet = { $days ->
        [one] { $days } día en esta etapa
        [many] { $days } de días en esta etapa
       *[other] { $days } días en esta etapa
    }, sin noticias desde hace { $quiet ->
        [one] { $quiet } día
        [many] { $quiet } de días
       *[other] { $quiet } días
    }

applications-card-ended = { $ending } en la etapa { $stage }

applications-menu-label = Mover { $title }

applications-menu-move-to = Mover a

applications-menu-remove = Quitar del seguimiento

applications-moved = Se movió { $title } a { $stage }

applications-moved-hidden = Se movió { $title } a { $stage }. La columna { $column } está oculta.

applications-move-undo = Deshacer

applications-move-failed = No se pudo mover { $title }. Inténtalo de nuevo.

applications-undo-failed = No se pudo devolver { $title } a donde estaba. Inténtalo de nuevo.

applications-move-failed-interview-kept = No se pudo mover { $title }, pero su entrevista quedó guardada. Abre la candidatura para cambiarla o eliminarla.

applications-removed = Se quitó { $title } de tu seguimiento

applications-remove-failed = No se pudo quitar { $title }. Inténtalo de nuevo.

applications-interview-title = ¿Cuándo es la entrevista?

applications-interview-for = { $title } en { $company }

applications-interview-pick-day = Elige el día

applications-interview-when-timed = { $date } · { $time }

applications-interview-when-day = { $date } · aún sin hora

applications-interview-zone = Zona horaria: { $zone }

applications-interview-no-time = Aún sin hora

applications-interview-times = Horas

applications-interview-time-invalid = Escribe una hora como { $example }.

applications-interview-day-missing = Elige el día de la entrevista.

applications-interview-optional = Opcional

applications-interview-round-recruiter = Preselección

applications-interview-round-hiring-manager = Responsable de contratación

applications-interview-round-technical = Técnica

applications-interview-round-panel = Panel

applications-interview-round-final = Ronda final

applications-interview-round = Ronda

applications-interview-round-add = Añadir otra ronda

applications-interview-round-name = Nombre de la ronda

applications-interview-default-label = Entrevista

applications-interview-time = Hora

applications-interview-format = Formato

applications-interview-format-video = Videollamada

applications-interview-format-phone = Teléfono

applications-interview-format-onsite = Presencial

applications-interview-link = Enlace de la reunión

applications-interview-link-placeholder = Pega el enlace de la reunión

applications-interview-link-invalid = Pega el enlace completo, empezando por https://.

applications-interview-cancel = Cancelar

applications-interview-submit = Mover a { $stage }

applications-interview-add-title = Añadir entrevista

applications-interview-edit-title = Editar entrevista

applications-interview-edit-submit = Guardar entrevista

applications-interview-delete = Eliminar entrevista

applications-interview-outcome = Resultado

applications-interview-outcome-none = Aún no

applications-interview-outcome-passed = Superada

applications-interview-outcome-not-passed = No superada

applications-interview-outcome-cancelled = Cancelada

applications-interview-notes = Notas

applications-interview-failed = No se pudo guardar la entrevista. Inténtalo de nuevo.

applications-interview-delete-failed = No se pudo eliminar la entrevista. Inténtalo de nuevo.

applications-interview-delete-confirm = ¿Eliminar esta entrevista?

applications-tabs-label = Vistas del seguimiento

applications-list-head-next = Siguiente paso

applications-list-head-actions = Acciones

applications-list-clear = Nada pendiente de empezar

applications-list-clear-board = Ver en el Tablero los puestos en curso

applications-list-not-for-me = No es para mí · { $title }

applications-list-column-left = Mover a la izquierda

applications-list-column-right = Mover a la derecha

applications-list-columns-reset = Restablecer columnas

applications-upnext-overdue = Con retraso

applications-upnext-day = { $offset ->
        [0] Hoy
        [1] Mañana
       *[other] { $date }
    }

applications-upnext-interview = Entrevista: { $label }

applications-upnext-step = Siguiente paso: { $step }

applications-upnext-step-when = Antes del final del día

applications-upnext-empty = No hay nada pendiente. Fija un siguiente paso o añade una entrevista a una candidatura y aparecerá aquí.

applications-month-label = Calendario

applications-month-prev = Mes anterior

applications-month-next = Mes siguiente

applications-month-today = Hoy

applications-month-interviews = { $count ->
    [one] { $count } entrevista
    [many] { $count } de entrevistas
   *[other] { $count } entrevistas
}

applications-month-steps = { $count ->
    [one] { $count } siguiente paso
    [many] { $count } de siguientes pasos
   *[other] { $count } siguientes pasos
}

applications-month-day = { $date }: { $summary }

applications-month-legend-interview = Entrevista

applications-month-legend-step = Siguiente paso

applications-month-day-empty = No hay nada este día.

applications-month-failed = No se pudo cargar el calendario

applications-page-bar = Candidatura

applications-page-back = Seguimiento / { $view }

applications-page-back-board = Abrir el Tablero

applications-page-load-failed = No se pudo cargar esta candidatura

applications-page-place = { $index } de { $total }

applications-page-previous = Anterior en esta columna: { $title }

applications-page-next = Siguiente en esta columna: { $title }

applications-page-more = Más acciones

applications-page-more-label = Más acciones para esta candidatura

applications-page-copy-link = Copiar enlace

applications-page-withdraw = Retirar candidatura

applications-link-copied = Enlace copiado

applications-link-copy-failed = No se pudo copiar el enlace. Cópialo desde la barra de direcciones.

applications-stage-button = { $stage } · { $days }

applications-stage-menu-label = Cambiar la etapa de { $title }

applications-change-failed = No se pudo guardar ese cambio en { $title }. Inténtalo de nuevo.

applications-crossing-closed = { $days ->
    [0] La oferta cerró el mismo día que enviaste tu candidatura.
    [one] La oferta cerró { $days } día después de enviar tu candidatura.
    [many] La oferta cerró { $days } de días después de enviar tu candidatura.
   *[other] La oferta cerró { $days } días después de enviar tu candidatura.
}

applications-crossing-reopened = { $days ->
    [0] La oferta se republicó el mismo día que enviaste tu candidatura.
    [one] La oferta se republicó { $days } día después de enviar tu candidatura.
    [many] La oferta se republicó { $days } de días después de enviar tu candidatura.
   *[other] La oferta se republicó { $days } días después de enviar tu candidatura.
}

applications-crossing-pay = { $days ->
    [0] El rango publicado cambió el mismo día que enviaste tu candidatura.
    [one] El rango publicado cambió { $days } día después de enviar tu candidatura.
    [many] El rango publicado cambió { $days } de días después de enviar tu candidatura.
   *[other] El rango publicado cambió { $days } días después de enviar tu candidatura.
}

applications-crossing-dismiss = Descartar

applications-next-title = Lo siguiente

applications-next-interview-none = No tienes ninguna entrevista programada.

applications-next-interview-all-day = { $date }, todo el día

applications-next-interview-at = { $date }, { $time }

applications-next-interview-meta = { $when } · { $format }

applications-next-interview-join = Unirse

applications-next-interview-join-label = Unirse a { $label }

applications-next-interview-edit = Editar entrevista

applications-next-empty = Aún no hay un siguiente paso.

applications-next-set = Fijar siguiente paso

applications-next-edit = Editar paso

applications-next-done = Marcar como hecho

applications-next-prompt = ¿Cuál es el siguiente paso?

applications-next-due = Fecha límite (opcional)

applications-next-required = Escribe el siguiente paso o pulsa Cancelar.

applications-next-save = Guardar paso

applications-notes-title = Notas

applications-notes-add = Añadir notas

applications-notes-edit = Editar notas

applications-notes-empty = Aún no hay notas.

applications-notes-label = Notas

applications-notes-more = Mostrar todo

applications-notes-less = Mostrar menos

applications-notes-save = Guardar notas

applications-feed-title = Actividad

applications-feed-mode-label = Mostrar

applications-feed-mode-comments = Comentarios

applications-feed-mode-all = Toda la actividad

applications-feed-empty = Aún no hay comentarios ni cambios.

applications-feed-fold = { $count ->
    [one] { $count } actualización: { $changes }
    [many] { $count } de actualizaciones: { $changes }
   *[other] { $count } actualizaciones: { $changes }
}

applications-feed-added = Añadido a tu seguimiento

applications-feed-added-at = Añadido en la etapa { $stage }

applications-feed-moved = Movido a { $stage }

applications-feed-priority = Prioridad cambiada

applications-feed-notes = Notas editadas

applications-feed-next-step = Siguiente paso cambiado

applications-feed-updated = Actualizado

applications-feed-by-agent = por una app de asistente

applications-comment-label = Comentario

applications-comment-placeholder = Escribe lo que pasó

applications-comment-submit = Comentar

applications-comment-author-you = Tú

applications-comment-author-agent = App de asistente

applications-comment-edited = Editado

applications-comment-edit = Editar comentario

applications-comment-delete-label = Eliminar comentario

applications-comment-delete-confirm = ¿Eliminar este comentario?

applications-comment-delete = Eliminar

applications-comment-save = Guardar

applications-comment-failed = No se pudo guardar tu comentario. Inténtalo de nuevo.

applications-comment-delete-failed = No se pudo eliminar ese comentario. Inténtalo de nuevo.

applications-facts-application = Candidatura

applications-facts-posting = Oferta

applications-facts-interviews = Entrevistas

applications-fact-priority = Prioridad

applications-fact-days = En esta etapa

applications-fact-days-value = { $days ->
    [one] { $days } día
    [many] { $days } de días
   *[other] { $days } días
}

applications-fact-applied = Enviada

applications-fact-applied-not = Aún no

applications-fact-starred = Guardado

applications-fact-starred-yes = Sí

applications-fact-starred-no = No

applications-fact-last-activity = Última actividad

applications-fact-status = Estado

applications-fact-status-open = Abierta

applications-fact-status-closed = Cerrada

applications-fact-pay = Rango publicado

applications-fact-pay-none = No publicado

applications-fact-pay-changed = Cambiado

applications-fact-level = Nivel

applications-fact-location = Ubicación

applications-fact-location-more = y { $count } más

applications-fact-first-seen = Visto por primera vez

applications-fact-listed-for = Publicado durante

applications-read-posting = Ver la oferta

applications-interview-add = Añadir entrevista

applications-interview-edit-label = Editar { $label }

applications-posting-row = Seguimiento

applications-posting-stage = Etapa

applications-posting-since-today = Desde hoy

applications-posting-ended = Terminó

applications-posting-interview = Entrevista

applications-posting-next-step = Siguiente paso

applications-posting-open = Abrir la candidatura

applications-posting-due = Vence

applications-posting-due-day = { $offset ->
        [0] Hoy
        [1] Mañana
       *[other] { $date }
    }

applications-posting-history-title = Historial de seguimiento

applications-posting-history-interview = Entrevista: { $label }

applications-posting-history-today = Hoy

applications-posting-history-now = { $days ->
    [one] { $stage }, 1 día
    [many] { $stage }, { $days } de días
   *[other] { $stage }, { $days } días
}
