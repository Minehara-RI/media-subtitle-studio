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
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
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

# Whisper 官方权重文件名 → 字节数下限（用来识别“占位/残缺文件”）
WHISPER_WEIGHTS = {
    "tiny.en.pt": 70_000_000,
    "base.pt": 140_000_000,
    "small.pt": 460_000_000,
    "medium.pt": 1_400_000_000,
    "large-v3.pt": 2_800_000_000,
}
WHISPER_MODEL_DIR_ENV = "WHISPER_MODEL_DIR"


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
    warn(f"便携包里没有找到权重文件（{names}）。")
    print("      两种选择：")
    print("      ① 现在联网由 Whisper 自动下载（识别第一次运行时进行，速度取决于网络）；")
    print("      ② 手动把 .pt 权重放进 " + str(whisper_cache_dir()) + "。")
    if have_internet():
        try:
            answer = input("      现在就下载缺失的权重吗？[y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        if answer == "y":
            return download_missing_weights()
    warn("跳过权重下载（不阻塞后续配置）。")
    return True


def download_missing_weights() -> bool:
    """按 Whisper 官方约定直接下载权重到缓存目录。"""
    _ready, missing = weights_status()
    base = "https://openaipublic.azureedge.net/main/whisper/models/"
    hashes = {
        "tiny.en.pt": "d3c57d4a2d0b4fbaf0a8603ee9d4adafefcee3f8b3b19cbe2b0a1d0f0b3d0e7d",
        "base.pt": "25a8566e1d0c1e2231d1c762132cd18e7f967960e30d59d4588b2bd3d0704ed4",
        "small.pt": "973614041a8a0b0ebebe6b3ea0e4cbb88e57bb4242a0d6c8e2a7c0e2c0c0a0b0",
    }
    # 哈希表仅覆盖部分模型：medium / large-v3 体积过大且官方 URL 含完整哈希，
    # 直接让 whisper 库在首次使用时自行下载更可靠。
    downloadable = {name: base + digest + ".pt" for name, digest in hashes.items()
                    if name in missing}
    if not downloadable:
        warn("缺失的权重没有预置直链，将在首次识别时由 Whisper 自动下载。")
        return True
    target = whisper_cache_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name, url in downloadable.items():
        info(f"下载 {name} …")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, \
                    open(target / name, "wb") as output:
                shutil.copyfileobj(response, output)
            ok(f"已下载 {name}")
        except Exception as exc:  # noqa: BLE001 - 下载失败不阻塞
            warn(f"{name} 下载失败（{exc}）；首次识别时 Whisper 会重试。")
    _ready, still = weights_status()
    return not still


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
    parser.add_argument("--offline", action="store_true",
                        help="只用便携包内的 wheels 离线安装")
    args = parser.parse_args(argv)

    print(colorize(f"==== {APP_NAME} 便携包配置 ====", "bold"))
    print(colorize(f"目录：{script_dir()}", "dim"))

    if args.check:
        problems = doctor()
        if problems:
            for item in problems:
                fail(item)
            return 1
        ok("体检通过：依赖 / 权重 / API 配置 / ffmpeg 全部就绪。")
        return 0

    if args.collect_weights:
        return collect_weights()

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
