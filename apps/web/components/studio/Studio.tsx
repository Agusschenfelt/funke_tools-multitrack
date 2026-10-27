"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  ApiError,
  describeError,
  getAnalysis,
  getSections,
  getSong,
  type Analysis,
  type Section,
  type SongDetail,
} from "@/lib/api";
import { StudioEngine, type LoadFailure } from "@/lib/audio/engine";
import { beatsPerBar } from "@/lib/audio/grid";
import { loopLabel as describeLoop, snapLoop } from "@/lib/audio/loop";
import { stemGains } from "@/lib/audio/mix";
import { loadPans, savePans } from "@/lib/audio/panStore";
import { detectPreset } from "@/lib/audio/presets";
import { buildClickEvents, cuePlacements } from "@/lib/audio/schedule";
import { orderStems, studioSources } from "@/lib/audio/stems";
import { formatBytes } from "@/lib/format";
import { chordsAround, type Chord } from "@/lib/chords";
import { buildStrip, flatIndex, locateActive } from "@/lib/strip";
import { editControlsVisible } from "@/lib/studio/toolbar";
import { isHelpKey, LEGEND } from "@/lib/studio/help";
import { loadTitle, saveTitle, titleView } from "@/lib/studio/title";
import { useEngineState, useFrame } from "./hooks";
import { ChordLane } from "./ChordLane";
import { Lane } from "./Lane";
import { MixBar } from "./MixBar";
import { DownloadsPanel } from "./DownloadsPanel";
import { EditControls, SectionEditor } from "./SectionPanel";
import { SectionStrip } from "./SectionStrip";
import { SongBar } from "./SongBar";
import { Transport } from "./Transport";
import { useSectionEditor } from "./useSectionEditor";
import lanes from "./Lane.module.css";
import styles from "./Studio.module.css";

type Load =
  | { phase: "loading" }
  | {
      phase: "ready";
      song: SongDetail;
      analysis: Analysis;
      sections: Section[];
      source: string | null;
      edited: boolean;
    }
  | { phase: "missing" }
  | { phase: "nostems" }
  | { phase: "error"; message: string };

export function Studio({ songId }: { songId: string }) {
  const [load, setLoad] = useState<Load>({ phase: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    getSong(songId, { signal })
      .then(async (song) => {
        if (song.artifacts.stems.length === 0 || !song.artifacts.analysis) {
          setLoad({ phase: "nostems" });
          return;
        }
        const [analysis, sections] = await Promise.all([
          getAnalysis(songId, { signal }),
          getSections(songId, { signal }).catch(() => null),
        ]);
        setLoad({
          phase: "ready",
          song,
          analysis,
          sections: sections?.sections ?? [],
          source: sections?.source ?? null,
          edited: sections?.edited ?? false,
        });
      })
      .catch((error) => {
        if (signal.aborted) return;
        if (error instanceof ApiError && error.kind === "http" && error.status === 404) {
          setLoad({ phase: "missing" });
        } else {
          setLoad({ phase: "error", message: describeError(error) });
        }
      });
    return () => controller.abort();
  }, [songId, attempt]);

  const reload = () => {
    setLoad({ phase: "loading" });
    setAttempt((n) => n + 1);
  };

  return (
    <main className={styles.studio}>
      {load.phase === "loading" && (
        <p className={styles.loadingNote} role="status">
          Cargando el estudio…
        </p>
      )}
      {load.phase === "missing" && (
        <div role="alert" className={styles.fatal}>
          <p>No encontramos esta canción. Los archivos se borran a las 24 h.</p>
          <Link href="/" className={styles.action}>
            Subir de nuevo
          </Link>
        </div>
      )}
      {load.phase === "nostems" && (
        <div role="alert" className={styles.fatal}>
          <p>Las pistas todavía no están listas, o ya se borraron. Mirá cómo va el procesamiento.</p>
          <Link href={`/temas/${songId}`} className={styles.action}>
            Ver el procesamiento
          </Link>
        </div>
      )}
      {load.phase === "error" && (
        <div role="alert" className={styles.fatal}>
          <p>{load.message}</p>
          <button type="button" className={styles.action} onClick={reload}>
            Reintentar
          </button>
        </div>
      )}
      {load.phase === "ready" && (
        <StudioBody
          key={attempt}
          songId={songId}
          song={load.song}
          analysis={load.analysis}
          sections={load.sections}
          source={load.source}
          edited={load.edited}
          onReload={reload}
        />
      )}
    </main>
  );
}

function failureText(failure: LoadFailure | null): string {
  switch (failure) {
    case "expired":
      return "Los enlaces de las pistas vencieron o ya no existen. Pedilos de nuevo.";
    case "decode":
      return "Este navegador no pudo leer una de las pistas.";
    case "unsupported":
      return "Este navegador no puede reproducir audio.";
    default:
      return "No pudimos descargar las pistas. Revisá tu conexión.";
  }
}

interface BodyProps {
  songId: string;
  song: SongDetail;
  analysis: Analysis;
  sections: Section[];
  source: string | null;
  edited: boolean;
  onReload: () => void;
}

/**
 * Owns the engine's lifetime: one engine per mount, created in the effect and disposed in its
 * cleanup. A disposed engine is final, so React Strict Mode's second effect run (or any remount)
 * gets a fresh one instead of reusing a dead context.
 */
function StudioBody(props: BodyProps) {
  const { song } = props;
  const studio = useMemo(() => studioSources(song.artifacts), [song]);
  const [engine, setEngine] = useState<StudioEngine | null>(null);

  useEffect(() => {
    const next = new StudioEngine();
    const controller = new AbortController();
    // Publishing an external resource created by this effect; it cannot be created during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEngine(next);
    next.load(studio.sources, controller.signal).catch(() => {
      // load() reports its own failures through the engine state; this only keeps a bug from
      // surfacing as an unhandled rejection.
      if (!controller.signal.aborted) next.reportFailure("network");
    });
    return () => {
      controller.abort();
      next.dispose();
      setEngine(null);
    };
  }, [studio]);

  if (!engine) {
    return (
      <p className={styles.loadingNote} role="status">
        Cargando el estudio…
      </p>
    );
  }
  return <StudioStage engine={engine} compressed={studio.compressed} {...props} />;
}

function StudioStage({
  engine,
  compressed,
  songId,
  song,
  analysis,
  sections: initialSections,
  source,
  edited,
  onReload,
}: BodyProps & { engine: StudioEngine; compressed: boolean }) {
  const state = useEngineState(engine);
  const [helpOpen, setHelpOpen] = useState(false);

  const grid = analysis.grid;
  const hasGrid = Boolean(grid && grid.downbeats.length > 0);
  const beats = useMemo(() => grid?.beats ?? [], [grid]);
  const downbeats = useMemo(() => grid?.downbeats ?? [], [grid]);
  const perBar = beatsPerBar(grid?.time_signature);
  const duration = state.duration || analysis.duration;
  const names = useMemo(() => orderStems(song.artifacts.stems).map((s) => s.name), [song]);

  const editor = useSectionEditor({
    songId,
    initial: initialSections,
    source,
    edited,
    downbeats,
  });
  const sections = editor.sections;

  const groups = useMemo(
    () => buildStrip(sections, downbeats, duration),
    [sections, downbeats, duration],
  );

  useEffect(() => {
    engine.setTimeline({
      beats,
      clicks: buildClickEvents(beats, downbeats),
      cues: cuePlacements(sections, beats, downbeats, perBar),
    });
  }, [engine, beats, downbeats, sections, perBar]);

  // The section under the playhead; state changes only when it moves to another section.
  const [active, setActive] = useState<{ group: number; span: number } | null>(null);
  const track = useCallback(
    (position: number) => {
      const next = locateActive(groups, position);
      setActive((prev) =>
        prev?.group === next?.group && prev?.span === next?.span ? prev : next,
      );
    },
    [groups],
  );
  useFrame(engine, track);

  // The chord under the playhead and the next one; state changes only when either moves on.
  const chords = useMemo<readonly Chord[]>(() => analysis.chords ?? [], [analysis.chords]);
  const [around, setAround] = useState({ current: -1, next: -1 });
  const trackChords = useCallback(
    (position: number) => {
      const next = chordsAround(chords, position);
      setAround((prev) =>
        prev.current === next.current && prev.next === next.next ? prev : next,
      );
    },
    [chords],
  );
  useFrame(engine, trackChords);

  // Space plays and pauses unless it would press a control or edit text.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      // ? opens or closes the help from anywhere except a text field.
      if (isHelpKey(event)) {
        if (target?.closest("input, textarea, select, [contenteditable]")) return;
        setHelpOpen((open) => !open);
        return;
      }
      // L clears the loop from anywhere except a text field.
      if (event.key === "l" || event.key === "L") {
        if (target?.closest("input, textarea, select, [contenteditable]")) return;
        engine.clearLoop();
        return;
      }
      if (event.code !== "Space") return;
      if (target?.closest("button, a, input, select, textarea, [role='slider']")) return;
      event.preventDefault();
      engine.toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [engine]);

  const gains = stemGains(state.mix);
  const [ruler, setRuler] = useState<"bars" | "time">(hasGrid ? "bars" : "time");
  const [downloadsOpen, setDownloadsOpen] = useState(false);
  const downloadsId = useId();
  const toggleHelp = useCallback(() => setHelpOpen((open) => !open), []);
  const wavs = useMemo(() => orderStems(song.artifacts.stems), [song]);
  // The rename lives in this browser only; the stage only mounts on the client, so reading is safe.
  const [customTitle, setCustomTitle] = useState<string | null>(() => loadTitle(songId));
  const titleInfo = titleView(song.filename, duration, customTitle);
  const title = titleInfo.text;
  const rename = (next: string | null) => {
    setCustomTitle(next);
    saveTitle(songId, next);
  };
  const silent = names.every((name) => gains[name] === 0);
  const preset = detectPreset(state.mix, state.order);

  // Pans are remembered per song: restored once the lanes exist, saved on every change after that.
  const restoredPans = useRef(false);
  const panKey = names.map((name) => state.mix[name].pan).join(",");
  useEffect(() => {
    if (state.status !== "ready") return;
    if (!restoredPans.current) {
      restoredPans.current = true;
      engine.restorePans(loadPans(songId));
      return;
    }
    savePans(songId, Object.fromEntries(names.map((name) => [name, state.mix[name].pan])));
    // panKey stands for the pan values; the rest of state.mix is irrelevant here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine, songId, state.status, panKey]);
  const activeGroup = active ? active.group : null;
  const activeSpan = active ? groups[active.group]?.spans[active.span] ?? null : null;
  const activeIndex = flatIndex(groups, active);

  const editorOpen = editor.selected !== null;
  const showEdit = editControlsVisible({
    dirty: editor.dirty,
    saving: editor.saving,
    canUndo: editor.canUndo,
    canRedo: editor.canRedo,
    editorOpen,
    status: editor.status,
  });
  const editControls = (dense: boolean) =>
    showEdit ? (
      <EditControls
        dense={dense}
        dirty={editor.dirty}
        saving={editor.saving}
        status={editor.status}
        canUndo={editor.canUndo}
        canRedo={editor.canRedo}
        onUndo={editor.undo}
        onRedo={editor.redo}
        onSave={editor.save}
      />
    ) : null;

  const select = (index: number) => {
    editor.select(index);
    const section = sections[index];
    if (section) engine.seek(section.start);
  };
  const playSection = (index: number) => {
    const section = sections[index];
    if (!section) return;
    editor.select(index);
    engine.seek(section.start);
    void engine.play();
  };
  const loadedCount = names.filter((name) => state.stems[name].phase === "ready").length;
  const downloaded = names.reduce((sum, name) => sum + state.stems[name].loaded, 0);
  const sizeNote =
    state.status === "ready" && downloaded > 0
      ? `${compressed ? "Vista previa comprimida" : "Pistas sin comprimir"}: ${formatBytes(downloaded)} descargados. El pack exportado conserva la calidad completa.`
      : null;

  return (
    <>
      <SongBar
        songId={songId}
        title={titleInfo}
        analysis={analysis}
        dirty={editor.dirty}
        saving={editor.saving}
        onSave={editor.save}
        onRename={rename}
        helpOpen={helpOpen}
        onToggleHelp={toggleHelp}
      />

      {state.status === "error" && (
        <div role="alert" className={styles.notice}>
          <p>{failureText(state.failure)}</p>
          <button type="button" className={styles.action} onClick={onReload}>
            Pedir de nuevo
          </button>
        </div>
      )}

      <p className="visually-hidden" role="status">
        {state.status === "loading" ? `Cargando pistas: ${loadedCount} de ${names.length}` : ""}
        {state.status === "ready" ? "Pistas listas" : ""}
      </p>

      <div className={styles.stage}>
        <SectionStrip
          engine={engine}
          sections={sections}
          downbeats={downbeats}
          estimatedUntil={grid?.extrapolated_until ?? null}
          duration={duration}
          loop={state.loop}
          ruler={ruler}
          activeIndex={activeIndex}
          selected={editor.selected}
          editedOnServer={editor.editedOnServer}
          onSelect={select}
          onPlay={playSection}
          onMove={editor.move}
          onNudge={editor.nudge}
        />
        <div className={styles.slot}>
          {editor.selected !== null && (
            <SectionEditor
              edit={editControls(false)}
              sections={sections}
              selected={editor.selected}
              downbeats={downbeats}
              onRename={editor.rename}
              onSplit={() => editor.split(engine.getPosition())}
              onMerge={editor.merge}
              onNudge={editor.nudge}
              onPlay={playSection}
              onClose={() => editor.select(null)}
            />
          )}
        </div>
        {sections.length === 0 && <p className={styles.quiet}>Esta canción no tiene secciones.</p>}
        <MixBar
          preset={preset}
          disabled={state.status !== "ready"}
          onPreset={(id) => engine.applyPreset(id)}
          loopLabel={state.loop ? describeLoop(state.loop, downbeats, duration) : null}
          canLoopSection={activeSpan !== null}
          onLoopSection={() => {
            if (!activeSpan) return;
            const range = snapLoop(activeSpan.start, activeSpan.end, { downbeats, duration, snap: true });
            if (range) engine.setLoop(range);
          }}
          onClearLoop={() => engine.clearLoop()}
          ruler={ruler}
          onRuler={setRuler}
          downloadsOpen={downloadsOpen}
          onToggleDownloads={() => setDownloadsOpen((open) => !open)}
          downloadsId={downloadsId}
          edit={editorOpen ? null : editControls(true)}
          editorOpen={editorOpen}
        />
        {downloadsOpen && (
          <DownloadsPanel
            id={downloadsId}
            engine={engine}
            title={title}
            duration={duration}
            compressed={compressed}
            wavSources={wavs}
            hasGrid={hasGrid}
            silent={silent}
            ready={state.status === "ready"}
            note={sizeNote}
          />
        )}
        <div className={lanes.lanes}>
          {names.map((name, index) => (
            <Lane
              key={name}
              engine={engine}
              name={name}
              view={state.stems[name]}
              mix={state.mix[name]}
              audible={gains[name] > 0}
              duration={duration}
              activeSpan={activeSpan}
              loop={state.loop}
              index={index}
              count={names.length}
            />
          ))}
        </div>
        <ChordLane engine={engine} chords={chords} duration={duration} current={around.current} />
        <p className={styles.quiet}>
          {LEGEND.slice(0, 3).map((item) => `${item.mark} ${item.short}`).join(" · ")}
        </p>
      </div>

      <Transport
        engine={engine}
        state={state}
        groups={groups}
        beats={beats}
        downbeats={downbeats}
        perBar={perBar}
        duration={duration}
        activeGroup={activeGroup}
        hasGrid={hasGrid}
        currentChord={chords[around.current]?.label ?? null}
        nextChord={chords[around.next]?.label ?? null}
      />
    </>
  );
}
