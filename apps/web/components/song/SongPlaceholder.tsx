"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { describeError, getSong, type SongOut } from "@/lib/api";
import styles from "./SongPlaceholder.module.css";

type State = { status: "loading" } | { status: "ready"; song: SongOut } | { status: "error"; message: string };

/** Stand-in until the processing screen lands: confirms the upload reached the API. */
export function SongPlaceholder({ songId }: { songId: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getSong(songId, { signal: controller.signal })
      .then((song) => setState({ status: "ready", song }))
      .catch((error) => {
        if (!controller.signal.aborted) setState({ status: "error", message: describeError(error) });
      });
    return () => controller.abort();
  }, [songId]);

  return (
    <main className={styles.page}>
      {state.status === "loading" && <p className={styles.note}>Cargando…</p>}
      {state.status === "error" && (
        <div role="alert">
          <p className={styles.error}>{state.message}</p>
          <Link href="/" className={styles.back}>
            Subir otra canción
          </Link>
        </div>
      )}
      {state.status === "ready" && (
        <>
          <h1 className={styles.title}>{state.song.filename}</h1>
          <p className={`${styles.id} mono`}>{state.song.id}</p>
          <p className={styles.note}>El análisis y la separación ya están en marcha.</p>
        </>
      )}
    </main>
  );
}
