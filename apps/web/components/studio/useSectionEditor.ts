"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { describeError, putSections, type Section, type SectionName } from "@/lib/api";
import {
  commit,
  createHistory,
  isDirty,
  mergeInto,
  moveBoundary,
  nudgeBoundary,
  redo,
  renameSection,
  serializeSections,
  splitAt,
  undo,
  type EditResult,
} from "@/lib/sections/edit";

export type SaveStatus =
  | { phase: "idle" }
  | { phase: "saving" }
  | { phase: "saved" }
  | { phase: "error"; message: string };

interface Baseline {
  sections: readonly Section[];
  edited: boolean;
}

interface Options {
  songId: string;
  initial: readonly Section[];
  source: string | null;
  edited: boolean;
  downbeats: readonly number[];
}

/**
 * The editing session for one song: history, selection, save with optimistic baseline and
 * rollback, the leave-page warning and the undo shortcuts. Edits are pure functions from
 * `lib/sections/edit`; this only holds the state around them.
 */
export function useSectionEditor({ songId, initial, source, edited, downbeats }: Options) {
  const [history, setHistory] = useState(() => createHistory<readonly Section[]>(initial));
  const [baseline, setBaseline] = useState<Baseline>({ sections: initial, edited });
  const [selectedRaw, setSelected] = useState<number | null>(null);
  const [status, setStatus] = useState<SaveStatus>({ phase: "idle" });
  const saving = status.phase === "saving";

  const sections = history.present as Section[];
  const selected = selectedRaw !== null && selectedRaw < sections.length ? selectedRaw : null;
  const dirty = useMemo(() => isDirty(sections, baseline.sections), [sections, baseline]);

  const apply = useCallback((result: EditResult | null) => {
    if (!result) return;
    setHistory((h) => commit(h, result.sections));
    setSelected(result.index);
    setStatus((s) => (s.phase === "saving" ? s : { phase: "idle" }));
  }, []);

  const doUndo = useCallback(() => setHistory(undo), []);
  const doRedo = useCallback(() => setHistory(redo), []);

  const actions = {
    move: (index: number, time: number) => apply(moveBoundary(sections, index, time, downbeats)),
    nudge: (index: number, bars: number) => apply(nudgeBoundary(sections, index, bars, downbeats)),
    split: (time: number) => apply(splitAt(sections, time, downbeats)),
    merge: (index: number, side: "prev" | "next") => apply(mergeInto(sections, index, side)),
    rename: (index: number, name: SectionName, label: string | null) =>
      apply(renameSection(sections, index, name, label)),
  };

  const save = useCallback(() => {
    if (saving || !dirty) return;
    const sent = sections;
    const previous = baseline;
    // Optimistic: the baseline moves now and rolls back if the server refuses.
    setBaseline({ sections: sent, edited: true });
    setStatus({ phase: "saving" });
    putSections(songId, serializeSections(sent, source))
      .then((out) => {
        setBaseline({ sections: sent, edited: out.edited });
        setStatus({ phase: "saved" });
      })
      .catch((error) => {
        setBaseline(previous);
        setStatus({ phase: "error", message: describeError(error) });
      });
  }, [saving, dirty, sections, baseline, songId, source]);

  useEffect(() => {
    if (!dirty && !saving) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, saving]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "z" || !(event.metaKey || event.ctrlKey) || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, [contenteditable='true']")) return;
      event.preventDefault();
      setHistory(event.shiftKey ? redo : undo);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return {
    sections,
    editedOnServer: baseline.edited,
    selected,
    select: setSelected,
    dirty,
    saving,
    status,
    canUndo: history.past.length > 0,
    canRedo: history.future.length > 0,
    undo: doUndo,
    redo: doRedo,
    save,
    ...actions,
  };
}
