from baodou_ai.core.task_memory_store import TaskMemoryStore


def test_task_memory_store_read_append_clear(tmp_path):
    memory_file = tmp_path / "memory.txt"
    store = TaskMemoryStore(memory_file=memory_file)

    assert store.read() == ""

    assert store.append("第一条记忆") is True
    assert store.append("第二条记忆") is True
    assert memory_file.read_text(encoding="utf-8") == "第一条记忆\n第二条记忆\n"
    assert store.read() == "第一条记忆\n第二条记忆"

    store.clear()
    assert memory_file.read_text(encoding="utf-8") == ""
    assert store.read() == ""


def test_task_memory_store_respects_runtime_resolver(tmp_path):
    path_state = {"path": tmp_path / "a" / "memory.txt"}
    store = TaskMemoryStore(memory_file_resolver=lambda: path_state["path"])

    store.append("alpha")
    assert path_state["path"].read_text(encoding="utf-8") == "alpha\n"

    path_state["path"] = tmp_path / "b" / "memory.txt"
    store.append("beta")
    assert (tmp_path / "a" / "memory.txt").read_text(encoding="utf-8") == "alpha\n"
    assert (tmp_path / "b" / "memory.txt").read_text(encoding="utf-8") == "beta\n"
