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
- Antes de desplegar un cambio en el formato de los trabajos de la cola, hay que vaciar la cola `cpu`.

### Separación

- La imagen Docker del worker pesa 10,5 GB porque torch para Linux baja los paquetes de CUDA desde PyPI. Usar el índice solo-CPU de PyTorch la achicaría mucho; está anotado en `infra/README.md`. La imagen de la API pesa 694 MB y no incluye torch.

- En CPU (Mac Intel de desarrollo) `htdemucs_6s` tarda 0,70 s por segundo de audio. Para producción hace falta GPU.
- Dentro de Docker, con el worker limitado a 2 núcleos, la separación tardó 201 s para 32 s de audio (unos 6,3 s por segundo). Una canción de 4 minutos tardaría unos 25 minutos: confirma que la separación en CPU no sirve para producción.
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

- 2026-10-26: repo privado en GitHub (`Agusschenfelt/funke_tools-multitrack`). Se abre cuando la tool esté online, momento en que la AGPL obliga a publicar el código. `main` apunta al commit inicial; el trabajo está en ramas `feat/*` apiladas.
- 2026-10-25: el Stage Pack recibe las secciones como entrada opcional (`sections.json`). Sin secciones, la guía solo trae la cuenta del count-in.
- 2026-10-25: cues con Piper (`es_MX/ald` y `en_US/ljspeech`) ahora; voz rioplatense propia más adelante. Cambiarla es solo reemplazar archivos y el `manifest.json`.
- 2026-10-25: detección de secciones con un pipeline propio sin pesos entrenados (segmentación de librosa más reglas para nombrar). Los nombres son sugerencias con nivel de confianza.
