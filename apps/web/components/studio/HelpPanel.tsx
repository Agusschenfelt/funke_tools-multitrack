"use client";

import { Fragment, useEffect, useRef, type RefObject } from "react";
import { PRESETS } from "@/lib/audio/presets";
import { AREAS, GESTURES, HELP_TITLE, LEGEND, SHORTCUTS } from "@/lib/studio/help";
import styles from "./HelpPanel.module.css";

const JOINER = { or: "o", plus: "+" } as const;

/**
 * What each area does, the shortcuts, the gestures and the small marks, in one place. Not modal:
 * Escape, the Cerrar button, "?" or a press outside close it, and focus goes back to the button.
 */
export function HelpPanel({
  id,
  onClose,
  triggerRef,
}: {
  id: string;
  onClose: () => void;
  triggerRef: RefObject<HTMLButtonElement | null>;
}) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const panel = ref.current;
    panel?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panel?.contains(target) || triggerRef.current?.contains(target)) return;
      onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    const trigger = triggerRef.current;
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
      // Give focus back unless the user already moved it somewhere on purpose.
      const active = document.activeElement;
      if (!active || active === document.body) trigger?.focus();
    };
  }, [onClose, triggerRef]);

  return (
    <section ref={ref} id={id} className={styles.panel} role="dialog" aria-label={HELP_TITLE} tabIndex={-1}>
      <div className={styles.head}>
        <h2 className={styles.title}>{HELP_TITLE}</h2>
        <button type="button" className={styles.close} onClick={onClose}>
          Cerrar
        </button>
      </div>

      <h3 className={styles.heading}>Cada zona</h3>
      <dl className={styles.list}>
        {AREAS.map((area) => (
          <Fragment key={area.name}>
            <dt>{area.name}</dt>
            <dd>{area.what}</dd>
          </Fragment>
        ))}
      </dl>

      <h3 className={styles.heading}>Atajos</h3>
      <dl className={styles.list}>
        {SHORTCUTS.map((shortcut) => (
          <Fragment key={shortcut.keys.join("-") + shortcut.what}>
            <dt>
              {shortcut.keys.map((key, index) => (
                <Fragment key={key}>
                  {index > 0 && <span className={styles.joiner}>{JOINER[shortcut.join ?? "or"]}</span>}
                  <kbd className={`${styles.key} mono`}>{key}</kbd>
                </Fragment>
              ))}
            </dt>
            <dd>{shortcut.what}</dd>
          </Fragment>
        ))}
      </dl>

      <h3 className={styles.heading}>Gestos</h3>
      <dl className={styles.list}>
        {GESTURES.map((gesture) => (
          <Fragment key={gesture.how}>
            <dt>{gesture.how}</dt>
            <dd>{gesture.what}</dd>
          </Fragment>
        ))}
      </dl>

      <h3 className={styles.heading}>Qué significan las marcas</h3>
      <dl className={styles.list}>
        {LEGEND.map((item) => (
          <Fragment key={item.mark}>
            <dt className={item.mono ? "mono" : undefined}>{item.mark}</dt>
            <dd>{item.what}</dd>
          </Fragment>
        ))}
      </dl>

      <h3 className={styles.heading}>Mezclas rápidas</h3>
      <ul className={styles.plain}>
        {PRESETS.map((preset) => (
          <li key={preset.id}>{preset.hint}</li>
        ))}
      </ul>
    </section>
  );
}
