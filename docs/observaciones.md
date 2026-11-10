# Observaciones · Tool de multitracks y stems

Documento vivo con observaciones, limitaciones conocidas y pendientes que necesitan una persona del equipo.
Se actualiza a medida que aparecen. Última actualización: 2026-10-25.

## Pendientes que necesitan al equipo

| Tema | Qué hace falta | Por qué |
| --- | --- | --- |
| Prime (Loop Community) | Importar un Stage Pack real en Prime y anotar cómo reconoce los archivos | No hay documentación pública de nombres ni ruteo. Hasta entonces `--destination prime` da error a propósito |
| Voces de las cues en español | Escuchar `assets/cues/es` y confirmar que suenan naturales | La voz `es_MX/ald` es lenta y se aceleró bastante (length_scale 0,52 en la cuenta) sin que nadie la escuchara |
| Voz rioplatense propia | Grabar las 15 cues con una voz de la agencia | El brief pide cues en rioplatense. La única voz rioplatense de Piper (`es_AR/daniela`) tiene licencia CC BY-SA y una base sin licencia verificada |
| Canciones de prueba | Conseguir canciones de uso libre (CC0 o CC BY) con secciones anotadas | Hacen falta para medir la calidad real de la detección de secciones y del beat tracking |

## Prueba de la v1 con el equipo

La v1 corre en una VPS propia (compartida, con un techo de 2 núcleos y 5 GB para la tool). Cada tema se procesa de a uno. En la VPS la separación tarda ~1,5 s por segundo de audio (un tema de 4 minutos, unos 6 minutos), y el estudio descarga stems comprimidos de ~3 MB cada uno.

Estas pruebas necesitan oído de músico; se hacen con la v1 completa, no durante el desarrollo.

- Subir 3 o 4 temas reales de distintos géneros (rock, cumbia, folklore, trap) y anotar si el BPM, el tono y el compás son correctos.
- En el estudio: que los stems suenen juntos, que el click caiga en cada tiempo con el 1 acentuado, y que las cues habladas suenen un compás antes de cada sección.
- Revisar si las secciones detectadas tienen sentido y cuánto hay que corregir en el editor.
- Exportar un Stage Pack, importarlo en Playback, en Prime y en un DAW, y confirmar que todo arranca alineado.
- Escuchar las cues en español y decidir si alcanza la voz sintética o hace falta grabar la voz rioplatense.

## Limitaciones conocidas

### Stage Pack

- Si una sección arranca justo en el primer tiempo después del count-in, su cue coincide con el "uno" de la cuenta. Gana la cuenta y la cue de la sección no suena. Es una decisión de diseño que se puede revisar.
- "Dos" y "Cuatro" en español duran 393 ms. Entran en un tiempo hasta unos 150 BPM; más rápido se cortan con un fundido de 3 ms.
- `htdemucs_6s` no separa coros, así que el archivo `BGVs` de Playback no se genera.
- El pack no agrega cola al final: los archivos terminan donde termina la canción.

### Análisis

- `beat_this` no detecta 3/4 en clicks sintéticos. Falta probarlo con una grabación real en 3/4.
- La detección de secciones se hace sin modelos entrenados (ver abajo). Los cortes suelen salir bien, pero los nombres (verso, coro) van a errar seguido y se corrigen en el editor.
- La segmentación agrupa sobre ventanas de 4 compases y después ajusta cada corte hasta 2 compases. Ese ajuste se afinó con una canción sintética limpia (los 7 cortes salieron exactos); con canciones reales todavía no se midió.

### Backend

- Si la limpieza borra una canción mientras un trabajo suyo está corriendo, el registro de salida que escribe el trabajo al terminar puede volver a crear la carpeta de la canción. Queda como carpeta huérfana hasta la limpieza manual del worker.

### Separación

- La imagen Docker del worker (solo-CPU) pesa 2,9 GB y la de la API 694 MB, sin torch. Detalle en `infra/README.md`.
- En CPU con 2 núcleos, un tema de 4 minutos tarda: análisis 2:45, separación 15:21, pack 1:36 (separación ~3,8 s por segundo de audio). El pico de memoria del cgroup fue 2,9 GiB, que fija el límite de 3,5 GiB. En producción la separación es un trabajo asíncrono de unos 15 minutos por tema, con una sola tarea a la vez. Alcanza para que el equipo pruebe; para uso público la cola se haría larga y hace falta GPU.
- El primer análisis después de levantar el worker tarda unos 7 minutos porque baja los pesos de beat_this (~180 kB/s). Conviene pre-descargar los pesos al construir la imagen.
- El worker de Linux debe usar torch 2.6 o más nuevo. La versión 2.2.2 de desarrollo solo existe porque Intel macOS no tiene wheels más nuevas, y tiene una vulnerabilidad conocida (CVE-2025-32434).

## Licencias revisadas

| Componente | Licencia | Estado |
| --- | --- | --- |
| Voz `es_MX/ald` (Piper) y su dataset | Unlicense | En uso |
| Voz `en_US/ljspeech` (Piper) | Dominio público | En uso |
| Voz `es_AR/daniela` (Piper) | CC BY-SA 4.0, entrenada desde lessac (licencia sin verificar) | Descartada |
| SongFormer (secciones) | Depende de los pesos de MuQ, CC BY-NC 4.0 | Descartado |
| All-In-One / allin1 (secciones) | Código MIT; pesos sin licencia publicada, entrenados con Harmonix | En duda. Consultar a los autores antes de probarlo en el worker de Linux |
| madmom | Modelos CC BY-NC-SA | Descartado |
| librosa (segmentación de secciones) | ISC | En uso |

## Decisiones tomadas

- 2026-10-25: el Stage Pack recibe las secciones como entrada opcional (`sections.json`). Sin secciones, la guía solo trae la cuenta del count-in.
- 2026-10-25: cues con Piper (`es_MX/ald` y `en_US/ljspeech`) ahora; voz rioplatense propia más adelante. Cambiarla es solo reemplazar archivos y el `manifest.json`.
- 2026-10-25: detección de secciones con un pipeline propio sin pesos entrenados (segmentación de librosa más reglas para nombrar). Los nombres son sugerencias con nivel de confianza.

## Próximos pasos

1. **Cambio de tono y tempo con Rubber Band:** transponer y cambiar el tempo de los stems sin alterar el otro parámetro.
2. **Avisos menores de la revisión de UX:**
   - Si el navegador rechaza la notificación de "listo", el error no se muestra.
   - El resultado parcial puede quedar con un texto provisorio viejo.
3. **Exportar en el celular:** separar las opciones en "Básico" y "Avanzado" con valores recomendados, y evitar que la barra fija tape contenido.
4. **Funciones pendientes:**
   - Editor de grilla.
   - Audio a MIDI con basic-pitch.
   - Separar coros de la voz principal y quitar reverb, solo con modelos de licencia comercial.
   - Destino Prime: probar con una importación real (ver la tabla de pendientes del equipo).
5. **Detalles conocidos:**
   - En escritorio, el editor de secciones tapa el carril de Batería.
   - Hay que volver a subir los temas ya procesados para obtener acordes y tono alternativo.
