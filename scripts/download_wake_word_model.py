#!/usr/bin/env python3
"""Download and verify the local sherpa-onnx wake word model."""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import ssl
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
ARCHIVE_NAME = f"{MODEL_NAME}.tar.bz2"
OFFICIAL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    f"kws-models/{ARCHIVE_NAME}"
)
DEFAULT_MODEL_ROOT = Path("models")
DEFAULT_DEST_DIR = DEFAULT_MODEL_ROOT / MODEL_NAME
DOWNLOAD_DIR_NAME = ".downloads"
PROXY_PREFIXES = (
    "https://gh-proxy.com/",
    "https://ghfast.top/",
)
REQUIRED_FILES = (
    "tokens.txt",
    "en.phone",
)
REQUIRED_GLOBS = (
    "encoder-*.onnx",
    "decoder-*.onnx",
    "joiner-*.onnx",
)


def build_source_candidates(
    *,
    custom_url: str = "",
    include_official: bool = True,
    include_proxies: bool = True,
) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    normalized_custom = str(custom_url or "").strip()
    if normalized_custom:
        candidates.append(("custom", normalized_custom))
    if include_official:
        candidates.append(("github", OFFICIAL_URL))
    if include_proxies:
        candidates.extend(
            (f"proxy:{prefix}", f"{prefix}{OFFICIAL_URL}") for prefix in PROXY_PREFIXES
        )
    return candidates


def resolve_ca_bundle() -> Tuple[Optional[str], str]:
    for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        candidate = str(os.environ.get(env_name, "")).strip()
        if candidate and Path(candidate).is_file():
            return candidate, f"env:{env_name}"

    for module_name, label in (
        ("certifi", "certifi"),
        ("pip._vendor.certifi", "pip._vendor.certifi"),
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        where = getattr(module, "where", None)
        if not callable(where):
            continue
        try:
            bundle = str(where()).strip()
        except Exception:
            continue
        if bundle and Path(bundle).is_file():
            return bundle, label

    return None, "system"


def create_ssl_context(*, verify: bool = True) -> Tuple[ssl.SSLContext, str]:
    if not verify:
        return ssl._create_unverified_context(), "insecure"

    ca_bundle, source = resolve_ca_bundle()
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle), source
    return ssl.create_default_context(), source


def verify_model_dir(model_dir: Path) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    if not model_dir.exists():
        return False, [f"directory:{model_dir}"]

    for name in REQUIRED_FILES:
        if not (model_dir / name).is_file():
            missing.append(name)
    for pattern in REQUIRED_GLOBS:
        if not any(model_dir.glob(pattern)):
            missing.append(pattern)
    return len(missing) == 0, missing


def download_file(
    url: str,
    destination: Path,
    *,
    timeout: int = 60,
    verify_ssl: bool = True,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    context, context_source = create_ssl_context(verify=verify_ssl)
    print(f"[wake-word] TLS 证书来源: {context_source}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"baodou-ai/{MODEL_NAME}"},
    )
    temp_path = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        with temp_path.open("wb") as file_obj:
            shutil.copyfileobj(response, file_obj)
    temp_path.replace(destination)


def extract_archive(archive_path: Path, destination_root: Path) -> Path:
    destination_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:bz2") as tar:
        tar.extractall(destination_root)
    return destination_root / MODEL_NAME


def download_and_extract(
    *,
    source_candidates: Sequence[Tuple[str, str]],
    archive_path: Path,
    destination_root: Path,
    keep_archive: bool,
    timeout: int,
    verify_ssl: bool,
) -> Path:
    errors: List[str] = []
    for label, url in source_candidates:
        print(f"[wake-word] 尝试下载源: {label}")
        try:
            download_file(
                url,
                archive_path,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )
            print(f"[wake-word] 下载完成: {archive_path}")
            model_dir = extract_archive(archive_path, destination_root)
            ok, missing = verify_model_dir(model_dir)
            if not ok:
                raise RuntimeError(f"模型文件不完整，缺少: {', '.join(missing)}")
            if not keep_archive and archive_path.exists():
                archive_path.unlink()
            print(f"[wake-word] 模型已就绪: {model_dir}")
            return model_dir
        except (urllib.error.URLError, TimeoutError, tarfile.TarError, RuntimeError) as exc:
            errors.append(f"{label}: {exc}")
            print(f"[wake-word] 下载失败: {exc}")
            if archive_path.exists():
                archive_path.unlink()
            partial_path = archive_path.with_suffix(archive_path.suffix + ".part")
            if partial_path.exists():
                partial_path.unlink()
    raise RuntimeError("所有下载源都失败了:\n- " + "\n- ".join(errors))


def _looks_like_tls_verify_error(exc: BaseException) -> bool:
    message = str(exc)
    return (
        "CERTIFICATE_VERIFY_FAILED" in message
        or "unable to get local issuer certificate" in message
        or "self signed certificate" in message.lower()
    )


def _looks_like_github_connectivity_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "connection reset by peer" in message
        or "timed out" in message
        or "remote end closed connection" in message
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载并校验 sherpa-onnx 本地语音唤醒模型。",
    )
    parser.add_argument(
        "--model-root",
        default=str(DEFAULT_MODEL_ROOT),
        help="模型根目录，默认是项目下的 models/",
    )
    parser.add_argument(
        "--url",
        default="",
        help="自定义下载地址，会优先于内置下载源尝试。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="单次下载连接超时时间，默认 90 秒。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使模型目录已存在也重新下载。",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="下载完成后保留 tar.bz2 压缩包。",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "github", "proxy"),
        default="auto",
        help="下载源策略：auto=官方+代理回退，github=仅官方，proxy=仅代理。",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="跳过 HTTPS 证书校验，仅在本机 Python 证书链异常且你确认下载源可信时使用。",
    )
    return parser.parse_args(argv)


def resolve_candidates(args: argparse.Namespace) -> List[Tuple[str, str]]:
    if args.source == "github":
        return build_source_candidates(
            custom_url=args.url,
            include_official=True,
            include_proxies=False,
        )
    if args.source == "proxy":
        return build_source_candidates(
            custom_url=args.url,
            include_official=False,
            include_proxies=True,
        )
    return build_source_candidates(
        custom_url=args.url,
        include_official=True,
        include_proxies=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    project_root = Path(__file__).resolve().parents[1]
    model_root = Path(args.model_root)
    if not model_root.is_absolute():
        model_root = (project_root / model_root).resolve()
    model_dir = model_root / MODEL_NAME

    if not args.force:
        ok, missing = verify_model_dir(model_dir)
        if ok:
            print(f"[wake-word] 模型已存在，无需下载: {model_dir}")
            return 0
        if model_dir.exists():
            print(f"[wake-word] 已发现模型目录，但文件不完整: {', '.join(missing)}")

    download_root = model_root / DOWNLOAD_DIR_NAME
    archive_path = download_root / ARCHIVE_NAME
    candidates = resolve_candidates(args)
    if not candidates:
        print("[wake-word] 未配置可用下载源。", file=sys.stderr)
        return 2

    try:
        final_dir = download_and_extract(
            source_candidates=candidates,
            archive_path=archive_path,
            destination_root=model_root,
            keep_archive=args.keep_archive,
            timeout=max(10, int(args.timeout)),
            verify_ssl=not args.insecure,
        )
    except Exception as exc:
        if _looks_like_tls_verify_error(exc) and not args.insecure:
            print(
                "[wake-word] 检测到 HTTPS 证书校验失败。"
                " 请优先确认当前解释器已安装/可访问 certifi，"
                " 或改用项目虚拟环境执行；如果你确认下载源可信，"
                " 可以重试：python3 scripts/download_wake_word_model.py --insecure",
                file=sys.stderr,
            )
        if args.source == "github" and (
            _looks_like_tls_verify_error(exc) or _looks_like_github_connectivity_error(exc)
        ):
            print(
                "[wake-word] 你的当前网络环境不适合直连官方 GitHub 下载。"
                " 建议直接改用代理源："
                " python3 scripts/download_wake_word_model.py --source proxy"
                " 或者不传 --source，使用默认 auto 自动回退。",
                file=sys.stderr,
            )
        print(f"[wake-word] 下载失败: {exc}", file=sys.stderr)
        return 1

    ok, missing = verify_model_dir(final_dir)
    if not ok:
        print(f"[wake-word] 模型校验失败，缺少: {', '.join(missing)}", file=sys.stderr)
        return 1

    print("[wake-word] 下载与校验完成。")
    print(f"[wake-word] 模型目录: {final_dir}")
    print("[wake-word] 当前默认模型路径配置与此目录兼容。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
