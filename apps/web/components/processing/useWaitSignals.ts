"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PRODUCT_NAME } from "@/lib/brand";
import { notifyState, shouldNotify, type NotifyState } from "@/lib/wait";

/** Keeps the tab title in step with the wait and restores it when the view goes away. */
export function useTabTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);
}

function currentPermission(): string | null {
  try {
    return typeof Notification === "undefined" ? null : Notification.permission;
  } catch {
    return null;
  }
}

/**
 * Optional browser notification for when the work ends. Permission is asked only from `request`,
 * which the UI calls on a click; everything is guarded because notifications can be missing or
 * blocked. Fires once, and only when the tab is not in view.
 */
export function useCompletionNotice(done: boolean, wasWaiting: boolean, songTitle: string) {
  const [state, setState] = useState<NotifyState>("unsupported");
  const fired = useRef(false);

  useEffect(() => {
    // Notification support is only known in the browser, after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState(notifyState(currentPermission()));
  }, []);

  const request = useCallback(() => {
    try {
      const result = Notification.requestPermission((permission) => setState(notifyState(permission)));
      if (result && typeof result.then === "function") {
        void result.then((permission) => setState(notifyState(permission))).catch(() => undefined);
      }
    } catch {
      setState("unsupported");
    }
  }, []);

  useEffect(() => {
    if (!done || !wasWaiting || fired.current) return;
    fired.current = true;
    if (!shouldNotify(state, document.hidden)) return;
    try {
      const notice = new Notification(PRODUCT_NAME, {
        body: `“${songTitle}” ya tiene sus pistas. Abrí el estudio.`,
      });
      notice.onclick = () => {
        window.focus();
        notice.close();
      };
    } catch {
      // Blocked or unsupported: the tab title still says the work is done.
    }
  }, [done, wasWaiting, state, songTitle]);

  return { state, request };
}
