# Brief · Tool de multitracks y stems

Oct 24, 2026 · @Agus

## Visión y alcance

Una herramienta web gratuita que agarra cualquier canción y devuelve todo lo que un músico necesita para tocarla en vivo o remixarla, en español y sin pagar por tema. La referencia es AudioForges (Stage Pack, Stem Splitter, Key Finder, Audio to MIDI), con la meta de igualar todas sus herramientas y sumar las que le sirven a un productor.

Dos públicos comparten el mismo motor de análisis.

- **Bandas y músicos en vivo** que necesitan multitracks con click, cues habladas y split track listos para Playback, Prime o Ableton
- **Productores que remixan** (por ejemplo llevar temas a techno) que necesitan acapellas limpias, stems, BPM, tonalidad, loops y MIDI

Principios del producto

- Gratis para el usuario y sin marca de agua. El costo de GPU se financia aparte
- Se escucha y se corrige antes de descargar, con mixer y editores en el navegador
- Español primero, con cues en español rioplatense y etiquetas que entiendan géneros latinos
- Todo el stack es open source y las licencias se revisan modelo por modelo
- Ningún archivo se guarda más de 24 horas

## Herramientas

Son 30 herramientas en 8 módulos, todas alimentadas por un mismo análisis de la canción que se hace una sola vez.

| Módulo | Herramienta | Qué entrega |
| --- | --- | --- |
| Ingesta | Subir archivo | MP3, WAV, FLAC, M4A, AIFF, OGG y video, hasta 10 minutos |
| Ingesta | Link | YouTube y SoundCloud (ver límites legales) |
| Ingesta | Setlist | Hasta 20 canciones en un solo lote y un ZIP al final |
| Separación | Removedor de voz | Voz e instrumental |
| Separación | Stems | 4 (voz, batería, bajo, otros) o 6 (más guitarra y piano) |
| Separación | Voz principal y coros | Lead, backing e instrumental por separado |
| Separación | Batería por piezas | Bombo, redoblante, toms, hi-hat y platos |
| Separación | Limpiar voz | Quita reverb y eco de la acapella |
| Análisis | Tempo y grilla | BPM, beats, primer tiempo de cada compás y compás (4/4, 3/4, 6/8) |
| Análisis | Tonalidad | Tono, modo, código Camelot y tonos compatibles |
| Análisis | Secciones | Intro, verso, pre-coro, coro, puente, solo, break, final |
| Análisis | Acordes | Progresión sincronizada con la grilla |
| Análisis | Letra | Transcripción con tiempos por palabra |
| Análisis | Volumen | LUFS integrado y pico real |
| Transformación | Cambio de tono | Todos los stems transpuestos juntos, de -6 a +6 semitonos |
| Transformación | Cambio de tempo | Todos los stems estirados juntos sin cambiar el tono |
| Transformación | Warp a BPM fijo | La canción llevada a un tempo objetivo (por ejemplo 128) con grilla recta |
| Transformación | Match de tonalidad | Transponer un tema para que combine con otro |
| Transcripción | Audio a MIDI | Un MIDI por stem melódico |
| Transcripción | Partitura | MusicXML, PDF y SVG |
| Transcripción | Mapa de tempo | MIDI con tempo y marcadores de sección para cualquier DAW |
| Vivo | Stage Pack | Stems, click, guía hablada, count-in y split track nombrados para Playback, Prime o DAW |
| Vivo | Setlist Pack | Varios Stage Packs con el mismo formato y orden de show |
| Producción | Producer Pack | Stems nombrados con BPM y tono, acapella limpia, MIDI y mapa de tempo |
| Producción | Loops | Cada stem cortado en loops de 4, 8 y 16 compases |
| Producción | One-shots | Golpes sueltos de batería extraídos del stem |
| Práctica | Mixer | Mute, solo, volumen, paneo y loop A-B por stem |
| Práctica | Karaoke | Instrumental con letra sincronizada |
| Utilidades | Conversor | Cambio de formato, frecuencia de muestreo y bits |
| Utilidades | Recorte | Cortar fragmento, quitar silencios y normalizar |

## Stack técnico

Todo sale de proyectos open source existentes. Como Essentia es AGPL y Rubber Band es GPL, el proyecto entero se publica como open source bajo AGPL (decisión tomada el 2026-10-25). La tool lleva la marca de la agencia, lo que cuenta como uso comercial, así que no se usan modelos ni checkpoints con licencia no comercial o sin licencia escrita.

| Función | Proyecto | Licencia | Corre en |
| --- | --- | --- | --- |
| Decodificar y convertir | ffmpeg | LGPL o GPL | CPU |
| Bajar links | yt-dlp | Unlicense | CPU |
| Stems base (4 y 6) | Demucs htdemucs\_ft y htdemucs\_6s | MIT | CPU o GPU |
| Stems de máxima calidad | BS-RoFormer y Mel-Band RoFormer vía python-audio-separator | MIT el código, checkpoints variables | GPU |
| Checkpoints de entrenamiento | ZFTurbo Music-Source-Separation-Training | MIT el código, checkpoints variables | GPU |
| Voz principal y coros | Checkpoints Mel-RoFormer karaoke | Variable | GPU |
| Batería por piezas | Modelos DrumSep (MDX23C) | Variable | GPU |
| Quitar reverb | Modelos de dereverb de la comunidad UVR | Variable | GPU |
| Beats y compases | beat\_this (CPJKU) | MIT | CPU |
| Secciones | allin1 (All-In-One Music Structure Analyzer) | MIT | CPU o GPU |
| Tonalidad | Essentia KeyExtractor más librosa para cruzar | AGPL y ISC | CPU |
| Acordes | Detección propia por plantillas sobre chroma (madmom descartado por modelos no comerciales) | Propio | CPU |
| Letra | faster-whisper | MIT | CPU o GPU |
| Audio a MIDI | basic-pitch (Spotify) | Apache 2.0 | CPU |
| Partitura | music21 para generar y Verovio u OpenSheetMusicDisplay para mostrar | BSD y LGPL | CPU y navegador |
| Tono y tempo final | Rubber Band vía pyrubberband (motor R3) | GPL | CPU |
| Tono y tempo en vivo | signalsmith-stretch o SoundTouch en el navegador | MIT y LGPL | Navegador |
| Volumen | pyloudnorm | MIT | CPU |
| Cues de voz | Grabadas a mano, o Piper como TTS local | Según versión | Una sola vez |
| Front | Next.js, wavesurfer.js con regiones, Web Audio, Tone.js | MIT | Navegador |
| API | FastAPI | MIT | CPU |
| Cola | Redis con RQ o Celery | BSD | CPU |
| Base de datos | PostgreSQL | PostgreSQL | CPU |
| Archivos | Cloudflare R2 o S3 con borrado automático a 24 horas | Servicio | Nube |
| GPU por demanda | Modal o RunPod Serverless | Servicio | Nube |

Antes de usar cada checkpoint de separación hay que anotar su licencia en un archivo MODELS.md del repo, porque varios de la comunidad no tienen licencia clara.

## Arquitectura

&#91;embedded content: arquitectura · 7 componentes, un solo paso en GPU\]

El navegador sube y edita, la API encola trabajos, el worker de CPU analiza y arma los packs, y solo la separación salta a la GPU. Las descargas salen directo de R2 con links firmados. En la fase 1 el worker de GPU no existe y Demucs corre en el de CPU.

## Stage Pack

Es un ZIP donde todos los archivos tienen la misma duración exacta en muestras y arrancan en la muestra cero con el count-in incluido, así se alinean solos en cualquier software.

**Count-in**

- 1 o 2 compases, elegible
- El click suena en cada tiempo y la guía cuenta "uno, dos, tres, cuatro" (o "uno, dos, tres" en 3/4)
- Se agregan esos compases de silencio al principio de todos los stems

**Click**

- Sigue la grilla de beats detectada, no un BPM fijo, para que acompañe las canciones grabadas sin click
- Opción "grilla recta" cuando el tempo es estable, que cuantiza al BPM promedio
- Acento en el primer tiempo de cada compás
- Sonidos a elegir entre clásico, cowbell, woodblock y rimshot
- Subdivisión opcional en corcheas
- Se genera con numpy, sin librerías extra

**Guía hablada**

- Cada cue cae exactamente un compás antes del inicio de su sección
- Solo va en la pista Guide, nunca en la mezcla de la banda
- Librería de samples en español y en inglés con Intro, Verso, Verso 2, Pre-coro, Coro, Puente, Solo, Instrumental, Break, Final, Tag y la cuenta del uno al cuatro
- Los samples se graban una sola vez (voz propia) o se generan con Piper y se guardan en assets

**Split track**

- Archivo estéreo con click más guía en el canal izquierdo y la suma de la banda en mono en el derecho
- Sirve para mandar a un solo envío de in-ears

**Formato de audio**

- WAV de 44,1 o 48 kHz y 24 bits, elegible
- La voz principal queda afuera por defecto, con opción de incluirla

**Nombres según destino**

| Destino | Archivos |
| --- | --- |
| Playback | Click, Guide, Drums, Bass, Keys, Electric Guitar, BGVs, Tracks |
| Prime | Mismo set con click y guía listos para salidas propias (verificar la convención exacta contra la documentación de Prime) |
| Ableton, Logic, Reaper y otros | Nombres en español numerados (01 Click, 02 Guía, 03 Batería) |

**Contenido del ZIP**

- Nombre del archivo con tema, tono y BPM, por ejemplo "Tema - G - 72 BPM.zip"
- Un WAV por parte, Click, Guide y Split Track
- Secciones.txt con cada sección, compás de inicio y tiempo
- Mapa de tempo en MIDI con marcadores de sección
- Cómo importar.txt con los pasos para el destino elegido

## Producer Pack

Es el pack para quien remixa. Deja la canción lista para arrastrar a un proyecto de techno o house a un tempo y tono elegidos, ya cortada en piezas útiles.

**Opciones antes de generar**

- Tempo objetivo (por defecto el original, con atajos a 120, 124, 128 y 132)
- Tono objetivo, o "combinar con" otro tema para que la tool proponga la transposición más corta a un tono compatible en Camelot
- Qué stems incluir y si separar la batería por piezas

**Qué trae**

- Stems con tono y BPM en el nombre ("Tema - Vox - 8A - 128.wav")
- Acapella principal limpia de reverb, y los coros aparte
- Toda la canción llevada a grilla recta al tempo objetivo con Rubber Band, así calza con el BPM del DAW sin warp manual
- Loops de 4, 8 y 16 compases por stem, cortados exactamente sobre la grilla y nombrados por sección ("Coro 1 - Bass - 8 bars.wav")
- One-shots de batería (bombo, redoblante, hi-hat) detectados por ataques sobre el stem de batería, con los más limpios elegidos por nivel de bleed
- Un MIDI por stem melódico (bajo, piano, guitarra, voz) y uno con la progresión de acordes
- Mapa de tempo en MIDI con marcadores de sección
- Info.txt con BPM, tono, Camelot, compatibles, LUFS y estructura

**Estructura de carpetas**

- Stems
- Acapella
- Loops (una subcarpeta por stem)
- One-shots
- MIDI
- Info.txt

## Interfaz

El resultado nunca es un botón de descarga sino un estudio en el navegador donde se escucha, se corrige y recién después se exporta. Todo lo que se edita acá corre en el cliente, sin volver a subir audio.

| Pantalla o editor | Qué hace |
| --- | --- |
| Inicio | Una barra para soltar archivo o pegar link, con el modo elegido (Vivo, Producción, Solo stems, Solo análisis) |
| Procesando | Posición en la cola, etapa actual y resultado gratis parcial apenas está el análisis |
| Mixer | Un carril por stem con forma de onda, mute, solo, volumen, paneo, medidores y loop A-B |
| Editor de secciones | Regiones sobre la forma de onda que se arrastran, se renombran y se ajustan al compás más cercano. Al reproducir suena el click y las cues |
| Editor de grilla | Mover el primer tiempo, tap tempo, cambiar compás y corregir tramos donde el beat tracking se perdió |
| Tono y tempo | Preview en tiempo real en el navegador, render final en el servidor al exportar |
| Piano roll | Ver y corregir el MIDI de cada stem con undo, cuantizado y transposición |
| Partitura | Notación que se reproduce con cursor y se baja en PDF, SVG o MusicXML |
| Acordes y letra | Tira de acordes y letra sincronizadas bajo el mixer |
| Exportar | Elegir pack (Stage o Producer), destino, count-in, sonido de click y formato |
| Setlist | Lista de temas con orden de show, estado de cada uno y un ZIP final |

Todo en español, con modo oscuro por defecto y pensado para usarse también desde el celular en el ensayo.

## Repo y datos

Un monorepo donde todo el procesamiento de audio vive en una librería Python propia que se puede usar sola desde la terminal. La web, la API y los workers solo la llaman.

```
/apps/web            Next.js, mixer y editores
/apps/api            FastAPI, jobs, links firmados
/workers/cpu         análisis, click, guía, packs, tono y tempo
/workers/gpu         separación (Demucs y RoFormer)
/packages/audio-core librería Python con todos los pipelines y una CLI
/assets/cues/es      samples de voz en español
/assets/cues/en      samples de voz en inglés
/assets/clicks       sonidos de click
/infra               docker-compose, Caddy, límites de CPU
/tests/fixtures      canciones de prueba con licencia libre
MODELS.md            cada checkpoint con su licencia y origen
```

| Entidad | Campos principales |
| --- | --- |
| Song | id, origen (archivo o link), duración, hash del audio, vence a las 24 horas |
| Analysis | bpm, beats, downbeats, compás, tono, camelot, acordes, letra, lufs, versión de cada modelo |
| Section | etiqueta, número, compás de inicio, compás de fin, editada por el usuario sí o no |
| StemSet | modelo usado, lista de stems con su archivo y formato |
| Job | tipo, estado, posición en cola, etapa, error, tiempos |
| Pack | tipo (Stage o Producer), destino, opciones, archivo ZIP, link de descarga |
| Setlist | lista ordenada de songs y su pack final |

El hash del audio permite reusar el análisis y los stems si alguien sube la misma canción dentro de las 24 horas, sin gastar GPU dos veces.

## Roadmap

&#91;embedded content: roadmap · 4 fases y 3 condiciones para avanzar\]

La fase 1 ya compite con AudioForges en lo que la gente más usa y corre gratis en la VPS. Cada rombo es la condición para pasar a la siguiente fase, así no se paga GPU antes de saber que la tool sirve.

## Límites, legales y costos

La única pieza que cuesta plata por canción es la separación en GPU. Todo lo demás corre en una VPS chica.

**Límites técnicos que hay que comunicar**

- Los stems separados siempre tienen algo de bleed y nunca igualan a los multitracks originales de estudio
- Dos partes del mismo instrumento en el mismo registro (dos guitarras, voces dobladas) no se separan
- La batería por piezas y los one-shots salen útiles pero imperfectos
- El click se pierde en temas sin tempo fijo, en vivo o con compás raro, y ahí entra el editor de grilla
- allin1 está entrenado con pop anglo, así que en cumbia, cuarteto, folklore o trap las etiquetas fallan más. Se mejora detectando el coro como la parte cuya letra más se repite
- Transponer más de 3 o 4 semitonos degrada el sonido

**Legales**

- La tool separa audio y no otorga derechos. Va un aviso claro en cada pantalla de subida
- Nada se guarda más de 24 horas y no hay galería pública de resultados
- Bajar de YouTube va contra sus términos, así que la ingesta por link es opcional y se puede apagar
- Algunos checkpoints son de uso no comercial. Mientras la tool sea gratis no hay problema, pero si alguna vez se cobra algo hay que revisarlos
- Publicar el código bajo AGPL cubre las licencias de Essentia y Rubber Band. Decidido: el código es abierto, sin costo de licencias comerciales

**Costos y financiamiento**

| Recurso | Opción | Costo estimado |
| --- | --- | --- |
| Servidor de CPU | VPS existente con el contenedor limitado a 2 núcleos, o una VPS aparte | Ya pagado, o una VPS chica mensual |
| Separación | GPU serverless por segundo de uso | Centavos de dólar por canción (medir en fase 2) |
| Archivos | R2 con borrado a 24 horas | Casi nulo |
| Dominio | Un .com o .ar | Anual |

La agencia financia la tool como parte de su marca. Sin publicidad ni sponsors (decisión del 2026-10-25). Se mantiene un límite diario por usuario para que la GPU no se dispare. Los costos se siguen en docs/costos.md.

## Instrucciones para Claude Code

Se arranca por la librería de audio y su CLI, no por la web. Si el pipeline produce un ZIP correcto desde la terminal, el resto es interfaz.

1. Crear el monorepo con la estructura de Repo y datos y un docker-compose con api, worker-cpu, redis y postgres
2. En packages/audio-core armar una CLI con estos comandos, cada uno escribiendo su salida en una carpeta
   1. analyze (tempo, grilla, tono, secciones, acordes, letra, LUFS) que devuelve un analysis.json
   2. separate con el modelo como parámetro (htdemucs\_6s por defecto)
   3. stagepack con destino, count-in, sonido de click y frecuencia de muestreo
   4. producerpack con tempo y tono objetivo
   5. transpose y stretch sobre un StemSet entero
   6. midi y score por stem
3. Escribir tests con canciones de licencia libre en tests/fixtures que verifiquen
   1. Que todos los archivos de un pack tienen exactamente la misma cantidad de muestras
   2. Que cada golpe del click cae a menos de 10 ms de su beat en analysis.json
   3. Que cada cue empieza un compás antes de su sección
   4. Que la suma de los stems se parece a la mezcla original (diferencia medida en dB)
   5. Que los loops empiezan y terminan sobre un primer tiempo de compás
4. Envolver la CLI en workers con RQ y exponer jobs desde FastAPI
5. Construir el front empezando por el mixer y el editor de secciones, que son lo que define si el usuario confía en el pack
6. Sumar el worker de GPU en Modal o RunPod recién en la fase 2, con la misma interfaz que el worker de CPU

Reglas para el agente

- No inventar nombres de checkpoints. Listar los disponibles en python-audio-separator y elegir de esa lista, anotándolos en MODELS.md
- Todo el audio interno en float32 a 44,1 kHz, y convertir solo al exportar
- Cada paso del análisis guarda la versión del modelo que lo produjo
- Nada de secretos en el repo. Los tokens se completan a mano en un .env
