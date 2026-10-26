import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  describeError,
  getJob,
  messageForStatus,
  parseDetail,
  uploadSong,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("messageForStatus", () => {
  it.each([
    [415, "formato"],
    [413, "límite"],
    [400, "vacío"],
    [503, "no está disponible"],
    [404, "24 h"],
    [409, "Esperá"],
    [500, "problema"],
  ])("maps HTTP %i to a Spanish message", (status, fragment) => {
    expect(messageForStatus("http", status)).toContain(fragment);
  });

  it("maps network failures and aborts", () => {
    expect(messageForStatus("network", null)).toContain("conexión");
    expect(messageForStatus("aborted", null)).toContain("canceló");
  });

  it("falls back for unknown client errors", () => {
    expect(messageForStatus("http", 418)).toContain("Probá de nuevo");
  });
});

describe("parseDetail", () => {
  it("reads a string detail", () => {
    expect(parseDetail('{"detail":"empty file"}')).toBe("empty file");
  });
  it("joins validation messages", () => {
    expect(parseDetail('{"detail":[{"msg":"a"},{"msg":"b"}]}')).toBe("a; b");
  });
  it("returns null for non-JSON bodies", () => {
    expect(parseDetail("<html>Bad gateway</html>")).toBeNull();
  });
});

describe("describeError", () => {
  it("uses the ApiError message and a generic one otherwise", () => {
    expect(describeError(new ApiError("http", 415))).toContain("formato");
    expect(describeError(new Error("boom"))).toBe("Algo salió mal. Probá de nuevo.");
  });
});

describe("getJob", () => {
  it("returns the parsed job", async () => {
    const job = { job_id: "j1", status: "queued" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(job))));
    await expect(getJob("j1")).resolves.toEqual(job);
  });

  it("throws an ApiError carrying status and detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"detail":"job not found"}', { status: 404 })),
    );
    await expect(getJob("nope")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      detail: "job not found",
    });
  });

  it("turns a rejected fetch into a network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(getJob("j1")).rejects.toMatchObject({ kind: "network" });
  });
});

class FakeXhr {
  static last: FakeXhr;
  status = 0;
  responseText = "";
  upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
  onload?: () => void;
  onerror?: () => void;
  onabort?: () => void;
  url = "";
  sent: unknown;
  constructor() {
    FakeXhr.last = this;
  }
  open(_method: string, url: string) {
    this.url = url;
  }
  send(body: unknown) {
    this.sent = body;
  }
  abort() {
    this.onabort?.();
  }
}

describe("uploadSong", () => {
  const file = new File([new Uint8Array(10)], "tema.wav");

  it("posts multipart, reports progress and resolves with the song", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const progress: number[] = [];
    const promise = uploadSong(file, { onProgress: (f) => progress.push(f) });
    const xhr = FakeXhr.last;
    expect(xhr.url).toMatch(/\/songs$/);
    expect((xhr.sent as FormData).get("file")).toBeInstanceOf(File);
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 });
    xhr.status = 201;
    xhr.responseText = JSON.stringify({ id: "s1", filename: "tema.wav", reused: false });
    xhr.onload?.();
    await expect(promise).resolves.toMatchObject({ id: "s1" });
    expect(progress).toEqual([0.5]);
  });

  it("rejects with the mapped status on a 415", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const promise = uploadSong(file);
    FakeXhr.last.status = 415;
    FakeXhr.last.responseText = '{"detail":"unsupported file type"}';
    FakeXhr.last.onload?.();
    await expect(promise).rejects.toMatchObject({ kind: "http", status: 415 });
  });

  it("rejects as network on transport failure", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const promise = uploadSong(file);
    FakeXhr.last.onerror?.();
    await expect(promise).rejects.toMatchObject({ kind: "network" });
  });

  it("aborts through the signal", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const controller = new AbortController();
    const promise = uploadSong(file, { signal: controller.signal });
    controller.abort();
    await expect(promise).rejects.toMatchObject({ kind: "aborted" });
  });
});

describe("request error bodies", () => {
  const stub = (response: Response) => vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

  it("falls back to the status text for an empty error body", async () => {
    stub(new Response("", { status: 502, statusText: "Bad Gateway" }));
    await expect(getJob("j1")).rejects.toMatchObject({ kind: "http", status: 502, detail: "Bad Gateway" });
  });

  it("does not throw on an HTML error page", async () => {
    stub(new Response("<html>oops</html>", { status: 500, statusText: "Server Error" }));
    await expect(getJob("j1")).rejects.toMatchObject({ kind: "http", status: 500, detail: "Server Error" });
  });

  it("keeps an ApiError when reading the error body fails", async () => {
    const broken = { ok: false, status: 503, statusText: "Unavailable", text: () => Promise.reject(new TypeError("reset")) };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(broken));
    await expect(getJob("j1")).rejects.toMatchObject({ kind: "http", status: 503, detail: "Unavailable" });
  });

  it("reports a lost success body as a network error", async () => {
    const broken = { ok: true, status: 200, statusText: "OK", text: () => Promise.reject(new TypeError("reset")) };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(broken));
    await expect(getJob("j1")).rejects.toMatchObject({ kind: "network" });
  });

  it("reports a non-JSON success body as invalid data", async () => {
    stub(new Response("not json", { status: 200 }));
    await expect(getJob("j1")).rejects.toMatchObject({ kind: "invalid" });
  });
});
