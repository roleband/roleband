## Errores. Clave: error- más el código que envía la API o el transporte
## (backend tracker/api/errors.py ErrorCode). Un error dice qué pasó y luego
## el siguiente paso, o next=none.

error-generic = No se pudo hacer. Inténtalo de nuevo.
error-offline = RoleBand no responde. Comprueba que RoleBand se está ejecutando e inténtalo de nuevo.
error-server = Algo salió mal. Inténtalo de nuevo.
error-invalid-input = No se pudo usar esa solicitud. Inténtalo de nuevo.

## Algo que se nombra ya no existe
error-job-not-found = Este puesto ya no existe.
error-company-not-found = No se encuentra esa empresa.
error-company-profile-not-found = No hay ningún perfil para esa empresa.
error-local-model-not-found = Ese modelo ya no está guardado.
error-cloud-model-not-found = Ese proveedor de IA ya no está guardado. Añade uno en Ajustes › IA.
error-notification-not-found = Esa notificación ya no existe.
error-link-not-found = Esas ofertas ya no están vinculadas.
error-suggestion-not-found = Esa sugerencia ya no existe.
error-recipe-not-found = Esa receta ya no existe.
error-rule-not-found = Esa exclusión ya no existe.
error-fit-band-not-found = No se encuentra ese grado de encaje.
error-schedule-not-found = Esa empresa aún no tiene programación. Inténtalo de nuevo cuando termine el escaneo.
error-page-not-found = Aquí no hay nada.

## Lo que se pidió no se puede hacer, y por qué
error-careers-page-refused = Ese sitio de empleo limita la recopilación automática, así que no se puede añadir.
error-careers-page-unreachable = Esa página no carga. Revisa el enlace o prueba con otro.
error-company-conflict = Esa empresa ya está en la lista.
error-company-refused = No se pudo añadir esa empresa. Revisa el enlace e inténtalo de nuevo.
error-consent-required = Para seguir esa empresa, primero responde a su aviso.
error-scope-refused = No se pudieron guardar tus respuestas. Inténtalo de nuevo.
error-schedule-refused = No se pudo mover ese escaneo. Inténtalo de nuevo.
error-scheduling-unavailable = El escaneo está en pausa o desactivado para { $companies }.
error-discovery-unsupported = { $company } no tiene escaneo rápido. Mueve su escaneo completo.
error-manual-scan-queued = Un escaneo iniciado con Escanear ahora sigue en cola. Inténtalo de nuevo cuando termine el escaneo.
error-switch-running = La clasificación ya se está actualizando. Inténtalo de nuevo cuando termine.
error-switch-not-started = El cambio está guardado. La clasificación se actualiza en el próximo escaneo.
error-no-switch-running = No hay ninguna actualización en curso.
error-switch-not-stopped = No se pudo detener la actualización y tu elección de modelo no ha cambiado. Inténtalo de nuevo.
error-price-key-refused = Tiingo rechazó esta clave, así que no se guardó. Revísala en tu cuenta de Tiingo e inténtalo de nuevo.
error-switch-not-managed = Esta actualización no se inició aquí, así que no se puede detener aquí.
error-server-not-managed = Este servidor de IA local no se puede iniciar ni detener desde aquí.
error-model-unreachable = No se pudo conectar con el modelo. Comprueba que se está ejecutando e inténtalo de nuevo.
error-local-models-off = Tu propio modelo está desactivado. Actívalo en Ajustes › IA.
error-no-local-model = Tu propio modelo no está configurado. Añade uno en Ajustes › IA.
error-model-profiles-unreadable = No se pudieron leer tus ajustes de modelos. No se cambió nada.
error-key-saved-for-another-address = La clave guardada es de la dirección anterior. Introduce la clave de esta.
error-link-to-itself = Una oferta no se puede vincular consigo misma.
error-already-linked = Estas ofertas ya están vinculadas.
error-verdict-decided = Ya tomaste una decisión sobre estas. Cámbialo en Historial.
error-pair-refused = Estas ofertas no se pueden vincular.
error-not-a-member = Esa oferta ya no está en este conjunto.
error-suggestion-decided = Ya respondiste a esa sugerencia.
error-last-world = Mantén al menos un ámbito en tu radar.
error-recipe-invalid = Esa receta tiene problemas. Corrígelos e inténtalo de nuevo.
error-recipe-conflict = Esa empresa ya se escanea de otra forma.
error-plugin-not-found = Ese plugin ya no está instalado.
error-ai-egress-off = El envío de ofertas a proveedores de IA está desactivado. Actívalo en Ajustes › IA.
error-usage-catalogue-changed = Lo que se comparte cambió mientras elegías. Inténtalo de nuevo.
error-plugin-not-runnable = Ese plugin solo se ejecuta cuando está aprobado y activado.
error-plugin-running = Ese plugin ya se está actualizando. Inténtalo de nuevo cuando termine.
error-plugin-approval-stale = Ese plugin cambió desde que lo revisaste, así que no está aprobado. Inténtalo de nuevo.
error-plugin-still-enabled = Los datos de un plugin solo se pueden eliminar mientras está desactivado.
error-plugin-confirm-mismatch = Lo que escribiste no coincide con el nombre mostrado. Inténtalo de nuevo.
error-plugin-estimates-moving = Las estimaciones aún se están actualizando para dejar fuera sus datos. Inténtalo de nuevo cuando termine.
error-field-answered-by-plugin = Un plugin aporta este dato mientras está activado, así que un valor que pongas aquí no se mostraría. Desactívalo en Ajustes › Plugins.
error-engine-locked = No se pudo volver a conectar. Abre tu Radar desde la app.

error-application-not-found = Ese puesto ya no está en tu seguimiento.

error-comment-not-found = Ese comentario ya no existe.

error-interview-not-found = Esa entrevista ya no existe.

error-comment-not-yours = Solo puedes cambiar tus propios comentarios.

error-application-under-way = Este puesto ya está en proceso, así que sigue guardado. Márcalo como Retirado.

error-scheduling-unavailable-unnamed = El escaneo está en pausa o desactivado para esta empresa.

error-try-again = Inténtalo de nuevo.
