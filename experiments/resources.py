"""Peak memory of an experiment run (KE_HOACH phase 4 "RAM đỉnh", Gate B0 2026-11-09). Read-only.

Two numbers, because the agent's memory lives in two places:
- the disposable container that runs the agent loop and holds the extracted package
  (cgroup `memory.peak`, read inside the container; peak since that container started, i.e. per batch);
- the model loaded by the host's Ollama (`/api/ps`: `size` total, `size_vram` on the GPU, so
  `size - size_vram` sits in system RAM), sampled on the host while the batch runs.
"""

import threading
from collections.abc import Callable
from pathlib import Path

MB = 1024 * 1024
CGROUP_FILES = (Path("/sys/fs/cgroup/memory.peak"),                         # cgroup v2 (Docker Desktop / WSL2)
                Path("/sys/fs/cgroup/memory/memory.max_usage_in_bytes"))     # cgroup v1


def container_peak_mb(files: tuple[Path, ...] = CGROUP_FILES) -> float | None:
    """Peak memory of the current cgroup in MB, or None when no counter is readable."""
    for path in files:
        try:
            return round(int(path.read_text(encoding="ascii").strip()) / MB, 1)
        except (OSError, ValueError):
            continue
    return None


def _ollama_ps() -> dict | None:
    from experiments.run_batch import _ollama
    return _ollama("/api/ps")


class OllamaSampler:
    """Background sampler of `/api/ps`; keeps the largest size and size_vram seen per model."""

    def __init__(self, interval: float = 2.0, ps: Callable[[], dict | None] = _ollama_ps) -> None:
        self.interval, self.ps = interval, ps
        self.peaks: dict[str, dict[str, float]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def sample(self) -> None:
        try:
            models = (self.ps() or {}).get("models") or []
        except Exception:  # a measurement must never stop the batch
            return
        for model in models:
            peak = self.peaks.setdefault(str(model.get("name")), {"size_mb": 0.0, "vram_mb": 0.0})
            peak["size_mb"] = max(peak["size_mb"], round((model.get("size") or 0) / MB, 1))
            peak["vram_mb"] = max(peak["vram_mb"], round((model.get("size_vram") or 0) / MB, 1))

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            self.sample()

    def __enter__(self) -> "OllamaSampler":
        self.sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 5)
        self.sample()


def merge_resources(old: dict | None, container_peaks: list[float | None], ollama: dict[str, dict]) -> dict:
    """Combine this call's measurements with those already in run_meta (resumed runs keep the max)."""
    old = old or {}
    seen = [value for value in [old.get("container_peak_mb"), *container_peaks] if value is not None]
    models = {name: dict(values) for name, values in (old.get("ollama") or {}).items()}
    for name, values in ollama.items():
        current = models.setdefault(name, {"size_mb": 0.0, "vram_mb": 0.0})
        for key in ("size_mb", "vram_mb"):
            current[key] = max(current.get(key, 0.0), values.get(key, 0.0))
    return {"container_peak_mb": max(seen) if seen else None, "ollama": models,
            "note": "container: cgroup memory.peak per batch; ollama: /api/ps sampled on the host"}
