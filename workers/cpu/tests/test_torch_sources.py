"""Guard against drift between the two copies of the CPU-only torch source block.

uv only honors ``[tool.uv.sources]`` / ``[[tool.uv.index]]`` of the project being locked, so
``packages/audio-core`` (dev) and ``workers/cpu`` (Docker image) each repeat the block. If they
diverge, the image silently resolves a different torch build than the one developed against.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROJECTS = {
    "audio-core": ROOT / "packages" / "audio-core" / "pyproject.toml",
    "worker-cpu": ROOT / "workers" / "cpu" / "pyproject.toml",
}
TORCH_PACKAGES = ("torch", "torchaudio")


def _uv(path: Path) -> dict:
    return tomllib.loads(path.read_text())["tool"]["uv"]


def _cpu_index(uv: dict) -> dict:
    return next(i for i in uv["index"] if i["name"] == "pytorch-cpu")


def test_both_projects_declare_the_cpu_index_identically():
    indexes = {name: _cpu_index(_uv(path)) for name, path in PROJECTS.items()}
    assert indexes["audio-core"] == indexes["worker-cpu"]
    assert indexes["worker-cpu"]["explicit"] is True
    assert indexes["worker-cpu"]["url"].endswith("/whl/cpu")


def test_both_projects_pin_torch_sources_to_the_cpu_index():
    for package in TORCH_PACKAGES:
        sources = {name: _uv(path)["sources"][package] for name, path in PROJECTS.items()}
        assert sources["audio-core"] == sources["worker-cpu"], package
        assert sources["worker-cpu"] == [
            {"index": "pytorch-cpu", "marker": "sys_platform == 'linux'"}
        ]


def test_worker_lock_resolves_torch_from_the_cpu_index_only():
    lock = (ROOT / "workers" / "cpu" / "uv.lock").read_text()
    assert "download.pytorch.org/whl/cpu" in lock
    assert "download.pytorch.org/whl/cu" not in lock
