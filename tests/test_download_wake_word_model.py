import ssl
from types import SimpleNamespace
from pathlib import Path

from scripts.download_wake_word_model import (
    MODEL_NAME,
    OFFICIAL_URL,
    PROXY_PREFIXES,
    build_source_candidates,
    create_ssl_context,
    main,
    resolve_ca_bundle,
    verify_model_dir,
)


def _create_minimal_model_dir(root: Path) -> Path:
    model_dir = root / MODEL_NAME
    model_dir.mkdir(parents=True)
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    (model_dir / "en.phone").write_text("lexicon", encoding="utf-8")
    (model_dir / "encoder-epoch-13.onnx").write_text("x", encoding="utf-8")
    (model_dir / "decoder-epoch-13.onnx").write_text("x", encoding="utf-8")
    (model_dir / "joiner-epoch-13.onnx").write_text("x", encoding="utf-8")
    return model_dir


def test_build_source_candidates_includes_official_and_proxies():
    candidates = build_source_candidates()

    assert candidates[0] == ("github", OFFICIAL_URL)
    assert candidates[1][0].startswith("proxy:")
    assert candidates[1][1] == f"{PROXY_PREFIXES[0]}{OFFICIAL_URL}"
    assert candidates[2][1] == f"{PROXY_PREFIXES[1]}{OFFICIAL_URL}"


def test_build_source_candidates_prioritizes_custom_url():
    custom_url = "https://example.com/model.tar.bz2"

    candidates = build_source_candidates(custom_url=custom_url)

    assert candidates[0] == ("custom", custom_url)


def test_verify_model_dir_detects_complete_directory(tmp_path):
    model_dir = _create_minimal_model_dir(tmp_path)

    ok, missing = verify_model_dir(model_dir)

    assert ok is True
    assert missing == []


def test_verify_model_dir_detects_missing_files(tmp_path):
    model_dir = tmp_path / MODEL_NAME
    model_dir.mkdir()
    (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")

    ok, missing = verify_model_dir(model_dir)

    assert ok is False
    assert "en.phone" in missing
    assert "encoder-*.onnx" in missing


def test_resolve_ca_bundle_prefers_environment_variable(tmp_path, monkeypatch):
    ca_bundle = tmp_path / "ca.pem"
    ca_bundle.write_text("fake-cert", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(ca_bundle))

    bundle, source = resolve_ca_bundle()

    assert bundle == str(ca_bundle)
    assert source == "env:SSL_CERT_FILE"


def test_resolve_ca_bundle_falls_back_to_pip_vendor(monkeypatch):
    def fake_import_module(name):
        if name == "certifi":
            raise ImportError("missing certifi")
        if name == "pip._vendor.certifi":
            return SimpleNamespace(where=lambda: "/tmp/pip-certifi.pem")
        raise ImportError(name)

    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.setattr(
        "scripts.download_wake_word_model.importlib",
        SimpleNamespace(import_module=fake_import_module),
    )
    monkeypatch.setattr(
        "scripts.download_wake_word_model.Path.is_file",
        lambda self: str(self) == "/tmp/pip-certifi.pem",
    )

    bundle, source = resolve_ca_bundle()

    assert bundle == "/tmp/pip-certifi.pem"
    assert source == "pip._vendor.certifi"


def test_create_ssl_context_supports_insecure_mode():
    context, source = create_ssl_context(verify=False)

    assert isinstance(context, ssl.SSLContext)
    assert source == "insecure"
    assert context.verify_mode == ssl.CERT_NONE


def test_main_returns_success_when_model_already_exists(tmp_path):
    model_root = tmp_path / "models"
    _create_minimal_model_dir(model_root)

    exit_code = main(["--model-root", str(model_root)])

    assert exit_code == 0
