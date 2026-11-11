## insights

## features/statistics/CompensationPanel.tsx
insights-compensation-panel-compensation = Compensación
insights-compensation-panel-no-open-roles-with-a = Aún no hay puestos abiertos con una estimación de compensación.
insights-compensation-panel-open-roles-now-coverage = { $with_comp } de { $total_open } puestos abiertos tienen una estimación ({ $pct }%)
insights-compensation-panel-estimated-total-compensation-is-imputed = Estimada a partir de la empresa, el nivel y la disciplina, no indicada por las empresas. Tómala como referencia, no como una oferta.
insights-compensation-panel-published-bands = Rangos publicados
insights-compensation-panel-what-employers-actually-print = Rangos publicados
insights-compensation-panel-bands-from-employers = { $bands } rangos · { $employers ->
    [one] { $employers } empleador
    [many] { $employers } de empleadores
   *[other] { $employers } empleadores
}
insights-compensation-panel-estimated-comp-distribution = Distribución de la compensación total estimada
insights-compensation-panel-median-comp-by-level = Mediana de la compensación total estimada por nivel
insights-compensation-panel-top-paying-companies = Empresas que más pagan
insights-compensation-panel-median-pay-by-discipline = Mediana de la compensación total estimada por disciplina
insights-compensation-panel-what-a-skill-adds-at = Compensación por habilidad, mismo nivel
insights-compensation-panel-roles-naming-the-skill-against = Puestos que mencionan la habilidad frente a todos los puestos del mismo nivel y disciplina. Muestra qué empresas la piden, no cuánto vale.
insights-compensation-panel-not-enough-priced-roles-per = Aún no hay suficientes puestos con estimación para cada habilidad.
insights-compensation-panel-roles = { $count ->
    [one] { $count } puesto
    [many] { $count } de puestos
   *[other] { $count } puestos
}
insights-compensation-panel-groups-of-roles-or-more = { $min_roles }+ puestos por barra
insights-compensation-panel-base-salary-quoted-from-the = Salario base tal como se publica, no una estimación. Cada línea es un rango publicado, sin importar cuántos puestos lo compartan.
insights-compensation-panel-how-compensation-is-estimated = Cómo se estima la compensación
insights-compensation-panel-coverage = Con estimación
insights-compensation-panel-middle-50 = 50% central
insights-compensation-panel-top-decile = 10% superior
insights-compensation-panel-range = Dispersión
insights-compensation-panel-about-published-salary-bands = Acerca de los rangos publicados
insights-compensation-panel-how-a-skill-s-pay = Cómo se mide la diferencia de compensación de una habilidad
insights-compensation-panel-median = { $roles } · mediana { $p50 }

## features/statistics/Demand.tsx
insights-demand-open-roles-by-company = Puestos abiertos por empresa
insights-demand-each-role-counts-once-however = Cada puesto cuenta una vez, aunque se publique en varios lugares. Nuevos y cerrados cuentan los últimos 2 días.
insights-demand-no-open-roles-at-these = No hay puestos abiertos en estas empresas.
insights-demand-more-hold = { $share ->
    [none] { $companies } más tienen { $roles }.
   *[known] { $companies } más tienen { $roles } ({ $percent }% de estos puestos).
}
insights-demand-show-all = Mostrar todas ({ $company })
insights-demand-open-roles-by-region = Puestos abiertos por región
insights-demand-a-role-open-in-several = Un puesto abierto en varias regiones cuenta en cada una. Uno que solo indica una región, como Remoto Europa, cuenta una vez para esa región y nunca en sus países. Remoto ANZ cuenta en Australia y Nueva Zelanda.
insights-demand-no-open-roles-yet = Aún no hay puestos abiertos.
insights-demand-all-of = Todo { $region }
insights-demand-and-more-countries = { $more ->
    [one] y { $more } país más
    [many] y { $more } de países más
   *[other] y { $more } países más
}
insights-demand-name-no-place-we-can = { $role } no indican ningún lugar concreto, como Remoto sin más.
insights-demand-of = { $shown } de { $companies }
insights-demand-hiring-now-new-closed = { $company } contratando ahora · { $new } nuevos y { $closed } cerrados en los últimos 2 días
insights-demand-each-role-once = cada puesto una vez
insights-demand-with-an-open-role = con un puesto abierto
insights-demand-how-companies-are-counted = Cómo se cuentan las empresas
insights-demand-how-regions-are-counted = Cómo se cuentan las regiones
insights-demand-all-companies-hiring = Todas las empresas que contratan
insights-demand-find-a-company = Buscar una empresa

## features/statistics/DisclosurePanel.tsx
insights-disclosure-panel-of-open-roles-have-not = { $pending } de { $open } puestos abiertos aún no se han revisado en busca de un rango publicado, así que quedan fuera.
insights-disclosure-panel-pay-transparency = Transparencia salarial
insights-disclosure-panel-who-states-pay = Quién publica un rango
insights-disclosure-panel-the-share-of-open-roles = La proporción de puestos abiertos revisados que publican un rango. Cuenta cualquier rango: salario base, compensación total o sin indicar.
insights-disclosure-panel-of-checked-roles-state-pay = { $rate } de { $checked } puestos revisados publican un rango
insights-disclosure-panel-no-open-roles-have-been = Aún no se ha revisado ningún puesto abierto en busca de un rango publicado.
insights-disclosure-panel-how-the-disclosure-rate-is = Cómo se mide la transparencia salarial
insights-disclosure-panel-disclosure-breakdown = Desglose de transparencia salarial
insights-disclosure-panel-share-of-open-roles-stating = { $group ->
    [company] Proporción de puestos abiertos que publican un rango, por empresa
   *[level] Proporción de puestos abiertos que publican un rango, por nivel
}

## features/statistics/OverviewPanel.tsx
insights-overview-panel-most-named-skills = Habilidades más mencionadas
insights-overview-panel-what-is-pulling-the-market = Habilidades más buscadas
insights-overview-panel-the-skills-open-roles-name = Habilidades ordenadas según cuántos puestos abiertos las mencionan.
insights-overview-panel-leads-roles = { $display } encabeza · { $job_count } puestos
insights-overview-panel-opened-closed = { $new_count } publicados · { $closed_count } cerrados
insights-overview-panel-about-the-demand-field = Acerca de este gráfico

## features/statistics/PayBands.tsx
insights-pay-bands-each-line-is-one-published = Cada línea es un rango publicado. El tramo resaltado es el rango mediano del nivel.
insights-pay-bands-any-employer = Cualquier empleador
insights-pay-bands-published-base-salary-bands-by = Rangos publicados de salario base por nivel
insights-pay-bands-bands-from-employers = { $bands ->
    [one] { $bands } rango
    [many] { $bands } de rangos
   *[other] { $bands } rangos
} · { $employers ->
    [one] { $employers } empleador
    [many] { $employers } de empleadores
   *[other] { $employers } empleadores
}
insights-pay-bands-employer-bands = { $published ->
    [none] Sin rango
   *[some] { $range } · { $bands } rangos
}

## features/statistics/SkillsView.tsx
insights-skills-view-a-narrowed-view-ranks-skills = Con filtros: ordenadas según cuánto mencionan estos puestos una habilidad frente al mercado. Sin filtros: según el número de puestos.
insights-skills-view-no-skills-extracted-for-this = Aún no hay habilidades para esta selección.
insights-skills-view-expected-of-the-role = Lo que se espera del puesto
insights-skills-view-process-leadership-and-collaboration-asks = Habilidades de procesos, liderazgo y colaboración que piden la mayoría de los puestos.
insights-skills-view-against-the-market = Frente al mercado
insights-skills-view-what-sets-these-roles-apart = Qué distingue a estos puestos
insights-skills-view-above-the-line-named-more = Sobre la línea: más mencionadas que en el mercado
insights-skills-view-pick-a-company-a-discipline = Elige una empresa o una disciplina para comparar sus puestos con el mercado.
insights-skills-view-skill = Habilidad
insights-skills-view-category = Categoría
insights-skills-view-share-of-roles = Proporción de puestos
insights-skills-view-lift = vs. mercado
insights-skills-view-lead-skill = { $view ->
    [narrowed] { $skill } distingue estos puestos
   *[market] { $skill } encabeza
}
insights-skills-view-of-roles-name-it = { $view ->
    [narrowed] { $share } de estos puestos la mencionan, frente a { $market_share } del mercado
   *[market] { $share } de los puestos la mencionan
}
insights-skills-view-how-skills-are-ranked = Cómo se ordenan las habilidades
insights-skills-view-roles = Puestos
insights-skills-view-naming-a-skill = que mencionan una habilidad
insights-skills-view-expected = Esperadas
insights-skills-view-any-company = Cualquier empresa
insights-skills-view-what-expected-of-the-role = Qué significa «Lo que se espera del puesto»
insights-skills-view-skills-order = { $view ->
    [narrowed] Habilidades, las más distintivas primero
   *[market] Habilidades, las más mencionadas primero
}
insights-skills-view-loading = Cargando las habilidades…
insights-skills-view-load-failed = No se pudieron cargar las habilidades

## features/statistics/StatisticsView.tsx
insights-statistics-view-window = Intervalo de tiempo
insights-statistics-view-all-time = Todo el periodo
insights-statistics-view-statistics-sections = Secciones de análisis
insights-statistics-view-discipline = Disciplina
insights-statistics-view-advanced-view = Vista avanzada
insights-statistics-view-advanced-warning-title = Quedas avisado
insights-statistics-view-advanced-warning-body = La vista avanzada es para quien lee las notas al pie por diversión: cuánto tiempo siguen abiertos los puestos, con qué frecuencia se publica el salario, niveles y acciones lado a lado, y las muestras pequeñas que hay detrás. Puedes volver cuando quieras.
insights-statistics-view-show-me-everything = Enséñamelo todo
insights-statistics-view-keep-it-simple = Mantenlo simple
insights-statistics-view-part-of-advanced-view = Esta pestaña es parte de la vista avanzada.
insights-statistics-view-show-advanced-view = Mostrar vista avanzada

## features/statistics/StockTrajectoryPanel.tsx
insights-stock-trajectory-panel-stock-trajectory = Trayectoria de las acciones
insights-stock-trajectory-panel-no-open-roles-at-public = Aún no hay puestos abiertos en empresas cotizadas con una estimación de compensación.
insights-stock-trajectory-panel-typical-package = { $equity ->
    [measured] Compensación total típica de empresa cotizada · acciones medidas
    [mixed] Compensación total típica de empresa cotizada · acciones medidas en parte
   *[estimated] Compensación total típica de empresa cotizada · acciones estimadas
}
insights-stock-trajectory-panel-stock-moves-re-price-equity = Solo las acciones se mueven con la cotización. La base es el rango de salario base publicado cuando el puesto tiene uno; si no, una estimación. El bono sale del anuncio, de datos salariales o de la regla de la empresa; si no, es una estimación. Es una referencia, no una oferta.
insights-stock-trajectory-panel-stock-price-change = Cambio en la cotización
insights-stock-trajectory-panel-reset-to-today = Volver a hoy
insights-stock-trajectory-panel-equity-shockwave = Impacto en las acciones
insights-stock-trajectory-panel-who-moves-when-the-stock = Quién se mueve cuando se mueve la cotización
insights-stock-trajectory-panel-public-companies = { $move ->
    [up] Empresas cotizadas · +{ $pct }%
   *[other] Empresas cotizadas · { $pct }%
}
insights-stock-trajectory-panel-sorted-by-equity-exposure-only = Ordenadas por peso de las acciones.
insights-stock-trajectory-panel-no-open-roles-at-public-yet = Aún no hay puestos abiertos en empresas cotizadas.
insights-stock-trajectory-panel-ticker = Símbolo
insights-stock-trajectory-panel-equity = Acciones
insights-stock-trajectory-panel-equity-share = Parte en acciones
insights-stock-trajectory-panel-today = Hoy
insights-stock-trajectory-panel-projected = Proyectado
insights-stock-trajectory-panel-change = Cambio
insights-stock-trajectory-panel-no-exposure = sin acciones
insights-stock-trajectory-panel-private-companies = Empresas privadas
insights-stock-trajectory-panel-pre-ipo-equity-is-illiquid = Las acciones de empresas privadas no tienen cotización diaria, así que este escenario no cambia su compensación total.
insights-stock-trajectory-panel-median-tc = Compensación total mediana
insights-stock-trajectory-panel-median-tc-full = Compensación total mediana
insights-stock-trajectory-panel-options = Opciones
insights-stock-trajectory-panel-no-equity = Sin acciones
insights-stock-trajectory-panel-cash-election = Efectivo o acciones
insights-stock-trajectory-panel-about-the-source-labels = De dónde sale cada cifra
insights-stock-trajectory-panel-part-source = { $source ->
    [posted] Publicado
    [company_rule] Regla de la empresa
    [measured] Medido
    [mixed] Mixto
   *[estimated] Estimado
}
insights-stock-trajectory-panel-part-source-explained = { $source ->
    [posted] De los rangos publicados de los puestos de esta empresa
    [company_rule] Cómo dice esta empresa que paga esta parte
    [measured] De datos salariales de esta empresa y nivel
    [mixed] Varía entre los puestos de esta empresa
   *[estimated] Estimado para este nivel
}
insights-stock-trajectory-panel-no-company-matches = Ninguna empresa coincide con «{ $query }».
insights-stock-trajectory-panel-base = Base
insights-stock-trajectory-panel-bonus = Bono
insights-stock-trajectory-panel-no-bonus = Sin bono
insights-stock-trajectory-panel-vests = Consolida { $schedule }
insights-stock-trajectory-panel-choice-companies = Efectivo o acciones, tú eliges
insights-stock-trajectory-panel-choice-explained = En estas empresas cada persona elige cuánto de su compensación total es en efectivo y cuánto en acciones, así que no se muestra un reparto y un cambio en la cotización no cambia nada aquí.
insights-stock-trajectory-panel-left-out = { $count ->
    [one] Fuera: { $count } { -role(num: "one") } sin reparto
    [many] Fuera: { $count } de { -role(num: "other") } sin reparto
   *[other] Fuera: { $count } { -role(num: "other") } sin reparto
}
insights-stock-trajectory-panel-why-left-out = Por qué quedan fuera estos puestos
insights-stock-trajectory-panel-left-out-reason = { $reason ->
    [not_us_pay] Fuera de Estados Unidos
    [level_unplaced] Nivel sin ubicar
    [base_only] Solo base, sin total
    [basis_unclear] Rango sin base indicada
    [hourly] Tarifa por hora
    [monthly] Tarifa mensual
    [period_unclear] Periodo poco claro
    [total_compensation] Publicado como compensación total
    [plugin_without_split] Plugin sin reparto
   *[plugin_not_covered] Plugin aún sin leer
}
insights-stock-trajectory-panel-projected-tc = { $projected } de compensación total proyectada
insights-stock-trajectory-panel-projected-tc-full = { $projected } de compensación total proyectada
insights-stock-trajectory-panel-equity-figure = El { $share } de la compensación total es en acciones
insights-stock-trajectory-panel-how-stock-trajectory-is-projected = Cómo se proyecta esta trayectoria
insights-stock-trajectory-panel-median-tc-tile = compensación total mediana
insights-stock-trajectory-panel-median-tc-tile-full = compensación total mediana
insights-stock-trajectory-panel-at-price-change = { $move ->
    [up] con +{ $pct }%
   *[other] con { $pct }%
}
insights-stock-trajectory-panel-vs-today = frente a hoy
insights-stock-trajectory-panel-of-tc-at-risk = de la CT (en riesgo)
insights-stock-trajectory-panel-of-tc-at-risk-full = de la compensación total (en riesgo)
insights-stock-trajectory-panel-stock-price-change-percent = Porcentaje de cambio en la cotización
insights-stock-trajectory-panel-how-to-read-equity-sensitivity = Cómo leer este gráfico
insights-stock-trajectory-panel-sensitivity-explained = { $move ->
    [flat] Con la cotización de hoy, cada barra es lo que una subida del 10% en las acciones añade a la compensación total típica. Mueve el control deslizante para ver un escenario.
   *[other] Muestra el cambio en dólares de la compensación total típica en este escenario.
}
insights-stock-trajectory-panel-scenario = { $move ->
    [flat] Por cada 10% de cambio en la cotización · ajústalo arriba para ver un escenario
    [up] Escenario de +{ $pct }%
   *[down] Escenario de { $pct }%
}
insights-stock-trajectory-panel-about-public-company-projections = Sobre proyecciones de empresas cotizadas
insights-stock-trajectory-panel-paid-in-cash-unaffected-by = Se paga en efectivo: no depende de la cotización
insights-stock-trajectory-panel-why-private-companies-do-not = Por qué las privadas no se mueven
insights-stock-trajectory-panel-loading = Cargando la trayectoria de las acciones…
insights-stock-trajectory-panel-load-failed = No se pudo cargar la trayectoria de las acciones
insights-stock-trajectory-panel-rsus = RSU

## features/statistics/OfferCalculator.tsx
insights-offer-entered = Introducido por ti, { $date }
insights-offer-started-from = { $kind ->
    [role] Rellenado a partir de { $title } en { $company }.
   *[company] Rellenado a partir del puesto mediano en { $company }.
}
insights-offer-undo = Deshacer
insights-offer-clear = Borrar oferta
insights-offer-cleared = Oferta borrada.
insights-offer-another-company = Otra empresa
insights-offer-chip-another = { $listed ->
    [yes] Otra empresa, cotizada
   *[no] Otra empresa, privada
}
insights-offer-listed-label = Cotizada o privada
insights-offer-listed = { $listed ->
    [yes] Cotizada
   *[no] Privada
}
insights-offer-bonus-rule = { $rule ->
    [none] Esta empresa no paga bono anual.
   *[pct_of_base] Esta empresa fija el bono como parte del base según el nivel. Introduce el de tu oferta.
}
insights-offer-equity-type = Tipo de acciones
insights-offer-grant-unit = Concesión expresada en
insights-offer-grant-unit-option = { $unit ->
    [dollars] Dólares
   *[shares] Acciones
}
insights-offer-price-needs-key = Escribe el precio de hoy, o añade una clave en { $link } para rellenarlo con el último cierre.
insights-offer-price-settings = Ajustes › Plugins › Precios de la acción
insights-offer-price-no-close = Aún no hay cierre guardado para { $ticker }. Escribe el precio de hoy.
insights-offer-vesting-year = Año { $year }, porcentaje que consolida
insights-offer-vesting-sum = Estos cuatro años consolidan el { $pct }% de la concesión.
insights-offer-sign-on = Prima inicial, año { $year }
insights-offer-sign-on-bridges = Esta empresa paga una prima inicial en los dos primeros años para compensar su consolidación.
insights-offer-private = Las acciones de una empresa privada no se pueden vender hasta que la empresa salga a bolsa o haga una venta autorizada.
insights-offer-valuation-unit = Valoración expresada como
insights-offer-valuation-unit-option = { $unit ->
    [per_share] Precio por acción
   *[company] Valoración de la empresa
}
insights-offer-valuation-grant = { $unit ->
    [per_share] Precio en la concesión
   *[company] Valoración en la concesión
}
insights-offer-valuation-test = { $unit ->
    [per_share] Precio a probar
   *[company] Valoración a probar
}
insights-offer-share-count = Acciones en circulación
insights-offer-valuation-hint = Introduce la valoración de tu oferta y la que quieres probar, como la última ronda o tu propia expectativa.
insights-offer-valuation-none = Sin una valoración, las acciones se muestran a la valoración con la que se concedieron.
insights-offer-move = { $listed ->
    [yes] Cambio en la cotización
   *[no] Cambio en la valoración
}
insights-offer-move-aria = { $listed ->
    [yes] Cambio en la cotización para tu oferta, porcentaje
   *[no] Cambio en la valoración para tu oferta, porcentaje
}
insights-offer-missing = { $missing ->
    [price] Introduce el precio de la acción de hoy para valorar las acciones.
    [strike] Introduce el precio de ejercicio para valorar las opciones.
    [valuation] Introduce una valoración para valorar las acciones.
   *[share_count] Introduce las acciones en circulación para convertir la valoración en un precio por acción.
}
insights-offer-year = Año
insights-offer-year-n = Año { $year }
insights-offer-four-years = Cuatro años
insights-offer-sign-on-column = Prima inicial
insights-offer-tc-today = CT hoy
insights-offer-tc-today-full = Compensación total al precio de hoy
insights-offer-tc-moved = { $move ->
    [up] CT con +{ $pct }%
   *[down] CT con { $pct }%
}
insights-offer-tc-moved-full = { $move ->
    [up] Compensación total tras una subida del { $pct }%
   *[down] Compensación total tras una bajada del { $pct }%
}
insights-offer-drop = Menos que el año { $year }
insights-offer-start = Empezar desde aquí
insights-offer-start-aria = Empezar una oferta desde { $company }
insights-offer-column = Tu oferta
insights-offer-at-your-valuation = Con tu valoración
insights-offer-at-your-valuation-moved = { $move ->
    [up] Con tu valoración, +{ $pct }%
   *[down] Con tu valoración, { $pct }%
}
insights-offer-at-your-valuation-full = Acciones a la valoración que introdujiste el { $date }
insights-offer-start-title = Lo que paga una oferta, año por año
insights-offer-start-intro = Unas pocas preguntas cortas, de una en una. Lo que introduces se queda en este ordenador.
insights-offer-loading = Cargando tu oferta
insights-offer-load-failed = Tu oferta no se ha cargado.
insights-offer-save-failed = Tu última respuesta no se ha guardado. Respóndela otra vez para conservarla.
insights-offer-progress = Pregunta { $n } de { $total }
insights-offer-q-company = ¿Qué empresa te ha hecho la oferta?
insights-offer-q-company-hint = Sus reglas habituales de acciones y bono se rellenan solas.
insights-offer-pick-company = Elige una empresa
insights-offer-all-companies = Todas las empresas
insights-offer-q-base = ¿Cuál es el salario base?
insights-offer-q-base-hint = El salario anual de tu carta de oferta.
insights-offer-per-year = al año
insights-offer-per-share = por acción
insights-offer-q-stock = { $vehicle ->
    [options] ¿Cuántas opciones incluye la oferta?
    [cash] ¿Cuánto elegiste cobrar en acciones?
   *[rsu] ¿Cuántas acciones incluye la oferta?
}
insights-offer-q-stock-hint = { $vehicle ->
    [options] { $company } concede opciones sobre acciones. Introduce el número de tu carta de oferta.
    [cash] { $company } te deja repartir tu pago entre efectivo y acciones. Introduce la parte en acciones de los cuatro años: un cambio solo afecta a esa parte.
    [another] Introduce la concesión total de tu carta de oferta, en dólares o en acciones.
   *[rsu] { $company } concede RSU. Introduce la concesión total de tu carta de oferta.
}
insights-offer-no-stock = { $vehicle ->
    [options] Sin opciones
    [cash] Todo en efectivo
   *[rsu] Sin acciones
}
insights-offer-q-strike = ¿Cuál es el precio de ejercicio?
insights-offer-q-strike-hint = El precio por acción que pagas para comprar cada opción.
insights-offer-q-price = { $quote ->
    [yes] ¿Usar el último cierre de { $company }?
   *[no] ¿Cuál es la cotización de hoy?
}
insights-offer-q-price-quote = { $price } por acción al cierre del { $date }.
insights-offer-use-price = Usar { $price }
insights-offer-own-price = Introducir un precio
insights-offer-q-valuation = ¿Cuánto vale { $company }?
insights-offer-dont-know = No lo sé
insights-offer-q-vesting-stated = ¿Tu concesión consolida { $schedule }?
insights-offer-q-vesting-stated-hint = Es el calendario que { $company } suele indicar, como porcentaje de la concesión en cada año.
insights-offer-q-vesting = ¿Cómo consolida la concesión?
insights-offer-q-vesting-hint = { $named ->
    [yes] { $company } no lo indica. La mayoría de las concesiones consolidan por igual en cuatro años.
   *[no] La mayoría de las concesiones consolidan por igual en cuatro años.
}
insights-offer-percent-of-grant = Porcentaje de la concesión en cada año.
insights-offer-vesting-yes = Sí, igual
insights-offer-vesting-differs = La mía cambia
insights-offer-vesting-other = Otro
insights-offer-vesting-even = uniforme
insights-offer-vesting-too-much = Los años suman el { $pct }%. Mantenlo en el 100% o menos.
insights-offer-q-bonus = ¿Hay un bono anual objetivo?
insights-offer-q-bonus-hint = Una parte del base, tal como la indica tu carta de oferta.
insights-offer-bonus-choice = { $pct ->
    [0] Sin bono
    [one] { $pct }%
    [many] { $pct }%
   *[other] { $pct }%
}
insights-offer-bonus-other = Otro bono objetivo, porcentaje del base
insights-offer-q-sign-on = ¿Hay prima inicial?
insights-offer-q-sign-on-hint = Un pago único por incorporarte, a veces repartido en dos años.
insights-offer-sign-on-yes = Sí
insights-offer-sign-on-no = Sin prima
insights-offer-need = { $what ->
    [company] Elige una empresa.
    [base] Introduce el salario base anual.
    [stock] Introduce la cantidad o elige el botón de al lado.
    [strike] Introduce el precio de ejercicio.
    [price] Introduce la cotización de hoy.
    [valuation] Introduce el valor en la concesión o elige No lo sé.
    [vesting] Introduce el porcentaje que consolida en al menos un año.
    [bonus] Elige un bono objetivo.
   *[sign_on] Introduce al menos un importe de prima inicial.
}
insights-offer-next = Siguiente
insights-offer-done = Hecho
insights-offer-back = Atrás
insights-offer-cancel = Cancelar
insights-offer-later = Terminar después
insights-offer-finished-title = { $named ->
    [yes] Tu oferta de { $company }, año por año
   *[no] Tu oferta, año por año
}
insights-offer-unfinished = { $answered } de { $total } respondidas
insights-offer-continue = Continuar
insights-offer-typical = Son cifras típicas. Cámbialas por las tuyas para ver tu propia oferta.
insights-offer-swap = Usar mis cifras
insights-offer-tag = { $tag ->
    [typical] Típico
    [rule] Regla de la empresa
    [employer] Indicado por la empresa
    [estimated] Estimado
    [assumed] Supuesto
   *[quote] Último cierre
}
insights-offer-chip-edit = Cambiar { $answer }
insights-offer-chip-base = Base { $amount }
insights-offer-chip-stock = { $kind ->
    [none] Sin acciones
    [cash] { $amount } en acciones
    [options] { $count } opciones
    [shares] { $count } acciones
   *[dollars] { $amount } en acciones
}
insights-offer-chip-strike = Ejercicio { $amount }
insights-offer-chip-price = { $kind ->
    [none] Sin precio por acción
   *[some] { $amount } por acción
}
insights-offer-chip-valuation = { $kind ->
    [none] Al valor concedido
    [per_share] De { $from } a { $to } por acción
   *[company] Valorada de { $from } a { $to }
}
insights-offer-chip-vesting = Consolida { $schedule }
insights-offer-chip-bonus = { $pct ->
    [0] Sin bono
    [one] Bono del { $pct }%
    [many] Bono del { $pct }%
   *[other] Bono del { $pct }%
}
insights-offer-chip-sign-on = { $kind ->
    [none] Sin prima inicial
   *[some] Prima { $first } + { $second }
}
insights-offer-chart = Compensación total por año
insights-offer-vs-today = { $sign ->
    [up] { $amount } más que al precio de hoy
    [down] { $amount } menos que al precio de hoy
   *[same] Al precio de hoy
}
insights-offer-show-table = Ver la tabla

## features/statistics/VelocityPanel.tsx
insights-velocity-panel-companies = Empresas · { $window }
insights-velocity-panel-open = Abiertos
insights-velocity-panel-time-posted = Tiempo publicado
insights-velocity-panel-from-the-first-scan-that = Días desde la primera publicación hasta el cierre. Requiere 5 puestos cerrados con inicio conocido.
insights-velocity-panel-age-of-open-roles = Antigüedad de los puestos abiertos
insights-velocity-panel-how-long-postings-stay-up = Cuánto tiempo siguen publicadas las ofertas
insights-velocity-panel-this-builds-up-as-roles = { $closed_sample ->
    [one] Se completa cuando 5 puestos cerrados tengan un inicio conocido. De momento, 1.
    [many] Se completa cuando 5 puestos cerrados tengan un inicio conocido. De momento, { $closed_sample }.
   *[other] Se completa cuando 5 puestos cerrados tengan un inicio conocido. De momento, { $closed_sample }.
}
insights-velocity-panel-median-age = Antigüedad mediana: { $median_days_open }
insights-velocity-panel-median-time-posted = Tiempo publicado mediano: { $median_observed_listing_duration_days }
insights-velocity-panel-more-already-listed-when-found = { $already_listed } encontrados ya publicados
insights-velocity-panel-what-time-posted-measures = Qué mide «Tiempo publicado»
insights-velocity-panel-age-unknown = Antigüedad desconocida: { $count }
insights-velocity-panel-time-posted-unknown = Tiempo publicado desconocido: { $count }
insights-velocity-panel-what-unknown-means = Qué significa «desconocido»
insights-velocity-panel-why-a-start-is-unknown = Encontrada en el primer escaneo de una empresa, sin fecha del empleador.
insights-velocity-panel-counted-from-first-listed = Contado desde la primera publicación de cada puesto.
insights-velocity-panel-what-already-listed-means = Qué significa «encontrados ya publicados»
insights-velocity-panel-why-already-listed = Ya publicados al verlos por primera vez: en el primer escaneo de una empresa, o con una fecha anterior del empleador.

## features/statistics/ageCopy.ts
insights-age-copy-listed-today = Publicado hoy
insights-age-copy-listed-for = Publicado desde hace { $days }

## features/statistics/charts/StatisticsCharts.tsx
insights-statistics-charts-skill-open-roles = { $job_count } puestos abiertos · { $category }
insights-statistics-charts-market-demand-field = Habilidades más buscadas
insights-statistics-charts-company-open-roles = { $open ->
    [one] { $open } puesto abierto
    [many] { $open } de puestos abiertos
   *[other] { $open } puestos abiertos
}
insights-statistics-charts-new-closed = { $new_roles } · { $closed_roles } en los últimos 2 días
insights-statistics-charts-new-count = +{ $fresh } nuevos
insights-statistics-charts-closed-count = −{ $closed } cerrados
insights-statistics-charts-open-roles-by-company = Puestos abiertos por empresa
insights-statistics-charts-open-new-closed = { $label }: { $open } abiertos, { $fresh } nuevos, { $closed } cerrados
insights-statistics-charts-closed = Cerrados ←
insights-statistics-charts-equity-change = { $direction ->
    [flat] Cambio de $0
    [down] −{ $amount }
   *[up] +{ $amount }
}
insights-statistics-charts-no-change = Sin cambios
insights-statistics-charts-equity-shockwave-by-company = Impacto en las acciones por empresa
insights-statistics-charts-share-against-market = { $share }% de estos puestos · { $market_share }% del mercado
insights-statistics-charts-lift-the-market-s-rate = ×{ $lift } la tasa del mercado
insights-statistics-charts-share-of-these-roles = proporción de estos puestos →
insights-statistics-charts-the-market-s-rate = × la tasa del mercado →
insights-statistics-charts-what-sets-these-roles-apart = Qué distingue a estos puestos
insights-statistics-charts-of-these-roles-the-market = { $skill }: { $share }% de estos puestos, ×{ $lift } el mercado

## features/statistics/charts/compBands.ts
insights-comp-bands-level-summary = { $label }: { $bands } { $bands ->
        [one] rango
        [many] rangos
       *[other] rangos
    } de { $employers } { $employers ->
        [one] empleador
        [many] empleadores
       *[other] empleadores
    }, mediana de { $low } a { $high }.
insights-comp-bands-1-more-role-states-a = 1 puesto más publica un rango pero nunca dice si incluye bonus o acciones, así que no se muestra.
insights-comp-bands-more-roles-state-a-range = { $unclear } puestos más publican un rango pero nunca dicen si incluye bonus o acciones, así que no se muestran.
insights-comp-bands-1-more-role-states-base = 1 puesto más publica el salario base en otra moneda o por hora o por mes, así que no está en esta escala anual en dólares.
insights-comp-bands-more-roles-state-base-pay = { $elsewhere } puestos más publican el salario base en otra moneda o por hora o por mes, así que no están en esta escala anual en dólares.

## features/statistics/charts/disclosure.ts
insights-disclosure-unclassified = Nivel desconocido
insights-disclosure-no-open-roles-have-been = Aún no se ha revisado ningún puesto abierto en busca de un rango publicado.
insights-disclosure-share-of-checked-open-roles = Proporción de puestos abiertos revisados que publican un rango. { $rates }.{ $unrated ->
        [0] { "" }
        [one] { " " }Hay { $unrated } grupo más sin ningún puesto revisado aún, así que no se puede indicar su porcentaje.
        [many] { " " }Hay { $unrated } de grupos más sin ningún puesto revisado aún, así que no se puede indicar su porcentaje.
       *[other] { " " }Hay { $unrated } grupos más sin ningún puesto revisado aún, así que no se puede indicar su porcentaje.
    }
insights-disclosure-of-roles = { $label }: { $rate }, { $disclosed } de { $checked } puestos
insights-disclosure-rate-states-pay = { $rate } publican un rango
insights-disclosure-of-checked-open-roles = { $disclosed } de { $checked } puestos abiertos revisados

## features/statistics/charts/StatisticsCharts.tsx (by hand)

## features/statistics/CompensationPanel.tsx
insights-compensation-panel-median-pay = { $p50 } de mediana
insights-compensation-panel-priced-roles = { $with_comp } puestos
insights-compensation-panel-loading = Cargando la compensación…
insights-compensation-panel-load-failed = No se pudo cargar la compensación
insights-compensation-panel-min-max = mín–máx

## features/statistics/Demand.tsx
insights-demand-open = { $role } abiertos
insights-demand-loading = Cargando la actividad de contratación…
insights-demand-load-failed = No se pudo cargar la actividad de contratación
insights-demand-last-2-days = últimos 2 días

## features/statistics/OverviewPanel.tsx
insights-overview-panel-companies = { $companies } empresas
insights-overview-panel-loading = Cargando el resumen…
insights-overview-panel-load-failed = No se pudo cargar el resumen

## features/statistics/VelocityPanel.tsx
insights-velocity-panel-opened-count = { $opened } publicados
insights-velocity-panel-open-count = { $open_total } abiertos
insights-velocity-panel-loading = Cargando el ritmo de contratación…
insights-velocity-panel-load-failed = No se pudo cargar el ritmo de contratación

## features/statistics/charts/compBands.ts
insights-comp-bands-to = de { $low } a { $high }
insights-comp-bands-employer-at-level = { $published ->
    [none] { $summary } { $employer } no publica ningún rango en este nivel.
   *[some] { $summary } { $employer }: { $ranges }.
}

## features/statistics/charts/disclosure.ts

## Los dos lados de la división por empresas de Análisis
insights-your-companies = Tus empresas
insights-other-companies = Otras empresas
insights-period-days = { $days } d

## Palabras que comparten varios paneles de Insights
insights-common-companies = Empresas
insights-common-company = Empresa
insights-common-open-roles = Puestos abiertos
insights-common-open-roles-unit = puestos abiertos
insights-common-new = Nuevos
insights-common-opened = Publicados
insights-common-closed = Cerrados
insights-common-market = Mercado
insights-common-by-level = Por nivel
insights-common-by-company = Por empresa
insights-common-all-companies = Todas las empresas
insights-common-last-days-or-all-time = { $period ->
    [all] todo el periodo
   *[days] últimos { $days } d
}
insights-common-since-date = desde el { $date } ({ $days ->
        [one] { $days } día
        [many] { $days } días
       *[other] { $days } días
    })

## Categorías de habilidades
insights-skill-language = Lenguaje
insights-skill-framework = Framework
insights-skill-cloud = Nube
insights-skill-data = Datos
insights-skill-ml-ai = ML / IA
insights-skill-infra = Infraestructura
insights-skill-security = Seguridad
insights-skill-process = Procesos
insights-skill-leadership = Liderazgo
insights-skill-collaboration = Colaboración
insights-skill-industry = Sector

## Nombres de estadísticas: serie de cohorte y franjas de antigüedad
insights-aging-from-0-days = < 1 semana
insights-aging-from-7-days = 1–2 semanas
insights-aging-from-14-days = 2–4 semanas
insights-aging-from-30-days = 1–2 meses
insights-aging-from-60-days = 2–3 meses
insights-aging-from-90-days = 3 meses o más

## El resumen de una línea de la vista general
insights-brief-open = { $open } puestos abiertos en { $companies } empresas.
insights-brief-opened = { $period ->
    [since] { $opened } publicados, { $closed } cerrados desde el { $date }.
    [all] { $opened } publicados, { $closed } cerrados, en todo el periodo.
   *[days] { $opened } publicados en { $days } d, { $closed } cerrados.
}
insights-brief-top-skill = Habilidad principal: { $skill } ({ $count } puestos).
insights-compensation-panel-spread = p25–p75: { $low }–{ $high } · { $roles }
insights-compensation-panel-estimated-base-by-level = Salario base estimado por nivel
insights-compensation-panel-base-only = Solo base
insights-compensation-panel-base-only-lead =
    { $count ->
        [one] { $count } puesto más solo tiene un salario base estimado, así que no está en las cifras de arriba.
        [many] { $count } de puestos más solo tienen un salario base estimado, así que no están en las cifras de arriba.
       *[other] { $count } puestos más solo tienen un salario base estimado, así que no están en las cifras de arriba.
    }

insights-levels-loading = Cargando la guía de niveles…

insights-levels-load-failed = No se pudo cargar la guía de niveles

insights-levels-figure = Cómo nombra cada empresa sus niveles

insights-levels-figure-translating = { $company } { $code } es { $level }

insights-levels-line = Elige cualquier nivel para ver cómo lo llama cada empresa con guía de niveles.

insights-levels-line-translating = La columna resaltada es el mismo nivel en todas las demás empresas.

insights-levels-kpi-guided = Con guía de niveles

insights-levels-kpi-flat = Títulos sin nivel

insights-levels-kpi-flat-sub = Nivel nunca indicado

insights-levels-kpi-skipped = Sin nivel { $level }

insights-levels-kpi-skipped-sub = Se usa el más cercano

insights-levels-search = Empresa o nivel

insights-levels-search-example = Google o ICT4

insights-levels-sector = Sector

insights-levels-your-level = { $level }, tu nivel

insights-levels-your-aim = { $level }, al que aspiras

insights-levels-translating-column = { $level }, traduciendo

insights-levels-translate-from = Traducir desde { $company } { $code }

insights-levels-translating = Traduciendo { $company } { $code } ({ $level }) a todas las empresas

insights-levels-clear = Borrar

insights-levels-ambiguous = { $count ->
    [one] { $code } es un nivel en { $count } empresa. Elígelo para traducir desde él.
    [many] { $code } es un nivel distinto en { $count } de empresas. Elige desde qué empresa traducir.
   *[other] { $code } es un nivel distinto en { $count } empresas. Elige desde qué empresa traducir.
}

insights-levels-engineering = Niveles de ingeniería

insights-levels-engineering-title = Esta empresa solo indica niveles de ingeniería

insights-levels-flat = Aquí los títulos no indican nivel

insights-levels-flat-title = Los títulos de puesto de esta empresa no indican ningún nivel más allá de estos

insights-levels-skipped = { $company } no tiene nivel { $level }

insights-levels-skipped-closest = Sin nivel { $level }. Más cercano: { $code }

insights-levels-no-guide = Aún no hay guía de niveles para { $company }.

insights-levels-same-as = Comparte los niveles de { $company }.

insights-levels-followed-without-guide = { $count ->
    [one] { $count } empresa que sigues aún no tiene guía de niveles.
    [many] { $count } de empresas que sigues aún no tienen guía de niveles.
   *[other] { $count } empresas que sigues aún no tienen guía de niveles.
}

insights-levels-empty = Ninguna empresa ni nivel coincide

insights-levels-reset = Restablecer todo
