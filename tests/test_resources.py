from experiments import resources


def test_container_peak_reads_first_readable_cgroup_counter(tmp_path):
    v2 = tmp_path / "memory.peak"
    v2.write_text(str(256 * 1024 * 1024) + "\n")
    assert resources.container_peak_mb((tmp_path / "missing", v2)) == 256.0
    (tmp_path / "bad").write_text("max\n")
    assert resources.container_peak_mb((tmp_path / "bad",)) is None


def test_sampler_keeps_largest_size_per_model_and_survives_errors():
    replies = iter([{"models": [{"name": "m", "size": 2 * resources.MB, "size_vram": resources.MB}]},
                    {"models": [{"name": "m", "size": 3 * resources.MB, "size_vram": 0}]},
                    None])

    def ps():
        reply = next(replies, None)
        if reply is None:
            raise OSError("ollama down")
        return reply

    with resources.OllamaSampler(interval=3600, ps=ps) as sampler:
        sampler.sample()
    assert sampler.peaks == {"m": {"size_mb": 3.0, "vram_mb": 1.0}}


def test_merge_keeps_max_across_resumed_runs():
    old = {"container_peak_mb": 400.0, "ollama": {"m": {"size_mb": 5.0, "vram_mb": 5.0}}}
    merged = resources.merge_resources(old, [None, 350.0], {"m": {"size_mb": 6.0, "vram_mb": 4.0}})
    assert merged["container_peak_mb"] == 400.0 and merged["ollama"]["m"] == {"size_mb": 6.0, "vram_mb": 5.0}
    assert resources.merge_resources(None, [None], {})["container_peak_mb"] is None
