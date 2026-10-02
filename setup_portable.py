# -*- coding: utf-8 -*-
"""Media Subtitle Studio 便携包首次配置脚本（Setup.bat 调用；也可直接 python 运行）。

做四件事，全部可跳过、可重跑：
1. 建独立虚拟环境 .venv，安装程序运行所需的 pip 包（离线 wheels 优先）。
2. 把 Whisper 权重放进 %USERPROFILE%\\.cache\\whisper（程序按官方约定自动找到）。
3. 配置 api_settings.json：交互输入 API Key，或 --from-ref 从本机既有配置里取。
4. 用 AI 自检：调一次 chat/completions 确认 Key 可用，并让 AI 复核配置是否完整。

用法示例：
  python setup_portable.py                     # 全流程（缺什么补什么）
  python setup_portable.py --from-ref 默认     # API Key/URL 从本机 api_settings.json 的指定模型复制
  python setup_portable.py --no-whisper        # 不复制权重（首次识别时会自己下载）
  python setup_portable.py --only-env          # 只装依赖
  python setup_portable.py --check             # 只做体检，不改动
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import posixpath
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_NAME = "Media Subtitle Studio"
CONFIG_FILENAME = "api_settings.json"
VENV_DIRNAME = ".venv"

# 程序运行的最小依赖集（media_subtitle_studio.py 实测用到的部分）。
# 版本取下限，让 pip 自行解析最新兼容版；离线 wheels 目录里有的就优先离线装。
REQUIRED_PACKAGES = [
    "pillow>=10.0",
    "tkinterdnd2>=0.4",
    "opencv-python>=4.8",
    "numpy",
    "faster-whisper>=1.0",
    "requests",
]

_WHISPER_BASE = "https://openaipublic.azureedge.net/main/whisper/models/"
WHISPER_MODEL_DIR_ENV = "WHISPER_MODEL_DIR"

# Whisper 官方模型表：名称 → {url, sha256, size}。
# url 末段目录即官方 SHA-256（出处：openai/whisper 的 whisper/__init__.py _MODELS）。
# size 为官方字节数，用于「已下满就直接校验、不重复下载」。
WHISPER_MODELS: dict[str, dict[str, object]] = {
    "tiny.en.pt": {
        "url": _WHISPER_BASE + "d3dd57d32accea0b295c96e26691aa14d8822fac7d9d27d5dc00b4ca2826dd03/tiny.en.pt",
        "sha256": "d3dd57d32accea0b295c96e26691aa14d8822fac7d9d27d5dc00b4ca2826dd03",
        "size": 75_571_315,
    },
    "base.pt": {
        "url": _WHISPER_BASE + "ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt",
        "sha256": "ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e",
        "size": 145_262_807,
    },
    "small.pt": {
        "url": _WHISPER_BASE + "9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt",
        "sha256": "9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794",
        "size": 483_617_219,
    },
    "medium.pt": {
        "url": _WHISPER_BASE + "345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt",
        "sha256": "345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1",
        "size": 1_528_008_539,
    },
    "large-v3.pt": {
        "url": _WHISPER_BASE + "e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb/large-v3.pt",
        "sha256": "e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb",
        "size": 3_087_371_615,
    },
}

# 识别权重用文件名 → 字节数下限（用来识别「占位 / 残缺文件」）。
# 注意：这里刻意用「下限」而不是精确字节数，这样旧版本 / 略微不同的同名权重
# 也能被认出来，不会被误判成残缺而重下 1.5 GB。
# 下载时用的精确字节数在 WHISPER_MODELS[name]["size"] 里（用于断点续传判断）。
WHISPER_WEIGHTS = {
    "tiny.en.pt": 70_000_000,
    "base.pt": 140_000_000,
    "small.pt": 460_000_000,
    "medium.pt": 1_400_000_000,
    "large-v3.pt": 2_800_000_000,
}

# 下载权重时优先使用的模型名（轻量包默认不带权重，首次配置按这个顺序挑一个直链下载）。
PREFERRED_DOWNLOAD_ORDER = ("medium.pt", "small.pt", "base.pt", "tiny.en.pt")
WEIGHT_MIRROR_ENV = "MSS_WEIGHT_MIRROR"
WEIGHT_MIRROR = os.environ.get(WEIGHT_MIRROR_ENV, "").strip()
WEIGHT_DOWNLOAD_TIMEOUT = 60
WEIGHT_DOWNLOAD_TRIES = 3


def configure_stdio() -> None:
    """把标准输出 / 错误改成 UTF-8：Windows 管道默认 GBK，✓/✗ 会直接 UnicodeEncodeError。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            continue


def supports_ansi() -> bool:
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint(0)
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


ANSI = supports_ansi()
COLORS = {
    "green": "\033[92m" if ANSI else "",
    "yellow": "\033[93m" if ANSI else "",
    "red": "\033[91m" if ANSI else "",
    "cyan": "\033[96m" if ANSI else "",
    "dim": "\033[90m" if ANSI else "",
    "bold": "\033[1m" if ANSI else "",
    "reset": "\033[0m" if ANSI else "",
}


def colorize(text: str, color: str) -> str:
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def info(message: str) -> None:
    print(colorize(f"[·] {message}", "cyan"))


def ok(message: str) -> None:
    print(colorize(f"[✓] {message}", "green"))


def warn(message: str) -> None:
    print(colorize(f"[!] {message}", "yellow"))


def fail(message: str) -> None:
    print(colorize(f"[✗] {message}", "red"))


def script_dir() -> Path:
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return Path.cwd()


def venv_python_path() -> Path:
    return script_dir() / VENV_DIRNAME / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python")


def have_internet(timeout: float = 4.0) -> bool:
    try:
        socket.create_connection(("pypi.org", 443), timeout=timeout).close()
        return True
    except OSError:
        return False


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ============================================================
# 1. 虚拟环境与依赖
# ============================================================
def find_wheels_dir() -> Path | None:
    for name in ("wheels", "wheels_backup"):
        candidate = script_dir() / name
        if candidate.is_dir() and any(candidate.glob("*.whl")):
            return candidate
    return None


def ensure_venv(offline_wheels: bool) -> bool:
    """确保 .venv 存在且依赖齐；返回是否可用。"""
    python = venv_python_path()
    if not python.is_file():
        info("创建虚拟环境 .venv …")
        result = subprocess.run([sys.executable, "-m", "venv", str(script_dir() / VENV_DIRNAME)])
        if result.returncode or not python.is_file():
            fail(f"创建虚拟环境失败（退出码 {result.returncode}）。")
            return False
        ok(f"虚拟环境已创建：{python}")
    try:
        result = subprocess.run(
            [str(python), "-m", "pip", "--version"], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        result = None
    if result is None or result.returncode:
        info("升级虚拟环境内的 pip …")
        subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"],
                       check=False)
    missing = missing_packages(python)
    wheels_dir = find_wheels_dir()
    if not missing:
        ok("pip 依赖已齐全。")
        return True
    names = ", ".join(missing)
    if offline_wheels and wheels_dir is not None:
        info(f"离线安装 {len(missing)} 个包：{names}")
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index",
             "--find-links", str(wheels_dir), *missing], check=False)
        if result.returncode == 0:
            ok("离线安装完成。")
            missing = missing_packages(python)
            if not missing:
                return True
            warn(f"离线包覆盖不全，还缺：{', '.join(missing)}（转在线安装）")
    if not have_internet():
        fail(f"缺少依赖（{names}）且当前无网络。请联网后重跑 Setup.bat，"
             "或把 wheel 文件放进 wheels\\ 目录实现离线安装。")
        return False
    info(f"在线安装缺失的包：{names}")
    mirrors = [
        [],  # 官方源优先
        ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],   # 清华镜像（国内备用）
        ["-i", "https://mirrors.aliyun.com/pypi/simple"],     # 阿里镜像（国内备用）
    ]
    for mirror in mirrors:
        result = subprocess.run(
            [str(python), "-m", "pip", "install", *mirror, *missing], check=False)
        if result.returncode == 0:
            missing = missing_packages(python)
            if not missing:
                ok("依赖安装完成。")
                return True
    fail("依赖安装失败；请检查网络或手动执行：")
    print(f"      \"{python}\" -m pip install {' '.join(missing)}")
    return False


def missing_packages(python: Path) -> list[str]:
    """逐个 import 探测缺哪些包（比 pip check 快、也不容易被历史残留误导）。"""
    import importlib.util

    probes = {
        "PIL": "pillow>=10.0",
        "tkinterdnd2": "tkinterdnd2>=0.4",
        "cv2": "opencv-python>=4.8",
        "numpy": "numpy",
        "faster_whisper": "faster-whisper>=1.0",
        "requests": "requests",
    }
    script = (
        "import importlib.util, sys\n"
        "needed = []\n"
        "for mod in ('PIL', 'tkinterdnd2', 'cv2', 'numpy', 'faster_whisper', 'requests'):\n"
        "    try:\n"
        "        if importlib.util.find_spec(mod) is None:\n"
        "            needed.append(mod)\n"
        "    except Exception:\n"
        "        needed.append(mod)\n"
        "print(','.join(needed))\n"
    )
    try:
        result = subprocess.run([str(python), "-c", script], capture_output=True,
                                text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return list(probes.values())
    if result.returncode:
        return list(probes.values())
    modules = (result.stdout or "").strip()
    # 空输出 = 全部就绪（不能用 not modules 判失败）
    return [probes[name] for name in modules.split(",") if name in probes]


# ============================================================
# 2. Whisper 权重
# ============================================================
def whisper_cache_dir() -> Path:
    return Path.home() / ".cache" / "whisper"


def whisper_search_dirs() -> list[Path]:
    """程序本体（whisper_model_directories）认的权重目录 + 便携包自带 weights\\。"""
    dirs: list[Path] = []
    env_dir = os.environ.get(WHISPER_MODEL_DIR_ENV)
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        dirs.append(Path(local_app_data) / "Buzz" / "Buzz" / "Cache" / "models" / "whisper")
    dirs.append(whisper_cache_dir())
    bundled = script_dir() / "weights"
    if bundled not in dirs:
        dirs.append(bundled)
    return dirs


def bundled_weights_dir() -> Path | None:
    candidate = script_dir() / "weights"
    return candidate if candidate.is_dir() and any(candidate.glob("*.pt")) else None


# 体检不要求全家桶：有 medium / large-v3 任一即够日常识别（其余可联网自动下载）
WEIGHTS_REQUIRED_FOR_CHECK = ("medium.pt", "large-v3.pt")


def weights_status() -> tuple[list[Path], list[str]]:
    """返回 (就绪的权重路径, 缺失的权重名)。任一搜索目录里命中即算就绪。"""
    ready, missing = [], []
    for name, min_size in WHISPER_WEIGHTS.items():
        found = None
        for directory in whisper_search_dirs():
            candidate = directory / name
            try:
                if candidate.is_file() and candidate.stat().st_size >= min_size:
                    found = candidate
                    break
            except OSError:
                continue
        (ready if found else missing).append(found or name)
    return ready, missing


def weights_ready_for_check() -> bool:
    """体检口径：要求的权重里至少一个就绪。"""
    ready, _missing = weights_status()
    names = {path.name if isinstance(path, Path) else str(path) for path in ready}
    return any(name in names for name in WEIGHTS_REQUIRED_FOR_CHECK)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_size(num_bytes: float) -> str:
    if num_bytes >= 1024 ** 3:
        return f"{num_bytes / 1024 ** 3:.2f} GB"
    return f"{num_bytes / 1_048_576:,.0f} MB"


def candidate_weight_urls(name: str) -> list[str]:
    """官方直链在前，镜像（MSS_WEIGHT_MIRROR / --weight-mirror）在后，去重保序。"""
    spec = WHISPER_MODELS.get(name)
    if not spec:
        return []
    urls = [str(spec["url"])]
    if WEIGHT_MIRROR:
        urls.append(WEIGHT_MIRROR.rstrip("/") + "/" + posixpath.basename(str(spec["url"])))
    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    return seen


def _retry_wait(attempt: int, attempts: int, exc: Exception) -> None:
    warn(f"连接失败（第 {attempt}/{attempts} 次）：{exc}；3 秒后重试…")
    time.sleep(3)


def _open_with_retry(url: str, offset: int, attempts: int = WEIGHT_DOWNLOAD_TRIES):
    """打开 url；offset > 0 时用 Range 续传。返回 (响应, 状态码, 实际起点的 offset)。

    - 起点失效（416）或服务器不支持 Range（非 206）时，自动退回从 0 重下，不消耗重试次数；
    - 网络错误才消耗重试次数，用满 attempts 次后抛出。
    """
    last_error: Exception | None = None
    used = 0
    while used < attempts:
        used += 1
        request = urllib.request.Request(
            url, headers={"User-Agent": "MediaSubtitleStudio-Setup/1.0"})
        if offset > 0:
            request.add_header("Range", f"bytes={offset}-")
        try:
            response = urllib.request.urlopen(request, timeout=WEIGHT_DOWNLOAD_TIMEOUT)
        except urllib.error.HTTPError as exc:
            if offset > 0 and exc.code == 416:
                # 起点超出文件长度：多半是本地 .part 已经下满，从头再来一次。
                exc.close()
                offset = 0
                used -= 1
                continue
            last_error = exc
            if used < attempts:
                _retry_wait(used, attempts, exc)
            continue
        except Exception as exc:  # noqa: BLE001 - 逐个重试，最后统一报错
            last_error = exc
            if used < attempts:
                _retry_wait(used, attempts, exc)
            continue
        status = getattr(response, "status", 200) or 200
        if offset > 0 and status != 206:
            # 服务器不支持断点续传：只能从 0 重来。
            response.close()
            warn("服务器不支持断点续传，从头上重新下载…")
            offset = 0
            used -= 1
            continue
        return response, status, offset
    raise RuntimeError(f"无法连接：{last_error}")


def fetch_weight(name: str, target_dir: Path) -> bool:
    """下载单个权重：支持断点续传 + SHA-256 校验 + 镜像回退。成功返回 True。

    完成判定以服务器给的 Content-Length 为准（.part 累计字节数），
    这样即使本地预置的 size 有细微出入也不会把下满的文件误判成中断。
    """
    spec = WHISPER_MODELS.get(name)
    if not spec:
        fail(f"没有 {name} 的官方直链，请手动放入 {target_dir}")
        return False
    expected_hash = str(spec["sha256"])
    expected_size = int(spec["size"])
    destination = target_dir / name
    partial = target_dir / (name + ".part")

    if destination.is_file() and destination.stat().st_size == expected_size:
        info(f"{name} 已存在，校验 SHA-256…")
        if sha256_of(destination) == expected_hash:
            ok(f"{name} 校验通过，跳过下载。")
            return True
        warn(f"{name} 已存在但校验不符，重新下载。")
        destination.unlink()
    elif partial.is_file() and partial.stat().st_size > expected_size:
        partial.unlink()

    for url in candidate_weight_urls(name):
        info(f"下载 {name}（{human_size(expected_size)}）…")
        info(f"  源：{url}")
        try:
            total = expected_size
            done = False
            for attempt in range(1, WEIGHT_DOWNLOAD_TRIES + 1):
                offset = partial.stat().st_size if partial.is_file() else 0
                if offset >= total:
                    # 已下满，只是还没改名 / 校验（例如上次正好下完就被打断）。
                    done = True
                    break
                response, _status, offset = _open_with_retry(url, offset)
                header = response.headers.get("Content-Length")
                if offset > 0:
                    info(f"  断点续传：从 {human_size(offset)} 继续（第 {attempt}/{WEIGHT_DOWNLOAD_TRIES} 次）。")
                else:
                    info(f"  开始下载（第 {attempt}/{WEIGHT_DOWNLOAD_TRIES} 次）。")
                if header and str(header).isdigit():
                    total = int(header) + offset
                written = offset
                started = time.time()
                last_report = started
                with response, open(partial, "ab" if offset else "wb") as output:
                    while True:
                        block = response.read(1024 * 512)
                        if not block:
                            break
                        output.write(block)
                        written += len(block)
                        now = time.time()
                        if now - last_report >= 2.0:
                            last_report = now
                            elapsed = max(now - started, 1e-6)
                            speed = (written - offset) / elapsed / 1_048_576
                            percent = min(written / total * 100, 100) if total else 0.0
                            sys.stdout.write(
                                f"\r      {percent:5.1f}%  {human_size(written)} / "
                                f"{human_size(total)}  {speed:6.1f} MB/s   ")
                            sys.stdout.flush()
                sys.stdout.write("\r" + " " * 78 + "\r")
                if written >= total:
                    done = True
                    break
                warn(f"  连接中断（已收 {human_size(written)} / {human_size(total)}），准备续传…")
            if not done:
                warn(f"{name} 多次中断，换下一个源…")
                continue
            info(f"  校验 {name} 的 SHA-256…")
            actual_hash = sha256_of(partial)
            if actual_hash != expected_hash:
                fail(f"  校验失败：期望 {expected_hash[:12]}…，实际 {actual_hash[:12]}…")
                partial.unlink()
                warn(f"{name} 校验不通过，换下一个源…")
                continue
            partial.replace(destination)
            ok(f"已下载并校验通过：{name} → {destination}")
            return True
        except Exception as exc:  # noqa: BLE001 - 一个源失败就换下一个
            warn(f"  该源失败：{exc}")
            continue

    fail(f"{name} 所有下载源都失败了。")
    print(f"      可手动下载后放进 {target_dir}")
    print(f"      官方地址：{WHISPER_MODELS[name]['url']}")
    if partial.is_file():
        print(colorize(f"      已保留未完成的文件 {partial.name}，下次重跑会自动续传。", "dim"))
    return False


def download_missing_weights(names: list[str] | None = None) -> bool:
    """下载缺失权重到缓存目录。支持断点续传、SHA-256 校验、镜像回退。

    names 为空时：优先下载 medium.pt（便携轻量包的默认大模型），
    已就绪就跳过；一个都没下成时才退到 small / base / tiny.en。
    """
    _ready, missing = weights_status()
    missing_names = {str(item) for item in missing if isinstance(item, str)}

    if names is None:
        # 只补缺失的：medium 优先，没有就退到更小的模型，避免白下 1.46 GB。
        names = [name for name in PREFERRED_DOWNLOAD_ORDER if name in missing_names]

    target = whisper_cache_dir()
    target.mkdir(parents=True, exist_ok=True)
    info(f"权重缓存目录：{target}")

    downloaded = False
    for name in names:
        # 点名的权重直接走 fetch_weight（内部会校验，一致就跳过）。
        if fetch_weight(name, target):
            downloaded = True

    _ready, still = weights_status()
    ok_names = {path.name for path in _ready if isinstance(path, Path)}
    if ok_names & set(WEIGHTS_REQUIRED_FOR_CHECK):
        return True
    if downloaded:
        return True
    warn(f"仍未就绪（缺失：{', '.join(str(item) for item in still)}）。")
    return False


def install_weights(auto: bool) -> bool:
    ready, missing = weights_status()
    for path in ready:
        try:
            size_mb = path.stat().st_size / 1_048_576
            ok(f"权重就绪：{path.name}（{size_mb:,.0f} MB）")
        except OSError:
            pass
    if not missing:
        return True
    if auto:
        warn(f"缺少权重 {len(missing)} 个（--no-whisper 模式不复制）；"
             "首次识别时 Whisper 会自动联网下载。")
        return True
    bundled = bundled_weights_dir()
    if bundled is not None:
        info(f"从便携包内复制权重：{bundled.name}\\")
        target = whisper_cache_dir()
        target.mkdir(parents=True, exist_ok=True)
        for name in missing:
            source = bundled / name
            if source.is_file():
                shutil.copy2(source, target / name)
                ok(f"已复制 {name}")
        _ready, missing = weights_status()
        if not missing:
            return True
    names = ", ".join(str(item) for item in missing if isinstance(item, str))
    info(f"便携包里未附带权重（{names}）——轻量包默认不带，首次配置时按需下载。")
    print("      两种选择：")
    print("      ① 现在下载（推荐；支持断点续传，中断后重跑 Setup.bat 会自动续传）；")
    print("      ② 跳过，稍后把 .pt 权重放进 " + str(whisper_cache_dir()) + "。")
    if not have_internet():
        warn("当前没有网络，跳过权重下载。")
        return True
    try:
        answer = input("      现在就下载权重吗？[Y/n] ").strip().lower()
    except EOFError:
        answer = ""
    if answer in ("", "y", "yes"):
        return download_missing_weights()
    warn("已跳过权重下载；下载好权重后重跑 Setup.bat 即可。")
    return True


def collect_weights() -> int:
    """把本机已缓存的 Whisper 权重复制进便携包 weights\\ 目录（供打包 / 离线部署）。"""
    ready, _missing = weights_status()
    if not ready:
        fail("本机没有找到任何可用的 Whisper 权重（%USERPROFILE%\\.cache\\whisper、"
             "Buzz 缓存、WHISPER_MODEL_DIR）。")
        return 1
    target = script_dir() / "weights"
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in ready:
        if not isinstance(path, Path):
            continue
        destination = target / path.name
        try:
            if destination.is_file() and destination.stat().st_size == path.stat().st_size:
                ok(f"已有副本：{path.name}")
                continue
            info(f"复制 {path.name}（{path.stat().st_size / 1_048_576:,.0f} MB）…")
            shutil.copy2(path, destination)
            copied += 1
        except OSError as exc:
            warn(f"{path.name} 复制失败：{exc}")
    ok(f"weights\\ 目录就绪（本次新复制 {copied} 个）。打包时带上它即可离线。")
    return 0


# ============================================================
# 3. API 配置（api_settings.json）
# ============================================================
def valid_model(model) -> bool:
    return (isinstance(model, dict) and model.get("name") and model.get("url")
            and model.get("api_key") and model.get("model"))


def load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def ref_model_from_local(ref: str) -> dict | None:
    """从“本机既有配置”（脚本所在目录 / 程序库目录 / 用户主目录）找指定名字的模型。"""
    bases = [script_dir().parent,
             Path(__file__).resolve().parent.parent,
             Path.home() / "Documents" / "Pys",
             Path.home()]
    seen: set[Path] = set()
    for base in bases:
        try:
            path = (base / CONFIG_FILENAME).resolve()
        except OSError:
            continue
        if path in seen:
            continue
        seen.add(path)
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        for model in data.get("models") or []:
            if not valid_model(model):
                continue
            if not ref or ref in ("默认", "default", "*") \
                    or str(model.get("name")) == ref:
                ok(f"从 {path} 取到模型「{model.get('name')}」的完整配置。")
                return dict(model)
    return None


def prompt_api_setup() -> dict | None:
    """交互式收集 API 配置；回车使用默认值。"""
    print()
    info("配置 AI 翻译模型（OpenAI 兼容接口；直接回车 = 使用括号里的默认值）")
    name = input("  配置名称 [DeepSeek]：").strip() or "DeepSeek"
    url = input("  API 地址 [https://api.deepseek.com/v1/chat/completions]：").strip() \
        or "https://api.deepseek.com/v1/chat/completions"
    model_id = input("  模型 ID [deepseek-chat]：").strip() or "deepseek-chat"
    api_key = ""
    while not api_key:
        api_key = input("  API Key（必填）: ").strip()
        if not api_key:
            print("  API Key 不能为空（可用 --from-ref 从本机既有配置复制，避免手输）。")
    concurrency = input("  并发数 [10]：").strip() or "10"
    try:
        concurrency = max(1, min(100, int(concurrency)))
    except ValueError:
        concurrency = 10
    return {"name": name, "url": url, "api_key": api_key,
            "model": model_id, "max_concurrent": concurrency}


def ensure_api_config(from_ref: str | None) -> dict | None:
    """便携包内的 api_settings.json；返回包含至少一个有效模型的配置 dict。

    zip 里带的是 api_settings.template.json（不含密钥）；首次配置时若只有模板，
    就以它为基础，让用户只填 Key 或用 --from-ref 从本机既有配置复制。
    """
    path = script_dir() / CONFIG_FILENAME
    data = load_json(path)
    if not (isinstance(data, dict) and any(valid_model(m) for m in data.get("models") or [])):
        template = load_json(script_dir() / "api_settings.template.json")
        if isinstance(template, dict):
            data = template          # 模板里没有可用 Key，只当骨架用
    if isinstance(data, dict) and any(valid_model(m) for m in data.get("models") or []):
        ok(f"API 配置已存在：{path.name}（{len(data['models'])} 个模型）")
        return data
    info("便携包里还没有可用的 API 配置。")
    model = None
    if from_ref is not None:
        model = ref_model_from_local(from_ref)
        if model is None:
            warn(f"--from-ref {from_ref!r} 在本机既有配置里没有找到可用模型。")
    if model is None and sys.stdin is not None and sys.stdin.isatty():
        model = prompt_api_setup()
    if model is None:
        # 无交互（双击 bat）时给出手动路径，不卡死流程
        warn("未配置 API 模型（双击运行无法交互）。请编辑 "
             f"{path} 填入 api_key 后重跑，或用命令行参数：")
        print(f"      setup_portable.py --from-ref 模型名   （从本机既有配置复制）")
        print(f"      setup_portable.py --api-url <url> --api-key <key> --api-model <id>")
        return None
    data = data if isinstance(data, dict) else {}
    models = [m for m in data.get("models", []) if valid_model(m)]
    models = [m for m in models if m.get("name") != model.get("name")]
    models.insert(0, model)
    data["models"] = models
    data["default_model"] = model["name"]
    write_json(path, data)
    ok(f"API 配置已写入：{path}（默认模型 {model['name']}）")
    return data


# ============================================================
# 4. AI 自检 / AI 复核配置
# ============================================================
def ai_self_check(config: dict) -> bool:
    """调一次 chat/completions：Key 可用性 + 让 AI 复核配置完整性。"""
    models = [m for m in config.get("models") or [] if valid_model(m)]
    if not models:
        warn("没有可用的 AI 模型，跳过 AI 自检。")
        return False
    model = models[0]
    info(f"AI 自检：调用 {model['name']}（{model['model']}）…")
    payload = json.dumps({
        "model": model["model"],
        "messages": [
            {"role": "system", "content": "你是配置检查助手。只输出一行 JSON。"},
            {"role": "user", "content": (
                "请检查这份本地字幕工具配置是否完整，只输出一行 JSON："
                "{\"ok\": true/false, \"notes\": \"一句话说明\"}。"
                f"配置：api 地址 {model['url']}，模型 {model['model']}，"
                f"并发 {model.get('max_concurrent', 10)}，"
                "用途 = Whisper 语音识别 + AI 字幕翻译（OpenAI 兼容 chat/completions）。")},
        ],
        "temperature": 0.0,
        "max_tokens": 120,
    }).encode("utf-8")
    request = urllib.request.Request(
        model["url"], data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {model['api_key']}"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = result.get("usage") or {}
        ok(f"API 连通（tokens {usage.get('total_tokens', '?')}）")
        print(f"      AI 复核意见：{content.strip()[:300]}")
        return True
    except Exception as exc:  # noqa: BLE001 - 自检失败只警告
        warn(f"AI 自检失败：{exc}")
        warn("配置未生效或网络问题；修正 api_settings.json 后重跑 Setup.bat 即可。")
        return False


# ============================================================
# 汇总
# ============================================================
def doctor() -> list[str]:
    """体检：返回问题清单（空 = 全部就绪）。"""
    problems: list[str] = []
    python = venv_python_path()
    if not python.is_file():
        problems.append("虚拟环境 .venv 不存在（依赖未安装）")
    else:
        missing = missing_packages(python)
        if missing:
            problems.append("缺少 pip 包：" + ", ".join(missing))
    if not weights_ready_for_check():
        _ready, missing_weights = weights_status()
        problems.append("Whisper 权重缺失（至少需要 medium.pt 或 large-v3.pt 之一）："
                        + ", ".join(str(item) for item in missing_weights))
    data = load_json(script_dir() / CONFIG_FILENAME)
    if not (isinstance(data, dict) and any(valid_model(m) for m in data.get("models") or [])):
        problems.append("api_settings.json 没有可用的 AI 模型配置")
    if not have_ffmpeg():
        problems.append("PATH 里找不到 ffmpeg（识别 / 压制必需；"
                        "请安装 FFmpeg 并加入 PATH，或把 ffmpeg.exe 所在目录加入 PATH）")
    return problems


def main(argv=None) -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(description=f"{APP_NAME} 便携包首次配置")
    parser.add_argument("--from-ref", metavar="模型名",
                        help="API 配置从本机既有 api_settings.json 的指定模型复制"
                             "（“默认”= 取第一个）")
    parser.add_argument("--api-url", help="直接指定 API 地址")
    parser.add_argument("--api-key", help="直接指定 API Key")
    parser.add_argument("--api-model", help="直接指定模型 ID")
    parser.add_argument("--no-whisper", action="store_true",
                        help="跳过权重复制 / 下载")
    parser.add_argument("--only-env", action="store_true", help="只装 pip 依赖")
    parser.add_argument("--check", action="store_true", help="只体检，不改动")
    parser.add_argument("--collect-weights", action="store_true",
                        help="把本机已缓存的 Whisper 权重复制进 weights\\ 目录（打包用）")
    parser.add_argument("--download-weights", metavar="模型名", nargs="?", const="auto",
                        help="只下载权重（默认 medium.pt；也可 tiny.en / base / small / medium / large-v3）")
    parser.add_argument("--weight-mirror", metavar="地址",
                        help="权重镜像地址（默认官方 CDN；如 https://hf-mirror.com 等自建镜像）")
    parser.add_argument("--offline", action="store_true",
                        help="只用便携包内的 wheels 离线安装")
    args = parser.parse_args(argv)

    global WEIGHT_MIRROR
    if args.weight_mirror:
        WEIGHT_MIRROR = args.weight_mirror.strip()

    print(colorize(f"==== {APP_NAME} 便携包配置 ====", "bold"))
    print(colorize(f"目录：{script_dir()}", "dim"))

    if args.check:
        problems = doctor()
        if problems:
            for item in problems:
                fail(item)
            if not args.no_whisper and not weights_ready_for_check() and have_internet():
                print(colorize("    提示：加 --download-weights 可以现在就下载权重（支持断点续传）。", "dim"))
            return 1
        ok("体检通过：依赖 / 权重 / API 配置 / ffmpeg 全部就绪。")
        return 0

    if args.collect_weights:
        return collect_weights()

    if args.download_weights:
        alias = args.download_weights
        if alias == "auto":
            names = None
        else:
            names = [alias if alias.endswith(".pt") else alias + ".pt"]
            unknown = [name for name in names if name not in WHISPER_MODELS]
            if unknown:
                fail(f"未知权重名：{', '.join(unknown)}；"
                     f"可选：{', '.join(WHISPER_MODELS)}")
                return 1
        return 0 if download_missing_weights(names) else 1

    if not ensure_venv(offline_wheels=args.offline):
        return 1

    if args.only_env:
        ok("--only-env 完成。")
        return 0

    if not args.no_whisper:
        install_weights(auto=False)
    else:
        warn("--no-whisper：跳过权重（首次识别时自动下载）")

    config = ensure_api_config(args.from_ref)
    if config is None:
        return 1
    if args.api_url or args.api_key:
        models = [m for m in config.get("models", []) if valid_model(m)]
        if models:
            if args.api_url:
                models[0]["url"] = args.api_url.strip()
            if args.api_key:
                models[0]["api_key"] = args.api_key.strip()
            if args.api_model:
                models[0]["model"] = args.api_model.strip()
            write_json(script_dir() / CONFIG_FILENAME, config)
            ok("已用命令行参数更新 API 配置。")

    ai_self_check(config)

    print()
    problems = doctor()
    if problems:
        warn("还有未就绪项：")
        for item in problems:
            print(colorize(f"    - {item}", "yellow"))
        print(colorize("    修正后重跑 Setup.bat 即可继续。", "dim"))
        return 2
    ok("全部就绪！双击 Start-MediaSubtitleStudio.bat 即可使用。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(130)
