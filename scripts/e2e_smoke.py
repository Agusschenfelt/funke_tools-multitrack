"""End-to-end smoke test against a running API stack.

Run from the repository root (the stack must already be up):

    uv run --project packages/audio-core python scripts/e2e_smoke.py --api http://localhost:8000

It uploads a synthetic song, analyzes it (with sections), edits the sections, separates stems, builds
a stage pack, downloads the ZIP and checks it, then runs two negative checks. Only the standard
library is used for HTTP. Exits non-zero on the first failing step.
"""

import argparse
import io
import json
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from urllib import error, parse, request

import numpy as np
import soundfile as sf
from rich.console import Console
from rich.table import Table

SAMPLE_RATE = 44100
BPM = 120.0
BEATS_PER_BAR = 4
BAR_SECONDS = BEATS_PER_BAR * 60.0 / BPM
# (part, bars): 16 bars at 120 bpm is a 32 s song.
STRUCTURE = [("intro", 2), ("A", 4), ("B", 4), ("A", 4), ("outro", 2)]
CHORDS = {
    "intro": [220.0, 261.63, 329.63],
    "A": [261.63, 329.63, 392.0],
    "B": [349.23, 440.0, 523.25],
    "outro": [220.0, 261.63, 329.63],
}
AMPLITUDE = {"intro": 0.05, "A": 0.12, "B": 0.3, "outro": 0.05}
EDITED_LABEL = "Estribillo QA"

console = Console()


class SmokeError(Exception):
    pass


def make_song(seed: int) -> np.ndarray:
    """Mono float32 song (the seed varies the hats so each run has a new hash): chords per part plus a kick on every beat and hats on every eighth."""
    rng = np.random.default_rng(seed)
    n = int(BAR_SECONDS * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE
    beat = BAR_SECONDS / BEATS_PER_BAR
    beat_phase = t % beat
    kick = 0.6 * np.sin(
        2 * np.pi * (50 + 120 * np.exp(-beat_phase / 0.03)) * beat_phase
    )
    kick *= np.exp(-beat_phase / 0.12)
    hat = 0.08 * rng.standard_normal(n) * np.exp(-(t % (beat / 2)) / 0.01)
    bars = []
    for part, count in STRUCTURE:
        for _ in range(count):
            chord = sum(
                np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t)
                for f in CHORDS[part]
            )
            chord = (
                chord * AMPLITUDE[part] * np.exp(-beat_phase / 0.3) / len(CHORDS[part])
            )
            bars.append(chord + kick + hat)
    return np.concatenate(bars).astype(np.float32)


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(
        self,
        method: str,
        path: str,
        *,
        json_body=None,
        data=None,
        headers=None,
        timeout=60,
    ):
        """Return (status, body bytes). HTTP errors are returned, not raised."""
        url = path if path.startswith("http") else self.base + path
        hdrs = dict(headers or {})
        if json_body is not None:
            data = json.dumps(json_body).encode()
            hdrs["Content-Type"] = "application/json"
        req = request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except error.HTTPError as exc:
            return exc.code, exc.read()

    def json(self, method: str, path: str, expect: int | tuple[int, ...], **kwargs):
        status, body = self.call(method, path, **kwargs)
        expected = (expect,) if isinstance(expect, int) else expect
        if status not in expected:
            raise SmokeError(
                f"{method} {path} -> {status} (expected {expected}): {body[:300]!r}"
            )
        return json.loads(body) if body else None

    def upload(self, path: Path) -> tuple[int, dict]:
        boundary = uuid.uuid4().hex
        head = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\nContent-Type: audio/wav\r\n\r\n'
        ).encode()
        body = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        status, raw = self.call(
            "POST",
            "/songs",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        if status not in (200, 201):
            raise SmokeError(f"POST /songs -> {status}: {raw[:300]!r}")
        return status, json.loads(raw)


def wait_job(client: Client, job_id: str, timeout: float, poll: float) -> dict:
    deadline = time.monotonic() + timeout
    last_stage = object()
    while True:
        job = client.json("GET", f"/jobs/{job_id}", 200)
        marker = (job["status"], job["stage"])
        if marker != last_stage:
            console.print(f"    [dim]{job['status']} / {job['stage']}[/dim]")
            last_stage = marker
        if job["status"] == "finished":
            return job
        if job["status"] == "failed":
            raise SmokeError(
                f"job {job_id} failed at stage {job['stage']}: {job['error']}"
            )
        if time.monotonic() > deadline:
            raise SmokeError(
                f"job {job_id} still {job['status']}/{job['stage']} after {timeout:.0f}s"
            )
        time.sleep(poll)


def run(args: argparse.Namespace, results: list[tuple[str, float, str]]) -> None:
    client = Client(args.api)
    workdir = Path(tempfile.mkdtemp(prefix="e2e-smoke-"))
    state: dict = {}

    def step(name):
        def decorator(fn):
            console.print(f"[bold]{name}[/bold]")
            start = time.monotonic()
            try:
                fn()
            except (
                SmokeError,
                AssertionError,
                OSError,
                zipfile.BadZipFile,
                KeyError,
            ) as exc:
                results.append((name, time.monotonic() - start, "FAIL"))
                raise SmokeError(
                    f"{name}: {exc!r}"
                    if not isinstance(exc, SmokeError)
                    else f"{name}: {exc}"
                )
            elapsed = time.monotonic() - start
            results.append((name, elapsed, "ok"))
            console.print(f"  ok in {elapsed:.1f}s")
            return fn

        return decorator

    @step("1. generate synthetic song")
    def _():
        audio = make_song(time.time_ns() % 2**32)
        state["wav"] = workdir / "smoke_song.wav"
        sf.write(state["wav"], audio, SAMPLE_RATE, subtype="PCM_16")
        console.print(f"    {len(audio) / SAMPLE_RATE:.1f}s -> {state['wav']}")

    @step("2. upload and reuse")
    def _():
        _, song = client.upload(state["wav"])
        assert not song["reused"], "first upload reported reused"
        state["song"] = song["id"]
        _status2, again = client.upload(state["wav"])
        assert again["reused"] and again["id"] == song["id"], (
            f"second upload not reused: {again}"
        )
        assert _status2 == 200, f"reused upload status {_status2}"

    sid = lambda: state["song"]

    @step("3. analyze with sections")
    def _():
        job = client.json(
            "POST", f"/songs/{sid()}/analyze", 202, json_body={"sections": True}
        )
        wait_job(client, job["job_id"], args.timeout, args.poll)
        analysis = client.json("GET", f"/songs/{sid()}/analysis", 200)
        grid = analysis.get("grid") or {}
        assert grid.get("beats") and grid.get("downbeats"), "analysis has no grid beats"
        console.print(f"    bpm {grid.get('bpm')}, {len(grid['downbeats'])} bars")
        sections = client.json("GET", f"/songs/{sid()}/sections", 200)
        assert sections["sections"], "no sections detected"
        assert not sections["edited"], "sections flagged edited before any edit"
        state["sections"] = sections

    @step("4. edit sections")
    def _():
        original = state["sections"]
        body = {
            "source": original["source"],
            "sections": [
                {k: v for k, v in s.items() if v is not None}
                for s in original["sections"]
            ],
        }
        body["sections"][-1]["label"] = EDITED_LABEL
        client.json("PUT", f"/songs/{sid()}/sections", 200, json_body=body)
        got = client.json("GET", f"/songs/{sid()}/sections", 200)
        assert got["edited"], "edited flag not set"
        assert got["sections"][-1]["label"] == EDITED_LABEL, "edited label not returned"

    @step("5. separate stems (htdemucs_6s)")
    def _():
        job = client.json(
            "POST", f"/songs/{sid()}/separate", 202, json_body={"model": "htdemucs_6s"}
        )
        wait_job(client, job["job_id"], args.separate_timeout, args.poll)

    @step("6. stage pack and ZIP checks")
    def _():
        options = {"destination": "daw", "count_in_bars": 2, "sample_rate": 48000}
        job = client.json("POST", f"/songs/{sid()}/stagepack", 202, json_body=options)
        done = wait_job(client, job["job_id"], args.timeout, args.poll)
        url = done.get("download_url")
        assert url, f"finished job has no download_url: {done}"
        status, payload = client.call("GET", url, timeout=300)
        assert status == 200, f"download -> {status}"
        zip_path = workdir / "pack.zip"
        zip_path.write_bytes(payload)
        console.print(f"    ZIP {len(payload) / 1e6:.1f} MB -> {zip_path}")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            wavs = [n for n in archive.namelist() if n.lower().endswith(".wav")]
            assert wavs, f"no WAVs in ZIP: {archive.namelist()}"
            frames = set()
            for name in wavs:
                with sf.SoundFile(io.BytesIO(archive.read(name))) as wav:
                    assert wav.samplerate == 48000, f"{name}: {wav.samplerate} Hz"
                    assert wav.subtype == "PCM_24", f"{name}: {wav.subtype}"
                    frames.add(wav.frames)
            assert len(frames) == 1, f"WAV frame counts differ: {sorted(frames)}"
            console.print(
                f"    {len(wavs)} WAVs, {frames.pop()} frames each, 48 kHz PCM_24"
            )
            sections_txt = archive.read("Secciones.txt").decode("utf-8")
            assert EDITED_LABEL in sections_txt, "Secciones.txt lacks the edited label"
        state["download_url"] = url

    @step("7. negative checks")
    def _():
        token = parse.urlsplit(state["download_url"]).path.rsplit("/", 1)[-1]
        tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        status, _ = client.call("GET", f"/files/{tampered}")
        assert status == 403, f"tampered token -> {status}, expected 403"
        status, _ = client.call("GET", f"/songs/{uuid.uuid4().hex}")
        assert status == 404, f"unknown song -> {status}, expected 404"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end smoke test against a running stack"
    )
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--timeout", type=float, default=900, help="seconds per analyze/stagepack job"
    )
    parser.add_argument(
        "--separate-timeout", type=float, default=3600, help="seconds for separation"
    )
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()

    results: list[tuple[str, float, str]] = []
    failure = None
    try:
        run(args, results)
    except SmokeError as exc:
        failure = str(exc)
    table = Table(title="E2E smoke summary")
    table.add_column("step")
    table.add_column("seconds", justify="right")
    table.add_column("result")
    for name, seconds, result in results:
        table.add_row(name, f"{seconds:.1f}", result)
    console.print(table)
    if failure:
        console.print(f"[red]FAILED[/red] {failure}")
        return 1
    console.print("[green]all steps passed[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
