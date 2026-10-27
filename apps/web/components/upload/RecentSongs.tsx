"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getSong } from "@/lib/api";
import { formatAgo, formatTimeLeft } from "@/lib/format";
import {
  markGone,
  readRecent,
  recentHref,
  removeRecent,
  updateRecent,
  visibleRecent,
  type RecentSong,
} from "@/lib/recentSongs";
import { isGoneError, statusAfterLookup } from "@/lib/recentVerification";
import styles from "./RecentSongs.module.css";

const CLOCK_TICK_MS = 30_000;

/** Songs this browser uploaded and that have not expired; each is checked against the API once. */
export function RecentSongs() {
  const [entries, setEntries] = useState<RecentSong[] | null>(null);
  const [nowMs, setNowMs] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    // localStorage only exists in the browser, so the list is read after mount (not during the
    // server render), in a microtask rather than synchronously in the effect body.
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      const start = Date.now();
      setNowMs(start);
      const stored = readRecent(start);
      setEntries(stored);
      // Lazy verification: a 404 or 410 means the song is gone; a reachable one tells if it is ready.
      for (const entry of visibleRecent(stored, start)) {
        getSong(entry.id, { signal: controller.signal })
          .then((song) => {
            const status = statusAfterLookup(song, entry.status);
            if (status) setEntries(updateRecent(entry.id, { status }, Date.now()));
          })
          .catch((error: unknown) => {
            if (isGoneError(error)) setEntries(markGone(entry.id, Date.now()));
            // Any other failure says nothing about the song: keep it as it was.
          });
      }
    });
    return () => controller.abort();
  }, []);

  // "hace X" and "quedan X" must not freeze while the tab stays open.
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), CLOCK_TICK_MS);
    return () => window.clearInterval(timer);
  }, []);

  const shown = entries ? visibleRecent(entries, nowMs) : [];
  if (shown.length === 0) return null;

  return (
    <section className={styles.recent} aria-labelledby="recent-title">
      <h2 id="recent-title" className={styles.title}>
        Tus temas recientes
      </h2>
      <ul className={styles.list}>
        {shown.map((entry) => (
          <li key={entry.id} className={styles.row}>
            <Link href={recentHref(entry)} className={styles.link}>
              <span className={styles.name}>{entry.filename}</span>
              <span className={`${styles.meta} mono`}>
                {formatAgo(nowMs - entry.createdAt)} · quedan {formatTimeLeft(entry.expiresAt - nowMs)}
              </span>
              <span className={styles.go}>{entry.status === "ready" ? "Abrir el estudio" : "Ver el proceso"}</span>
            </Link>
            <button
              type="button"
              className={styles.remove}
              aria-label={`Quitar ${entry.filename} de la lista`}
              onClick={() => setEntries(removeRecent(entry.id, Date.now()))}
            >
              Quitar
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
