import json

from baodou_ai.core.runtime_artifact_store import RuntimeArtifactStore


def test_runtime_artifact_store_context_debug_round_increments_and_resets(tmp_path):
    debug_dir = tmp_path / "context_debug"
    store = RuntimeArtifactStore(context_debug_dir=debug_dir)
    messages = [{"role": "user", "content": "hello"}]

    store.write_context_debug("round 1", messages)
    store.write_context_debug("round 2", messages)

    files = sorted(debug_dir.glob("*.json"))
    assert len(files) == 2
    payload_1 = json.loads(files[0].read_text(encoding="utf-8"))
    payload_2 = json.loads(files[1].read_text(encoding="utf-8"))
    assert payload_1["round"] == 1
    assert payload_2["round"] == 2

    store.clear_context_debug()
    assert list(debug_dir.glob("*.json")) == []

    store.write_context_debug("round 1 again", messages)
    payload_3 = json.loads(next(debug_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload_3["round"] == 1


def test_runtime_artifact_store_context_debug_round_is_store_scoped(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    store_a = RuntimeArtifactStore(context_debug_dir=dir_a)
    store_b = RuntimeArtifactStore(context_debug_dir=dir_b)

    store_a.write_context_debug("a-1", [{"role": "user", "content": "A1"}])
    store_b.write_context_debug("b-1", [{"role": "user", "content": "B1"}])
    store_a.write_context_debug("a-2", [{"role": "user", "content": "A2"}])

    payload_a = sorted(json.loads(path.read_text(encoding="utf-8"))["round"] for path in dir_a.glob("*.json"))
    payload_b = sorted(json.loads(path.read_text(encoding="utf-8"))["round"] for path in dir_b.glob("*.json"))
    assert payload_a == [1, 2]
    assert payload_b == [1]
