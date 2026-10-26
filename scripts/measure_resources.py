"""Measure wall time and worker memory for a long synthetic song against a running stack.

Run from the repository root (the compose stack must be up):

    uv run --project packages/audio-core python scripts/measure_resources.py \
        --api http://localhost:8000 --worker-container infra-worker-cpu-1

It builds a stereo song (default 240 s) from the e2e smoke generator, uploads it and runs analyze
(with sections), separate (htdemucs_6s) and stagepack one after another. While each job runs it
samples the worker container cgroup (memory.current and the anonymous part of memory.stat, once per
second) through one long-lived ``docker exec``. Anonymous memory is the real RSS-like cost; the
page cache part of memory.current is reclaimable under a memory limit. The worker is restarted
first so the cgroup ``memory.peak`` covers only these jobs. Idle memory of the other stack
containers is read with ``docker stats`` before and after. Only the standard library is used for
HTTP and Docker.
"""

import argparse
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_smoke as smoke  # noqa: E402  (reuses the song generator, HTTP client and job polling)

# 120 bars at 120 bpm (2 s per bar) = 240 s.
LONG_STRUCTURE = [
    ("intro", 8),
    ("A", 16),
    ("B", 16),
    ("A", 16),
    ("B", 16),
    ("A", 16),
    ("B", 16),
    ("A", 8),
    ("outro", 8),
]
SAMPLER = (
    "while true; do "
    "a=$(awk '/^anon /{print $2}' /sys/fs/cgroup/memory.stat); "
    "c=$(cat /sys/fs/cgroup/memory.current); echo \"$c $a\"; sleep 1; done"
)
MIB = 1024 * 1024


def make_stereo_song(seconds: float, seed: int) -> np.ndarray:
    """Stereo float32 song of at least ``seconds`` seconds (whole bars)."""
    total_bars = sum(count for _, count in LONG_STRUCTURE)
    smoke.STRUCTURE = LONG_STRUCTURE
    left = smoke.make_song(seed)
    right = smoke.make_song(seed + 1)
    song = np.stack([left, right], axis=1)
    want = int(seconds * smoke.SAMPLE_RATE)
    if len(song) < want:
        raise SystemExit(f"generator produced {len(song) / smoke.SAMPLE_RATE:.0f}s for {total_bars} bars")
    return song[:want]


class MemorySampler:
    """Streams ``current anon`` byte pairs from inside the worker container, one per second."""

    def __init__(self, container: str) -> None:
        self.proc = subprocess.Popen(
            ["docker", "exec", container, "sh", "-c", SAMPLER],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.samples: list[tuple[float, int, int]] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            parts = line.split()
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                with self._lock:
                    self.samples.append((time.monotonic(), int(parts[0]), int(parts[1])))

    def peak_since(self, start: float) -> tuple[float, float, int]:
        """(peak current MiB, peak anon MiB, sample count) for samples taken at or after ``start``."""
        with self._lock:
            window = [s for s in self.samples if s[0] >= start]
        if not window:
            return 0.0, 0.0, 0
        return max(s[1] for s in window) / MIB, max(s[2] for s in window) / MIB, len(window)

    def stop(self) -> None:
        self.proc.terminate()


def docker_text(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout.strip()


def idle_memory(project: str) -> dict[str, str]:
    """Container name -> 'MemUsage' for every container of the compose project."""
    names = docker_text("ps", "--filter", f"label=com.docker.compose.project={project}", "--format", "{{.Names}}")
    out: dict[str, str] = {}
    for name in names.splitlines():
        out[name] = docker_text("stats", "--no-stream", "--format", "{{.MemUsage}}", name)
    return out


def timed_job(client, sampler, label, start_call, wait_timeout, poll, rows):
    started = time.monotonic()
    job = start_call()
    done = smoke.wait_job(client, job["job_id"], wait_timeout, poll)
    wall = time.monotonic() - started
    peak_cur, peak_anon, n = sampler.peak_since(started)
    rows.append((label, wall, peak_cur, peak_anon, n))
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--worker-container", default="infra-worker-cpu-1")
    parser.add_argument("--project", default="infra", help="compose project name (idle memory report)")
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--separate-timeout", type=float, default=7200.0)
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--no-restart", action="store_true", help="do not restart the worker first")
    args = parser.parse_args()

    client = smoke.Client(args.api)
    workdir = Path(tempfile.mkdtemp(prefix="measure-"))
    wav = workdir / "long_song.wav"
    audio = make_stereo_song(args.seconds, time.time_ns() % 2**32)
    sf.write(wav, audio, smoke.SAMPLE_RATE, subtype="PCM_16")
    print(f"song: {len(audio) / smoke.SAMPLE_RATE:.0f}s stereo, {wav.stat().st_size / 1e6:.1f} MB -> {wav}")

    if not args.no_restart:
        docker_text("restart", args.worker_container)
        time.sleep(8)
    idle_before = idle_memory(args.project)

    _, song = client.upload(wav)
    sid = song["id"]
    sampler = MemorySampler(args.worker_container)
    time.sleep(3)
    rows: list[tuple[str, float, float, float, int]] = []
    try:
        timed_job(
            client, sampler, "analyze (sections)",
            lambda: client.json("POST", f"/songs/{sid}/analyze", 202, json_body={"sections": True}),
            args.timeout, args.poll, rows,
        )
        timed_job(
            client, sampler, "separate htdemucs_6s",
            lambda: client.json("POST", f"/songs/{sid}/separate", 202, json_body={"model": "htdemucs_6s"}),
            args.separate_timeout, args.poll, rows,
        )
        options = {"destination": "daw", "count_in_bars": 2, "sample_rate": 48000}
        timed_job(
            client, sampler, "stagepack",
            lambda: client.json("POST", f"/songs/{sid}/stagepack", 202, json_body=options),
            args.timeout, args.poll, rows,
        )
    finally:
        sampler.stop()
    lifetime_peak = int(docker_text("exec", args.worker_container, "cat", "/sys/fs/cgroup/memory.peak")) / MIB
    idle_after = idle_memory(args.project)

    print("\n| job | wall time | peak memory.current (MiB) | peak anon (MiB) | samples |")
    print("|---|---|---|---|---|")
    for label, wall, cur, anon, n in rows:
        print(f"| {label} | {wall:.0f} s | {cur:.0f} | {anon:.0f} | {n} |")
    print(f"\nworker cgroup memory.peak since restart: {lifetime_peak:.0f} MiB")
    print("\nidle memory before jobs:")
    for name, usage in idle_before.items():
        print(f"  {name}: {usage}")
    print("idle memory after jobs:")
    for name, usage in idle_after.items():
        print(f"  {name}: {usage}")


if __name__ == "__main__":
    main()
