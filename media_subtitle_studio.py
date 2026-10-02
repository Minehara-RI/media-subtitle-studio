#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Media Subtitle Studio: GUI and CLI for local ASR, AI translation and muxing."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import ctypes
import difflib
from enum import Enum, auto
import functools
from html.parser import HTMLParser
import importlib
import importlib.util
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import urllib.error
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

try:
    _tkinterdnd2 = importlib.import_module("tkinterdnd2")
    DND_FILES = _tkinterdnd2.DND_FILES
    TkinterDnD = _tkinterdnd2.TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

try:
    Image = importlib.import_module("PIL.Image")
    ImageDraw = importlib.import_module("PIL.ImageDraw")
    ImageFont = importlib.import_module("PIL.ImageFont")
    ImageTk = importlib.import_module("PIL.ImageTk")
except ImportError:
    Image = ImageDraw = ImageFont = ImageTk = None

try:
    cv2 = importlib.import_module("cv2")
except ImportError:
    cv2 = None

# 说明：字幕解析 / 生成 / 并发翻译内核已内嵌到本文件（见“内嵌字幕核心”一节），
# 不再 import S_subtitles.py；下面保持 `subtitles.*` 的调用方式不变。


APP_TITLE = "Media Subtitle Studio"
MEDIA_EXTENSIONS = {
    ".3gp", ".aac", ".avi", ".flac", ".m4a", ".m4v", ".mka", ".mkv",
    ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".opus", ".wav",
    ".webm", ".wma", ".wmv",
}
SUBTITLE_EXTENSIONS = {".ass", ".smi", ".srt", ".ssa", ".sub", ".vtt"}
SUBTITLE_IMPORT_ENTRY = "导入外部字幕文件…"
# 「输出 / 压制的字幕」列表里可选的条目（可同时选多条 → 多条字幕轨）
MUX_TRACK_ORIGINAL = "生成 · 原文"
MUX_TRACK_TRANSLATED = "生成 · 译文"
MUX_TRACK_BILINGUAL = "生成 · 双语"
MUX_TRACK_EXTERNAL = "外部字幕文件…"
MUX_TRACK_KINDS = (MUX_TRACK_ORIGINAL, MUX_TRACK_TRANSLATED, MUX_TRACK_BILINGUAL,
                   MUX_TRACK_EXTERNAL)
MUX_TRACK_MODES = {MUX_TRACK_ORIGINAL: "原文", MUX_TRACK_TRANSLATED: "译文",
                   MUX_TRACK_BILINGUAL: "双语"}
SUBTITLE_OUTPUT_SUFFIX = {"原文": "original", "译文": "translated", "双语": "bilingual"}
LANGUAGES = {
    "自动检测": "auto",
    "中文（简体）": "Simplified Chinese (简体中文)",
    "中文（繁體）": "Traditional Chinese (繁體中文)",
    "English": "English",
    "日本語": "Japanese (日本語)",
    "한국어": "Korean (한국어)",
    "Français": "French (Français)",
    "Deutsch": "German (Deutsch)",
    "Español": "Spanish (Español)",
    "Português": "Portuguese (Português)",
    "Русский": "Russian (Русский)",
    "Italiano": "Italian (Italiano)",
    "العربية": "Arabic (العربية)",
    "हिन्दी": "Hindi (हिन्दी)",
    "ไทย": "Thai (ไทย)",
    "Tiếng Việt": "Vietnamese (Tiếng Việt)",
    "Bahasa Indonesia": "Indonesian (Bahasa Indonesia)",
    "Bahasa Melayu": "Malay (Bahasa Melayu)",
    "Türkçe": "Turkish (Türkçe)",
    "Nederlands": "Dutch (Nederlands)",
    "Polski": "Polish (Polski)",
    "Українська": "Ukrainian (Українська)",
    "Svenska": "Swedish (Svenska)",
    "Norsk": "Norwegian (Norsk)",
    "Dansk": "Danish (Dansk)",
    "Suomi": "Finnish (Suomi)",
    "Ελληνικά": "Greek (Ελληνικά)",
    "עברית": "Hebrew (עברית)",
    "Čeština": "Czech (Čeština)",
    "Română": "Romanian (Română)",
    "Magyar": "Hungarian (Magyar)",
    "فارسی": "Persian (فارسی)",
    "বাংলা": "Bengali (বাংলা)",
    "اردو": "Urdu (اردو)",
    "Filipino": "Filipino",
    "繁體中文（香港）": "Traditional Chinese (Hong Kong) (繁體中文，香港)",
}
WHISPER_LANGUAGE_CODES = {
    "English": "en", "中文（简体）": "zh", "中文（繁體）": "zh",
    "繁體中文（香港）": "zh", "日本語": "ja", "한국어": "ko",
    "Français": "fr", "Deutsch": "de", "Español": "es",
    "Português": "pt", "Русский": "ru", "Italiano": "it",
    "العربية": "ar", "हिन्दी": "hi", "ไทย": "th",
    "Tiếng Việt": "vi", "Bahasa Indonesia": "id", "Bahasa Melayu": "ms",
    "Türkçe": "tr", "Nederlands": "nl", "Polski": "pl",
    "Українська": "uk", "Svenska": "sv", "Norsk": "no",
    "Dansk": "da", "Suomi": "fi", "Ελληνικά": "el", "עברית": "he",
    "Čeština": "cs", "Română": "ro", "Magyar": "hu", "فارسی": "fa",
    "বাংলা": "bn", "اردو": "ur", "Filipino": "tl",
}
WHISPER_MODELS = ("tiny", "tiny.en", "base", "small", "medium", "large-v3")
if cv2 is not None:
    CAP_PROP_POS_MSEC = cv2.CAP_PROP_POS_MSEC
    CAP_PROP_POS_FRAMES = cv2.CAP_PROP_POS_FRAMES
    CAP_PROP_FRAME_COUNT = cv2.CAP_PROP_FRAME_COUNT
    CAP_PROP_FPS = cv2.CAP_PROP_FPS
else:
    CAP_PROP_POS_MSEC = CAP_PROP_POS_FRAMES = 0
    CAP_PROP_FRAME_COUNT = CAP_PROP_FPS = 0
FONT_PATHS = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)
PALETTE = {
    "bg": "#eef2ef",
    "surface": "#ffffff",
    "surface_alt": "#f5f9f6",
    "border": "#d9e2db",
    "ink": "#1d2c26",
    "muted": "#68786f",
    "accent": "#0b7d5b",
    "accent_hover": "#096a4d",
    "accent_soft": "#dff0e8",
    "drop_idle": "#e3efe8",
    "drop_hover": "#cae4d5",
    "preview": "#0e1512",
    "preview_text": "#d6e4dc",
}
UI_FONT_STACK = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Tahoma")
LOG_FONT_STACK = ("Cascadia Mono", "Consolas", "Courier New")


# ============================================================
# 内嵌字幕核心（原 S_subtitles.py 中本程序用到的部分，已解除文件依赖）
#   - API 配置读取 / 多编码读取 / 格式检测 / 解析器 / 生成器
#   - 并发 AI 翻译（单条 / 整段、重试、token 统计、取消）
# ============================================================
CONFIG_FILENAME = "api_settings.json"

# ---------- 语言标记 ----------
AUTO_SOURCE_LANG = "auto"
AUTO_SOURCE_ALIASES = {"auto", "自动识别", "自动", "detect", "autodetect", "Auto"}

TRANSLATION_RETRIES = 2         # 每条/每批请求失败后的额外重试次数（网络错误/限流/5xx）
REQUEST_TIMEOUT = 300           # 单次 API 请求超时（秒）
CONTEXT_LINE_MAX_CHARS = 300    # 上下文单行最大字符数（防止 prompt 过大）

MAX_OUTPUT_TOKENS_SINGLE = 8000     # 单条模式输出上限
BATCH_TOKENS_PER_LINE = 1000        # 整段模式：每行预留输出 token
MAX_OUTPUT_TOKENS_BATCH_CAP = 32000 # 整段模式输出上限

BATCH_SIZE_MIN = 2              # 每批最少行数
BATCH_SIZE_MAX = 50             # 每批最多行数
DEFAULT_BATCH_SIZE = 30         # 每次启动的默认值（会话级，不持久化）

DEFAULT_CONTEXT_LINES = 5       # 翻译上下文：前后各 N 条非空字幕（仅参考，不翻译）
CONTEXT_LINES_MAX = 10          # 上下文句数上限


def get_config_path() -> Path:
    """配置文件 = 程序同目录下的 api_settings.json"""
    if getattr(sys, "frozen", False):          # PyInstaller 打包后取 exe 所在目录
        base = Path(sys.executable).parent
    else:
        try:
            base = Path(__file__).resolve().parent
        except NameError:
            base = Path.cwd()
    return base / CONFIG_FILENAME


def _valid_model(model) -> bool:
    return bool(isinstance(model, dict)
                and model.get("name") and model.get("url")
                and model.get("api_key") and model.get("model"))


def load_config():
    """读取配置；不存在 / 损坏 / 无有效模型时返回 None"""
    path = get_config_path()
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(config, dict):
        return None
    models = [item for item in config.get("models", []) if _valid_model(item)]
    if not models:
        return None
    config["models"] = models
    if config.get("default_model") not in {item["name"] for item in models}:
        config["default_model"] = models[0]["name"]
    return config


# ------------------------------------------------------------ 时间工具
def ms_to_srt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def ms_to_vtt_time(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{millis:03d}"


def ms_to_ass_time(ms: int) -> str:
    ms = max(0, int(ms))
    total_cs = (ms + 5) // 10
    h = total_cs // 360000
    m = (total_cs % 360000) // 6000
    s = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def parse_srt_time(s: str) -> int:
    s = s.strip().replace(',', '.')
    parts = s.split(':')
    if len(parts) != 3:
        raise ValueError(f"Invalid SRT time: {s!r}")
    try:
        h, m = int(parts[0]), int(parts[1])
        sec_parts = parts[2].split('.')
        sec = int(sec_parts[0])
        ms = int(sec_parts[1].ljust(3, '0')[:3])
    except (ValueError, IndexError):
        raise ValueError(f"Invalid SRT time: {s!r}")
    return h * 3600000 + m * 60000 + sec * 1000 + ms


def parse_vtt_time(s: str) -> int:
    s = s.strip()
    parts = s.split(':')
    try:
        if len(parts) == 2:
            h, m, rest = 0, int(parts[0]), parts[1]
        elif len(parts) == 3:
            h, m, rest = int(parts[0]), int(parts[1]), parts[2]
        else:
            raise ValueError
        sec_parts = rest.split('.')
        sec = int(sec_parts[0])
        ms = int(sec_parts[1].ljust(3, '0')[:3])
    except (ValueError, IndexError):
        raise ValueError(f"Invalid VTT time: {s!r}")
    return h * 3600000 + m * 60000 + sec * 1000 + ms


def parse_lrc_time(s: str) -> int:
    s = s.strip().strip('[').strip(']')
    parts = s.split(':')
    try:
        if len(parts) == 3:
            h, m, sec_str = int(parts[0]), int(parts[1]), parts[2]
        elif len(parts) == 2:
            h, m, sec_str = 0, int(parts[0]), parts[1]
        else:
            raise ValueError
        sec_parts = sec_str.split('.')
        sec = int(sec_parts[0])
        cs = int(sec_parts[1].ljust(2, '0')[:2]) if len(sec_parts) > 1 else 0
    except (ValueError, IndexError):
        raise ValueError(f"Invalid LRC time: {s!r}")
    return h * 3600000 + m * 60000 + sec * 1000 + cs * 10


def parse_ass_time(s: str) -> int:
    s = s.strip()
    parts = s.split(':')
    try:
        if len(parts) == 3:
            h, m, sec_str = int(parts[0]), int(parts[1]), parts[2]
        elif len(parts) == 2:
            h, m, sec_str = 0, int(parts[0]), parts[1]
        else:
            raise ValueError
        sec_parts = sec_str.split('.')
        sec = int(sec_parts[0])
        cs = int(sec_parts[1].ljust(2, '0')[:2]) if len(sec_parts) > 1 else 0
    except (ValueError, IndexError):
        raise ValueError(f"Invalid ASS time: {s!r}")
    return h * 3600000 + m * 60000 + sec * 1000 + cs * 10


# ------------------------------------------------------------ 格式枚举 / 读取 / 检测
class SubFormat(Enum):
    SRT = auto()
    LRC = auto()
    VTT = auto()
    ASS = auto()
    SSA = auto()
    SUB = auto()   # MicroDVD
    SMI = auto()   # SAMI
    TXT = auto()   # 纯文本（仅输出用）

    def __str__(self):
        return self.name


def read_file_content(filepath):
    """多编码尝试读取文本文件（与 S_subtitles 行为一致）"""
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'big5',
                 'shift-jis', 'euc-kr', 'cp949', 'utf-16',
                 'cp1252', 'latin-1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as handle:
                return handle.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
        except OSError as exc:
            raise RuntimeError(f"无法读取文件: {exc}")
    with open(filepath, 'r', encoding='latin-1', errors='replace') as handle:
        return handle.read()


def detect_format(filepath) -> SubFormat:
    ext = Path(filepath).suffix.lower()
    if ext == '.srt':
        return SubFormat.SRT
    if ext == '.lrc':
        return SubFormat.LRC
    if ext in ('.vtt', '.webvtt'):
        return SubFormat.VTT
    if ext == '.ass':
        return SubFormat.ASS
    if ext == '.ssa':
        return SubFormat.SSA
    if ext == '.sub':
        content = read_file_content(filepath)[:500]
        low = content.lower()
        if '<sami' in low or '<sync' in low:       # .sub 可能实际是 SAMI
            return SubFormat.SMI
        return SubFormat.SUB
    if ext in ('.smi', '.sami'):
        return SubFormat.SMI

    content = read_file_content(filepath)[:500]
    low = content.lower()
    if re.search(r'\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,.]\d{3}', content):
        return SubFormat.SRT
    if re.search(r'\[\d{1,3}:\d{2}\.\d{1,3}\]', content):
        return SubFormat.LRC
    if 'webvtt' in low[:100]:
        return SubFormat.VTT
    if '[script info]' in low[:300]:
        return SubFormat.ASS
    if re.search(r'\{(\d+)\}\{(\d+)\}', content):
        return SubFormat.SUB
    if '<sami>' in low[:300] or '<sync' in low[:500]:
        return SubFormat.SMI
    return SubFormat.SRT


# ------------------------------------------------------------ 解析器
class SubtitleParser:
    """把任意支持格式解析为统一条目: {index,start_ms,end_ms,text,style,actor}"""

    @staticmethod
    def parse(filepath, fmt=None):
        if fmt is None:
            fmt = detect_format(filepath)
        content = read_file_content(filepath)
        parsers = {
            SubFormat.SRT: SubtitleParser._parse_srt,
            SubFormat.LRC: SubtitleParser._parse_lrc,
            SubFormat.VTT: SubtitleParser._parse_vtt,
            SubFormat.ASS: SubtitleParser._parse_ass,
            SubFormat.SSA: SubtitleParser._parse_ass,
            SubFormat.SUB: SubtitleParser._parse_sub,
            SubFormat.SMI: SubtitleParser._parse_smi,
        }
        parser = parsers.get(fmt)
        if parser is None:
            raise ValueError(f"Unsupported input format: {fmt}")
        return parser(content, filepath)

    @staticmethod
    def _parse_srt(content, filepath):
        entries = []
        pattern = re.compile(
            r'(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*'
            r'(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})[^\n]*\n'
            r'((?:(?!\n\n|\n\d+\s*\n).)+)',
            re.DOTALL
        )
        for m in pattern.finditer(content):
            try:
                start = parse_srt_time(m.group(1))
                end = parse_srt_time(m.group(2))
            except ValueError:
                continue
            entries.append({
                'index': len(entries) + 1,
                'start_ms': start,
                'end_ms': end,
                'text': m.group(3).strip(),
                'style': None,
                'actor': None,
            })
        return entries

    @staticmethod
    def _parse_lrc(content, filepath):
        entries = []
        tag_re = re.compile(r'\[(\d{1,3}:\d{2}(?:\.\d{1,3})?)\]')
        head_re = re.compile(r'^((?:\[\d{1,3}:\d{2}(?:\.\d{1,3})?\])+)(.*)$')
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            m = head_re.match(line)
            if not m:
                continue
            text = m.group(2).strip()
            for ts in tag_re.findall(m.group(1)):        # 支持一行多个时间标签
                try:
                    ms = parse_lrc_time(ts)
                except ValueError:
                    continue
                entries.append({
                    'index': 0,
                    'start_ms': ms,
                    'end_ms': ms + 3000,
                    'text': text,
                    'style': None,
                    'actor': None,
                })
        entries.sort(key=lambda e: e['start_ms'])
        for i in range(len(entries) - 1):
            nxt = entries[i + 1]['start_ms'] - 10
            if nxt > entries[i]['start_ms']:
                entries[i]['end_ms'] = min(entries[i]['end_ms'], nxt)
        for i, e in enumerate(entries, 1):
            e['index'] = i
        return entries

    @staticmethod
    def _parse_vtt(content, filepath):
        entries = []
        content = re.sub(r'^WEBVTT[^\n]*\n+', '', content, count=1)
        content = re.sub(r'^NOTE.*?\n\n', '', content, flags=re.DOTALL | re.MULTILINE)
        content = re.sub(r'^STYLE\n.*?\n\n', '', content, flags=re.DOTALL | re.MULTILINE)
        content = re.sub(r'^REGION\n.*?\n\n', '', content, flags=re.DOTALL | re.MULTILINE)
        pattern = re.compile(
            r'((?:\d{1,2}:)?\d{2}:\d{2}\.\d{1,3})\s*-->\s*'
            r'((?:\d{1,2}:)?\d{2}:\d{2}\.\d{1,3})[^\n]*\n'
            r'((?:(?!\n\n).)+)',
            re.DOTALL
        )
        for m in pattern.finditer(content):
            try:
                start = parse_vtt_time(m.group(1))
                end = parse_vtt_time(m.group(2))
            except ValueError:
                continue
            text = m.group(3).strip()
            text = re.sub(r'</?[^>]+>', '', text)        # 清除 v/c/b/i 等 HTML 标签
            entries.append({
                'index': len(entries) + 1,
                'start_ms': start,
                'end_ms': end,
                'text': text,
                'style': None,
                'actor': None,
            })
        return entries

    @staticmethod
    def _parse_ass(content, filepath):
        entries = []
        in_events = False
        for line in content.split('\n'):
            line = line.strip()
            if line.lower().startswith('[events]'):
                in_events = True
                continue
            if line.startswith('[') and in_events:
                in_events = False
                continue
            if not in_events:
                continue
            if not line.startswith('Dialogue:'):
                continue
            _, _, rest = line.partition(':')
            parts = rest.split(',', 8)
            if len(parts) < 9:
                continue
            start_str = parts[1].strip()
            end_str = parts[2].strip()
            style_name = parts[3].strip()
            actor = parts[4].strip()
            text = parts[8]
            text = re.sub(r'\{[^}]*\}', '', text)        # 去除 ASS 特效标签
            text = (text.replace('\\N', '\n').replace('\\n', '\n')
                        .replace('\\h', ' ').strip())
            try:
                entries.append({
                    'index': len(entries) + 1,
                    'start_ms': parse_ass_time(start_str),
                    'end_ms': parse_ass_time(end_str),
                    'text': text,
                    'style': style_name if style_name else None,
                    'actor': actor if actor else None,
                })
            except ValueError:
                continue
        return entries

    @staticmethod
    def _parse_sub(content, filepath):
        entries = []
        pattern = re.compile(r'\{(\d+)\}\{(\d+)\}(.*?)(?=\n\{|$)', re.DOTALL)
        fps = 23.976
        first_line = content.split('\n', 1)[0]
        m0 = re.match(r'^\{\d+\}\{\d+\}(\d+(?:\.\d+)?)\s*$', first_line.strip())
        if m0:
            try:
                f = float(m0.group(1))
                if 1.0 <= f <= 240.0:
                    fps = f
            except ValueError:
                pass
        for m in pattern.finditer(content):
            start_frame = int(m.group(1))
            end_frame = int(m.group(2))
            text = m.group(3).strip().replace('|', '\n')
            if re.fullmatch(r'\d+(?:\.\d+)?', text):     # 跳过 fps 声明行本身
                continue
            entries.append({
                'index': len(entries) + 1,
                'start_ms': int(start_frame / fps * 1000),
                'end_ms': int(end_frame / fps * 1000),
                'text': text,
                'style': None,
                'actor': None,
            })
        return entries

    @staticmethod
    def _parse_smi(content, filepath):
        entries = []
        pattern = re.compile(
            r'<SYNC\s+Start\s*=\s*(\d+)[^>]*>(.*?)(?=<SYNC|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        matches = list(pattern.finditer(content))
        for i, m in enumerate(matches):
            start_ms = int(m.group(1))
            body = re.sub(r'<!--.*?-->', '', m.group(2), flags=re.DOTALL)
            text_parts = re.findall(r'<P[^>]*>(.*?)</P>', body, re.DOTALL | re.IGNORECASE)
            text = '\n'.join(t.strip() for t in text_parts if t.strip())
            if not text:
                text_parts = re.findall(r'>([^<]+)<', body, re.DOTALL)
                text = ' '.join(t.strip() for t in text_parts if t.strip())
            text = re.sub(r'<[^>]+>', '', text)
            text = (text.replace('&nbsp;', ' ').replace('&lt;', '<')
                        .replace('&gt;', '>').replace('&quot;', '"')
                        .replace('&amp;', '&')).strip()
            if i + 1 < len(matches):
                end_ms = int(matches[i + 1].group(1))
            else:
                end_ms = start_ms + 3000
            entries.append({
                'index': i + 1,
                'start_ms': start_ms,
                'end_ms': max(end_ms, start_ms),
                'text': text,
                'style': None,
                'actor': None,
            })
        return entries


# ------------------------------------------------------------ 生成器
class SubtitleGenerator:
    """输出 SRT / VTT / ASS(SSA)，行为与 S_subtitles 一致"""

    @staticmethod
    def generate(entries, fmt, original_format=None):
        generators = {
            SubFormat.SRT: SubtitleGenerator._gen_srt,
            SubFormat.VTT: SubtitleGenerator._gen_vtt,
            SubFormat.ASS: SubtitleGenerator._gen_ass,
            SubFormat.SSA: SubtitleGenerator._gen_ass,
        }
        gen = generators.get(fmt)
        if gen is None:
            raise ValueError(f"Unsupported output format: {fmt}")
        return gen(entries, original_format)

    @staticmethod
    def _gen_srt(entries, original_format=None):
        lines = []
        for i, e in enumerate(entries, 1):
            lines.append(str(i))
            lines.append(f"{ms_to_srt_time(e['start_ms'])} --> "
                         f"{ms_to_srt_time(e['end_ms'])}")
            lines.append(e['text'])
            lines.append('')
        return '\n'.join(lines)

    @staticmethod
    def _gen_vtt(entries, original_format=None):
        lines = ['WEBVTT', '']
        for i, e in enumerate(entries, 1):
            lines.append(str(i))
            lines.append(f"{ms_to_vtt_time(e['start_ms'])} --> "
                         f"{ms_to_vtt_time(e['end_ms'])}")
            lines.append(e['text'])
            lines.append('')
        return '\n'.join(lines)

    @staticmethod
    def _gen_ass(entries, original_format=None):
        lines = []
        lines.append('[Script Info]')
        lines.append('Title: Converted Subtitle')
        lines.append('ScriptType: v4.00+')
        lines.append('WrapStyle: 2')
        lines.append('PlayResX: 1920')
        lines.append('PlayResY: 1080')
        lines.append('')
        lines.append('[V4+ Styles]')
        lines.append('Format: Name, Fontname, Fontsize, PrimaryColour, '
                     'SecondaryColour, OutlineColour, BackColour, Bold, '
                     'Italic, Underline, StrikeOut, ScaleX, ScaleY, '
                     'Spacing, Angle, BorderStyle, Outline, Shadow, '
                     'Alignment, MarginL, MarginR, MarginV, Encoding')
        lines.append('Style: Default,Arial,48,&H00FFFFFF,&H000000FF,'
                     '&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,'
                     '10,10,10,1')
        lines.append('')
        lines.append('[Events]')
        lines.append('Format: Layer, Start, End, Style, Name, MarginL, '
                     'MarginR, MarginV, Effect, Text')
        for e in entries:
            start = ms_to_ass_time(e['start_ms'])
            end = ms_to_ass_time(e['end_ms'])
            style = e.get('style') or 'Default'
            actor = e.get('actor') or ''
            text = e['text'].replace('\n', '\\N')
            lines.append(f'Dialogue: 0,{start},{end},{style},{actor},'
                         f'0,0,0,,{text}')
        return '\n'.join(lines) + '\n'


# ============================================================
# 并发 AI 翻译（OpenAI 兼容接口）
#  - _chat_completion        : 底层请求（重试 / token 统计 / max_tokens 自适应）
#  - translate_text          : 单条翻译
#  - translate_batch_text    : 整段（多行合并）翻译
#  - translate_entries_concurrent : 调度入口（单条 / 整段两种模式）
# ============================================================
token_lock = threading.Lock()
total_prompt_tokens = 0
total_completion_tokens = 0
total_total_tokens = 0


def _add_tokens(tokens):
    global total_prompt_tokens, total_completion_tokens, total_total_tokens
    with token_lock:
        total_prompt_tokens += tokens[0]
        total_completion_tokens += tokens[1]
        total_total_tokens += tokens[2]


def get_token_stats():
    with token_lock:
        return (total_prompt_tokens, total_completion_tokens, total_total_tokens)


def _chat_completion(model_cfg, system_prompt, user_content, max_tokens):
    """
    底层 chat/completions 调用。
    返回 (content, (prompt_tokens, completion_tokens, total_tokens))。
    - 网络错误 / 429 / 5xx 自动重试 TRANSLATION_RETRIES 次
    - 4xx 中疑似 max_tokens/上下文超限 → 自动减半再试一次（最低 2000）
    """
    api_key = (model_cfg.get("api_key") or "").strip()
    url = (model_cfg.get("url") or "").strip()
    model = (model_cfg.get("model") or "").strip()
    if not api_key:
        raise ValueError("该模型未配置 API Key")
    if not url:
        raise ValueError("该模型未配置 API 地址")
    if not model:
        raise ValueError("该模型未配置模型名称")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    base_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
    }

    cur_max_tokens = int(max_tokens)
    halved = False
    last_err = None

    for attempt in range(TRANSLATION_RETRIES + 1):
        payload = dict(base_payload)
        payload["max_tokens"] = cur_max_tokens
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                result = json.loads(response.read().decode('utf-8'))
            choices = result.get('choices') or []
            if not choices:
                console_echo("AI", f"{model} · 响应缺少 choices：{str(result)[:300]}")
                raise RuntimeError(f"API 响应缺少 choices: {str(result)[:200]}")
            content = (choices[0].get('message', {}).get('content') or '').strip()
            if not content:
                console_echo("AI", f"{model} · 返回空内容：{str(result)[:300]}")
                raise RuntimeError("API 返回了空结果")
            usage = result.get('usage', {}) or {}
            tokens = (usage.get('prompt_tokens', 0),
                      usage.get('completion_tokens', 0),
                      usage.get('total_tokens', 0))
            console_echo("AI", f"{model} · tokens {tokens[0]}+{tokens[1]}={tokens[2]}")
            console_echo("AI", content)
            return content, tokens
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', errors='replace')
            except Exception:
                body = ""
            console_echo("AI", f"{model} · HTTP {e.code}：{body[:300]}")
            err = RuntimeError(f"API 错误 {e.code}: {body[:300]}")
            if 400 <= e.code < 500 and e.code != 429:    # 参数/密钥错误默认不重试
                low = body.lower()
                if (not halved and cur_max_tokens > 2000
                        and ('max_tokens' in low or 'max output' in low
                             or 'context length' in low or 'maximum' in low)):
                    cur_max_tokens = max(2000, cur_max_tokens // 2)  # 疑似超限 → 减半重试
                    halved = True
                    last_err = err
                    continue
                raise err
            last_err = err
        except Exception as e:
            console_echo("AI", f"{model} · 请求失败：{type(e).__name__}: {e}")
            last_err = RuntimeError(f"网络错误: {e}")
        if attempt < TRANSLATION_RETRIES:
            time.sleep(1.0 * (attempt + 1))
    if last_err is None:                       # 正常流程到不了这里；兜底并收窄类型
        last_err = RuntimeError("翻译请求失败")
    raise last_err


def _strip_wrapping_quotes(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'“”‘’":
        return s[1:-1].strip()
    return s


def translate_text(text, source_lang, target_lang, model_cfg, context_lines=""):
    """单条翻译。返回 (译文, (prompt, completion, total))"""
    if context_lines:
        user_content = (
            f"Context (for reference only, do not translate):\n"
            f"{context_lines}\n\n"
            f"Current subtitle line to translate:\n{text}"
        )
    else:
        user_content = text

    is_auto = isinstance(source_lang, str) and source_lang.strip().lower() in AUTO_SOURCE_ALIASES
    if is_auto:
        src_desc = "detect the source language of the subtitle automatically"
    else:
        src_desc = f"translate the given subtitle text from {source_lang}"

    system_prompt = (
        f"You are a professional subtitle translator. "
        f"You must {src_desc} into {target_lang}. "
        f"Preserve formatting such as line breaks (\\n). "
        f"Use the provided context lines to understand the meaning and maintain consistency, "
        f"but only translate the 'Current subtitle line to translate'. "
        f"Do not translate the context lines. "
        f"Output ONLY the translated current line, with no extra quotes or explanations."
    )

    translated, tokens = _chat_completion(model_cfg, system_prompt, user_content,
                                          MAX_OUTPUT_TOKENS_SINGLE)
    return _strip_wrapping_quotes(translated), tokens


def _parse_batch_response(content, expected_numbers):
    """从模型输出中解析 [n] 译文 行，返回 {n: 译文}（仅接受期望编号，重复取首个）"""
    result = {}
    for m in re.finditer(r'^[ \t]*\[(\d+)\][ \t]*(.*)$', content, re.MULTILINE):
        num = int(m.group(1))
        line = m.group(2).strip()
        if num in expected_numbers and num not in result and line:
            result[num] = _strip_wrapping_quotes(line)
    return result


def translate_batch_text(lines, source_lang, target_lang, model_cfg,
                         prev_context="", next_context=""):
    """
    整段翻译：把一批字幕合并为一次请求。
    lines: [(local_no, text), ...]，local_no 为批内编号（从 1 开始）
    prev_context / next_context: 整批前后各 N 条非空字幕（仅提示，不翻译）
    返回 ({local_no: 译文}, (prompt, completion, total))
    """
    body = []
    for ln, text in lines:
        safe = text.replace('\n', '<NL>')              # 行内换行 → 占位符，防止破坏行结构
        body.append(f"[{ln}] {safe}")

    parts = []
    if prev_context:
        parts.append("Context before (for reference only — do NOT translate):\n"
                     + prev_context)
    parts.append("Subtitle lines to translate:\n" + "\n".join(body))
    if next_context:
        parts.append("Context after (for reference only — do NOT translate):\n"
                     + next_context)
    user_content = "\n\n".join(parts)

    is_auto = isinstance(source_lang, str) and source_lang.strip().lower() in AUTO_SOURCE_ALIASES
    if is_auto:
        src_desc = ("Translate the numbered subtitle lines into "
                    f"{target_lang}. Detect the source language of the text "
                    "automatically; all lines in one batch are usually the "
                    "same language.")
    else:
        src_desc = (f"Translate the numbered subtitle lines from {source_lang} "
                    f"into {target_lang}.")

    system_prompt = (
        f"You are a professional subtitle translator. "
        f"{src_desc}\n"
        f"Rules:\n"
        f"1. Translate EVERY numbered line.\n"
        f"2. Output each translation on its own line, keeping the SAME [number] "
        f"prefix and the SAME order.\n"
        f"3. Never merge, split, add or drop lines.\n"
        f"4. If a subtitle needs an internal line break, write <NL> where the break goes.\n"
        f"5. The context blocks are for reference only — NEVER translate or repeat them.\n"
        f"6. Output ONLY the translated numbered lines, nothing else."
    )

    n = len(lines)
    # 输出上限：max(单条上限, 行数 × 每行预留)，封顶 BATCH_CAP
    max_tokens = min(MAX_OUTPUT_TOKENS_BATCH_CAP,
                     max(MAX_OUTPUT_TOKENS_SINGLE, n * BATCH_TOKENS_PER_LINE))

    content, tokens = _chat_completion(model_cfg, system_prompt, user_content,
                                       max_tokens)
    expected = {ln for ln, _ in lines}
    raw = _parse_batch_response(content, expected)

    parsed = {}
    for num, line in raw.items():
        line = line.replace('<NL>', '\n').replace('<nl>', '\n').strip()
        if line:                                        # 空译文视为缺失 → 由调用方降级
            parsed[num] = line
    return parsed, tokens


# ============================================================
# Context helpers（上下文只统计非空字幕条目）
# ============================================================
def _collect_context(entries, nonempty, pos_start, pos_end, exclude_pos=None):
    """收集 nonempty[pos_start:pos_end) 范围的上下文行（跳过 exclude_pos）"""
    parts = []
    for j in range(max(0, pos_start), min(len(nonempty), pos_end)):
        if j == exclude_pos:
            continue
        text = entries[nonempty[j]]['text'].replace('\n', ' ').strip()
        if len(text) > CONTEXT_LINE_MAX_CHARS:
            text = text[:CONTEXT_LINE_MAX_CHARS] + "..."
        if text:
            parts.append(f"{j + 1}. {text}")
    return "\n".join(parts) if parts else ""


def _context_around_single(entries, nonempty, pos, prev_count, next_count):
    return _collect_context(entries, nonempty,
                            pos - prev_count, pos + next_count + 1,
                            exclude_pos=pos)


# ============================================================
# Scheduler（单条 / 整段两种模式，共用同一套并发与统计）
# ============================================================
def translate_entries_concurrent(entries, source_lang, target_lang, model_cfg,
                                 prev_count, next_count, batch_size=0,
                                 progress_callback=None, log_callback=None,
                                 cancel_event=None):
    """
    并发翻译所有非空字幕条目。
      batch_size == 0        → 单条模式：一行一个请求
      batch_size >= 2        → 整段模式：每批 batch_size 行合并成一个请求
                                （并发单位 = 批次，上限仍为模型配置的 max_concurrent）
    上下文句数（prev/next）在两种模式下均生效：
      单条模式 → 该行前后各 N 条非空字幕
      整段模式 → 整批之前 / 之后各 N 条非空字幕（仅作提示，不翻译）
    整段模式下批次失败或个别行缺失 → 自动降级为逐条翻译。
    返回 (entries, cancelled)。
    """
    with token_lock:
        global total_prompt_tokens, total_completion_tokens, total_total_tokens
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_total_tokens = 0

    try:
        max_workers = int(model_cfg.get('max_concurrent', 10))
    except (TypeError, ValueError):
        max_workers = 10
    max_workers = max(1, min(200, max_workers))

    nonempty = [i for i, e in enumerate(entries) if e['text'].strip()]
    pos_of = {gi: p for p, gi in enumerate(nonempty)}
    total = len(nonempty)
    results = {}
    completed = 0
    cancelled = False
    use_batch = isinstance(batch_size, int) and batch_size >= BATCH_SIZE_MIN

    def _single(gi):
        """单条翻译 worker，返回 [(entry_idx, text), ...]"""
        text = entries[gi]['text']
        p = pos_of[gi]
        ctx = _context_around_single(entries, nonempty, p, prev_count, next_count)
        try:
            translated, tokens = translate_text(text, source_lang, target_lang,
                                                model_cfg, ctx)
            _add_tokens(tokens)
            return [(gi, translated)]
        except Exception as e:
            if log_callback:
                log_callback(f"  第 {gi + 1} 条翻译失败: {e}")
            return [(gi, text)]

    def _batch(batch_indices, batch_no):
        """
        整段翻译 worker：
        1) 批量请求整批行 → 按编号回填
        2) 失败批次 / 缺失行 → 自动降级为逐条翻译
        3) 降级仍失败 → 保留原文
        """
        local = {1 + k: gi for k, gi in enumerate(batch_indices)}
        first_pos = pos_of[batch_indices[0]]
        last_pos = pos_of[batch_indices[-1]]

        prev_ctx = _collect_context(entries, nonempty,
                                    first_pos - prev_count, first_pos)
        next_ctx = _collect_context(entries, nonempty,
                                    last_pos + 1, last_pos + 1 + next_count)

        result_map = {}
        try:
            lines = [(ln, entries[gi]['text']) for ln, gi in local.items()]
            parsed, tokens = translate_batch_text(lines, source_lang, target_lang,
                                                  model_cfg, prev_ctx, next_ctx)
            _add_tokens(tokens)
            result_map = parsed
        except Exception as e:
            if log_callback:
                log_callback(f"  第 {batch_no} 批翻译失败（{len(batch_indices)} 行），"
                             f"降级为逐条翻译: {e}")

        # 缺失行（批请求失败、解析缺行、空译文）→ 逐条降级
        missing = [(ln, gi) for ln, gi in local.items() if ln not in result_map]
        if missing:
            if log_callback and result_map:
                log_callback(f"  第 {batch_no} 批有 {len(missing)} 行未获得译文，"
                             f"降级为逐条翻译")
            for ln, gi in missing:
                if cancel_event is not None and cancel_event.is_set():
                    break
                try:
                    ctx = _context_around_single(entries, nonempty, pos_of[gi],
                                                 prev_count, next_count)
                    translated, tokens = translate_text(entries[gi]['text'],
                                                        source_lang, target_lang,
                                                        model_cfg, ctx)
                    _add_tokens(tokens)
                    result_map[ln] = translated
                except Exception as e:
                    if log_callback:
                        log_callback(f"  第 {gi + 1} 条翻译失败: {e}")
                    result_map[ln] = entries[gi]['text']          # 保留原文

        return [(gi, result_map.get(ln, entries[gi]['text']))
                for ln, gi in local.items()]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        if use_batch:
            batches = [nonempty[i:i + batch_size]
                       for i in range(0, total, batch_size)]
            if log_callback:
                log_callback(f"  整段翻译: {total} 行 → {len(batches)} 批，"
                             f"每批最多 {batch_size} 行，并发 {max_workers}")
            futures = {executor.submit(_batch, b, bi): b
                       for bi, b in enumerate(batches, 1)}
        else:
            if log_callback:
                log_callback(f"  单条翻译: {total} 行，并发 {max_workers}")
            futures = {executor.submit(_single, gi): [gi] for gi in nonempty}

        for fut in as_completed(futures):
            if fut.cancelled():
                continue
            for gi, text in fut.result():
                results[gi] = text
            completed += len(futures[fut])
            if progress_callback:
                progress_callback(completed, total)
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                for f in futures:                       # 取消时终止剩余任务
                    f.cancel()
                break

    if cancelled:
        return entries, True

    for gi, text in results.items():
        entries[gi]['text'] = text
    return entries, False


# 兼容命名空间：保持原 `subtitles.xxx` 调用方式，但已不再依赖 S_subtitles.py
subtitles = types.SimpleNamespace(
    AUTO_SOURCE_LANG=AUTO_SOURCE_LANG,
    BATCH_SIZE_MIN=BATCH_SIZE_MIN,
    BATCH_SIZE_MAX=BATCH_SIZE_MAX,
    DEFAULT_BATCH_SIZE=DEFAULT_BATCH_SIZE,
    SubFormat=SubFormat,
    SubtitleParser=SubtitleParser,
    SubtitleGenerator=SubtitleGenerator,
    detect_format=detect_format,
    get_config_path=get_config_path,
    get_token_stats=get_token_stats,
    load_config=load_config,
    parse_ass_time=parse_ass_time,
    read_file_content=read_file_content,
    translate_entries_concurrent=translate_entries_concurrent,
)


def configure_stdio() -> None:
    """把标准输出 / 错误改成 UTF-8（errors="replace"）。

    语言列表里有韩文等非 GBK 字符，而 argparse 的 --help 会直接打印 choices；
    输出被重定向到管道 / 文件时 Python 会用 locale（GBK）编码，
    非 GBK 字符会直接抛 UnicodeEncodeError 把命令搞挂。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:                # pythonw / 被重定向的流可能没有这个方法
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            continue


# ------------------------------------------------------------ 控制台回显（GUI 也能看）
CONSOLE_ECHO_ENV = "MSS_ECHO"                    # =0 关闭回显，=1 强制打开（CLI 也能用）
CONSOLE_ECHO_MAX_ENV = "MSS_ECHO_MAX_CHARS"      # 单条回显上限，full / 0 = 不限
CONSOLE_ECHO_SEGMENTS_ENV = "MSS_ECHO_SEGMENTS"  # Whisper 分段回显条数上限，0 / full = 全部
CONSOLE_ECHO_MAX_CHARS = 1200
_console_echo_state = {"enabled": False, "lock": threading.Lock()}


def set_console_echo(enabled: bool) -> None:
    """GUI 启动时打开：把 Whisper 的识别结果与 AI 接口的返回打到命令行。"""
    _console_echo_state["enabled"] = bool(enabled)


def console_echo_enabled() -> bool:
    """回显开关：环境变量优先，其次是 set_console_echo()（GUI 启动即打开）。"""
    override = str(os.environ.get(CONSOLE_ECHO_ENV) or "").strip().lower()
    if override:
        return override not in ("0", "false", "no", "off")
    return bool(_console_echo_state["enabled"])


def _console_echo_limit(env_name: str, default: int) -> int:
    """回显长度 / 条数上限；0 = 不限，读不出数字时用默认值。"""
    raw = str(os.environ.get(env_name) or "").strip().lower()
    if raw in ("full", "all", "0", "-1"):
        return 0
    if raw:
        try:
            return max(0, int(float(raw)))
        except ValueError:
            return default
    return default


def console_echo(tag: str, message) -> None:
    """把引擎 / API 的返回写到命令行（GUI 里也能看到）：带标记、多行缩进、超长截断。"""
    if not console_echo_enabled():
        return
    raw = "" if message is None else str(message)
    text = raw.rstrip()
    if not text:
        return
    limit = _console_echo_limit(CONSOLE_ECHO_MAX_ENV, CONSOLE_ECHO_MAX_CHARS)
    if limit and len(text) > limit:
        text = f"{text[:limit]}…（已截断，共 {len(raw)} 字符；MSS_ECHO_MAX_CHARS 可改）"
    prefix = f"[{tag}] "
    indent = " " * len(prefix)
    lines = text.splitlines() or [""]
    with _console_echo_state["lock"]:
        try:
            for index, line in enumerate(lines):
                print(f"{prefix if index == 0 else indent}{line}", flush=True)
        except (OSError, ValueError, AttributeError, RuntimeError):
            _console_echo_state["enabled"] = False   # 没有标准输出（pythonw）→ 静默停用


def echo_whisper_result(engine: str, model: str, language: str, entries: list[dict],
                        label: str = "") -> None:
    """把 Whisper 的返回（引擎 / 模型 / 条数 / 逐条时间轴 + 文本）打到命令行。"""
    if not console_echo_enabled():
        return
    tag = "Whisper" if not label else f"Whisper·{label}"
    console_echo(tag, f"{engine} · 模型 {model} · 语言 {language or '自动检测'} · "
                      f"返回 {len(entries)} 条")
    limit = _console_echo_limit(CONSOLE_ECHO_SEGMENTS_ENV, 0)
    shown = entries if not limit else entries[:limit]
    for entry in shown:
        console_echo(tag, f"{ms_to_srt_time(entry.get('start_ms', 0))} → "
                          f"{ms_to_srt_time(entry.get('end_ms', 0))}  {entry.get('text', '')}")
    if limit and len(entries) > limit:
        console_echo(tag, f"…… 其余 {len(entries) - limit} 条未打印"
                          f"（MSS_ECHO_SEGMENTS=full 可全部输出）")


# ------------------------------------------------------------ 解释器 / 虚拟环境
VENV_DIRNAME = ".venv"
VENV_RELAUNCH_DISABLE_ENV = "MSS_NO_VENV_RELAUNCH"
VENV_RELAUNCH_MARK_ENV = "MSS_VENV_RELAUNCHED"


def venv_python() -> Path | None:
    """程序目录（或当前目录）下 .venv 的解释器；找不到返回 None。"""
    relative = ((Path("Scripts") / "python.exe") if os.name == "nt"
                else (Path("bin") / "python"))
    roots: list[Path] = []
    try:
        roots.append(Path(__file__).resolve().parent)
    except (NameError, OSError):
        pass
    roots.append(Path.cwd())
    for root in roots:
        candidate = root / VENV_DIRNAME / relative
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def inside_virtualenv() -> bool:
    """当前是否运行在虚拟环境里（venv / virtualenv 的 prefix 与 base_prefix 不同）。"""
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def relaunch_in_venv(arguments: list[str]) -> int | None:
    """不在 .venv 里时，改用 .venv 的解释器重新运行本程序。

    双击 .py、或 .bat 里的裸 `python` 会落到系统解释器上（可能缺少 OpenCV 等依赖），
    这里直接换成项目自带的 .venv。
    返回 None = 继续用当前解释器；返回整数 = 子进程已结束，请以该退出码退出。

    注意：不能用 os.execv —— Windows 下它不对参数做引号转义，
    带空格的路径（如 "D:\\My Files\\a.mp4"）会被拆成多个参数；
    交给 subprocess 的列表形式则由 CPython 负责转义。
    设置 MSS_NO_VENV_RELAUNCH=1 可关闭该行为。
    """
    if os.environ.get(VENV_RELAUNCH_DISABLE_ENV) or os.environ.get(VENV_RELAUNCH_MARK_ENV):
        return None
    if getattr(sys, "frozen", False) or inside_virtualenv():
        return None
    try:
        script = Path(__file__).resolve()
    except (NameError, OSError):
        return None
    interpreter = venv_python()
    if interpreter is None or not script.is_file():
        return None
    try:
        if interpreter.resolve() == Path(sys.executable).resolve():
            return None
    except OSError:
        pass
    command = [str(interpreter), str(script), *arguments]
    os.environ[VENV_RELAUNCH_MARK_ENV] = "1"      # 子进程不会再切一次，避免来回重启
    print(f"未使用项目虚拟环境，改用：{interpreter}", file=sys.stderr, flush=True)
    try:
        completed = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"切换虚拟环境失败（{exc}），继续使用当前解释器。", file=sys.stderr)
        os.environ.pop(VENV_RELAUNCH_MARK_ENV, None)
        return None
    return int(completed.returncode or 0)


def opencv_missing_message() -> str:
    """缺少 OpenCV 时的提示：说明影响范围，并给出该在哪个解释器里安装。"""
    interpreter = venv_python() or Path(sys.executable)
    return ("缺少 OpenCV，无法预览视频画面\n"
            "（识别 / 翻译 / 导出与封装不受影响）\n"
            f"当前解释器：{sys.executable}\n"
            f"安装：\"{interpreter}\" -m pip install opencv-python")


def enable_dpi_awareness() -> None:
    """Windows 下启用每显示器 DPI 感知，避免高缩放屏幕上的位图拉伸模糊。"""
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def window_dpi(window: tk.Misc) -> int:
    """读取窗口当前所在显示器的 DPI；API 不可用时回退到 Tk 估算值或 96。"""
    if os.name == "nt":
        try:
            dpi = int(ctypes.windll.user32.GetDpiForWindow(ctypes.c_void_p(window.winfo_id())))
            if dpi > 0:
                return dpi
        except Exception:
            pass
    try:
        return max(96, int(round(float(window.winfo_fpixels("1i")))))
    except Exception:
        return 96


_PRECISE_TIMER = {"active": False}


def set_precise_timers(enable: bool) -> None:
    """播放期间把系统计时器精度提到 1ms，避免 Tk after() 抖动导致丢帧/卡顿。"""
    if os.name != "nt":
        return
    if enable == _PRECISE_TIMER["active"]:
        return
    try:
        if enable:
            ctypes.windll.winmm.timeBeginPeriod(1)
        else:
            ctypes.windll.winmm.timeEndPeriod(1)
        _PRECISE_TIMER["active"] = enable
    except Exception:
        pass


class StudioError(RuntimeError):
    pass


def find_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in (
        Path(r"D:\Program Files\ffmpeg\bin") / f"{name}.exe",
        Path(r"C:\Program Files\ffmpeg\bin") / f"{name}.exe",
        Path(r"C:\ffmpeg\bin") / f"{name}.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def whisper_model_directories() -> list[Path]:
    roots = []
    configured = os.environ.get("WHISPER_MODEL_DIR")
    if configured:
        roots.append(Path(configured).expanduser())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "Buzz" / "Buzz" / "Cache" / "models" / "whisper")
    roots.append(Path.home() / ".cache" / "whisper")
    return roots


def cached_whisper_model(model: str) -> Path | None:
    aliases = {"large": "large-v3", "turbo": "large-v3-turbo"}
    filename = aliases.get(model, model) + ".pt"
    for directory in whisper_model_directories():
        candidate = directory / filename
        if candidate.is_file() and candidate.stat().st_size > 50_000_000:
            return candidate
    return None


def cached_whisper_models() -> list[str]:
    found = set()
    for directory in whisper_model_directories():
        if directory.is_dir():
            found.update(path.stem for path in directory.glob("*.pt")
                         if path.stat().st_size > 50_000_000)
    return [model for model in WHISPER_MODELS if model in found]


def default_whisper_model() -> str:
    available = cached_whisper_models()
    for preferred in ("medium", "large-v3", "small", "base", "tiny"):
        if preferred in available:
            return preferred
    return "small"


def translation_models() -> list[dict]:
    config = subtitles.load_config() or {}
    return list(config.get("models") or [])


def default_translation_model() -> str:
    config = subtitles.load_config() or {}
    models = config.get("models") or []
    default_name = config.get("default_model")
    if isinstance(default_name, str) and any(item.get("name") == default_name
                                             for item in models):
        return default_name
    return str(models[0]["name"]) if models else ""


def translation_model_by_name(name: str | None) -> dict | None:
    models = translation_models()
    if not models:
        return None
    for item in models:
        if item.get("name") == name:
            return item
    default_name = (subtitles.load_config() or {}).get("default_model")
    for item in models:
        if item.get("name") == default_name:
            return item
    return models[0]


def model_concurrency(model: dict | None, fallback: int = 5) -> int:
    try:
        return max(1, min(100, int((model or {}).get("max_concurrent", fallback))))
    except (AttributeError, TypeError, ValueError):
        return fallback


def default_translation_concurrency() -> int:
    return model_concurrency(translation_model_by_name(None))


@functools.lru_cache(maxsize=1)
def system_whisper_python() -> str | None:
    candidates = [Path(sys.base_prefix) / "python.exe"]
    whisper_executable = shutil.which("whisper")
    if whisper_executable:
        candidates.append(Path(whisper_executable).parent.parent / "python.exe")
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if candidate.resolve() == Path(sys.executable).resolve():
            if importlib.util.find_spec("whisper"):
                return str(candidate)
            continue
        try:
            result = subprocess.run(
                [str(candidate), "-c", "import whisper"],
                capture_output=True, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return str(candidate)
    return None


def run_command(command: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError as exc:
        raise StudioError(f"找不到程序：{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise StudioError(f"命令执行超时：{command[0]}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "未知错误").strip()
        raise StudioError(detail[-2500:])
    return result


def probe_media(path: str | Path) -> dict:
    ffprobe = find_binary("ffprobe")
    if not ffprobe:
        raise StudioError("未找到 ffprobe，请安装 FFmpeg 并加入 PATH。")
    result = run_command([
        ffprobe, "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ], timeout=60)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StudioError("ffprobe 返回了无效媒体信息。") from exc


def subtitle_candidates(media_path: Path) -> list[Path]:
    found = []
    for path in media_path.parent.iterdir():
        if path.is_file() and path.suffix.lower() in SUBTITLE_EXTENSIONS:
            if path.stem == media_path.stem or path.stem.startswith(media_path.stem + "."):
                found.append(path)
    return sorted(found, key=lambda item: (item.stem != media_path.stem, item.name.lower()))


def probe_tracks(info: dict) -> tuple[list[dict], list[dict], list[dict]]:
    audio, embedded_subtitles, videos = [], [], []
    audio_index = 0
    sub_index = 0
    for stream in info.get("streams", []):
        codec_type = stream.get("codec_type")
        tags = stream.get("tags") or {}
        language = tags.get("language", "und")
        title = tags.get("title", "")
        label = f"{language} {title}".strip()
        if codec_type == "audio":
            audio.append({
                "ordinal": audio_index,
                "stream_index": stream.get("index"),
                "label": f"音轨 {audio_index + 1} · {label or stream.get('codec_name', 'audio')} · "
                         f"{stream.get('channels', '?')} 声道",
            })
            audio_index += 1
        elif codec_type == "subtitle":
            embedded_subtitles.append({
                "ordinal": sub_index,
                "stream_index": stream.get("index"),
                "codec": stream.get("codec_name", "unknown"),
                "label": f"内嵌字幕 {sub_index + 1} · {label or stream.get('codec_name', 'subtitle')}",
            })
            sub_index += 1
        elif codec_type == "video":
            videos.append(stream)
    return audio, embedded_subtitles, videos


# ffprobe 的 disposition 布尔表 → ffmpeg 的 disposition 位掩码
# （用于封裝时精确清掉 default 标记，同时保留 forced 等其它标记）
DISPOSITION_BITS = {
    "default": 1, "dub": 2, "original": 4, "comment": 8, "lyrics": 16,
    "karaoke": 32, "forced": 64, "hearing_impaired": 128, "visual_impaired": 256,
    "clean_effects": 512, "attached_pic": 1024, "timed_thumbnails": 2048,
    "captions": 4096, "descriptions": 8192, "metadata": 16384, "dependent": 32768,
    "still_image": 65536,
}
DISPOSITION_DEFAULT = DISPOSITION_BITS["default"]


def disposition_value(stream: dict) -> int:
    """把 ffprobe 的 disposition 布尔表折算成 ffmpeg 的 disposition 位掩码。"""
    flags = stream.get("disposition") or {}
    return sum(bit for name, bit in DISPOSITION_BITS.items() if flags.get(name))


# 字幕轨语言标记：翻译语言名 / 2 字母代码 → mux 惯用的 ISO 639-2/B 三字母
ISO639_1_TO_2B = {
    "en": "eng", "zh": "zho", "ja": "jpn", "ko": "kor", "fr": "fra",
    "de": "deu", "es": "spa", "pt": "por", "ru": "rus", "it": "ita",
    "ar": "ara", "hi": "hin", "th": "tha", "vi": "vie", "id": "ind",
    "ms": "msa", "tr": "tur", "nl": "nld", "pl": "pol", "uk": "ukr",
    "sv": "swe", "no": "nor", "da": "dan", "fi": "fin", "el": "ell",
    "he": "heb", "cs": "ces", "ro": "ron", "hu": "hun", "fa": "fas",
    "bn": "ben", "ur": "urd", "tl": "tgl", "und": "und",
}
# 文件名里的语言标记（a.zh-CN.srt / film.eng.srt / film_日文.srt）；中文区分简繁
SUBTITLE_LANGUAGE_TOKENS = {
    "zh": "zh", "zho": "zh", "chi": "zh",
    "zh-cn": "zh-cn", "zhcn": "zh-cn", "cn": "zh-cn", "chs": "zh-cn",
    "sc": "zh-cn", "hans": "zh-cn", "zh-hans": "zh-cn",
    "zh-tw": "zh-tw", "zhtw": "zh-tw", "tw": "zh-tw", "cht": "zh-tw",
    "tc": "zh-tw", "hant": "zh-tw", "zh-hant": "zh-tw",
    "zh-hk": "zh-hk", "hk": "zh-hk", "yue": "yue",
    "en": "eng", "eng": "eng", "english": "eng",
    "ja": "jpn", "jp": "jpn", "jpn": "jpn", "japanese": "jpn",
    "ko": "kor", "kr": "kor", "kor": "kor", "korean": "kor",
    "fr": "fra", "fre": "fra", "de": "deu", "ger": "deu", "es": "spa",
    "spa": "spa", "pt": "por", "por": "por", "ru": "rus", "rus": "rus",
    "it": "ita", "ita": "ita", "th": "tha", "vie": "vie", "vi": "vie",
    "id": "ind", "msa": "msa", "tur": "tur", "tr": "tur", "nl": "nld",
    "dut": "nld", "pl": "pol", "uk": "ukr", "sv": "swe", "da": "dan",
    "fi": "fin", "el": "ell", "gre": "ell", "he": "heb", "cs": "ces",
    "ro": "ron", "hu": "hun", "fa": "fas", "bn": "ben", "ur": "urd",
    "tgl": "tgl", "und": "und",
}
# 中文文件名里常直接写语言（没分隔符可拆）
CJK_LANGUAGE_TOKENS = {
    "简体": "zh-cn", "繁体": "zh-tw", "繁體": "zh-tw", "中文": "zh",
    "中文字幕": "zh", "英文字幕": "eng", "日文": "jpn", "日语": "jpn",
    "韩文": "kor", "韩语": "kor",
}
LANGUAGE_TOKEN_SPLIT_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


# ============================================================
# 中文简繁（简体 zh-cn / 繁体 zh-tw / 港繁 zh-hk）
# 简繁相关的东西全部集中在这里：写法常量、语言标记映射、字形对照表、
# 文件名写法、写法判定。翻译语言名 / 文件名推断 / 判重 / AI 语言判定都引用本节。
# ============================================================
CHINESE_VARIANT_HANS = "hans"
CHINESE_VARIANT_HANT = "hant"

# 翻译目标 / 来源的中文选项 → 具体写法（用户要求：简中 zh-cn、繁中 zh-tw）
CHINESE_LANGUAGE_CODES = {
    "中文（简体）": "zh-cn", "中文（繁體）": "zh-tw", "繁體中文（香港）": "zh-hk",
}
CHINESE_TARGET_VARIANTS = {"zh-cn": CHINESE_VARIANT_HANS, "zh-tw": CHINESE_VARIANT_HANT,
                          "zh-hk": CHINESE_VARIANT_HANT}
CHINESE_VARIANT_LABELS = {CHINESE_VARIANT_HANS: "简体中文", CHINESE_VARIANT_HANT: "繁体中文"}
# 判出来的写法 → 翻译内核认识的语言名（翻译步骤拿它当来源语言）
CHINESE_VARIANT_LANGUAGES = {CHINESE_VARIANT_HANS: "中文（简体）",
                             CHINESE_VARIANT_HANT: "中文（繁體）"}
# 文件名里的中文写法（先匹配组合写法，再退到单词元；顺序不能颠倒）
CHINESE_FILENAME_PATTERNS = (
    ("zhhans", "zh-cn"), ("zhcn", "zh-cn"), ("hans", "zh-cn"), ("chs", "zh-cn"),
    ("zhhant", "zh-tw"), ("zhtw", "zh-tw"), ("hant", "zh-tw"), ("cht", "zh-tw"),
    ("zhhk", "zh-hk"),
    ("zh", "zh"),
)
# 常见简↔繁字形对照（只列有差异的字，两边写法相同的常用字不列）
CHINESE_VARIANT_PAIRS = (
    ("们", "們"), ("个", "個"), ("来", "來"), ("这", "這"), ("说", "說"),
    ("话", "話"), ("国", "國"), ("体", "體"), ("汉", "漢"), ("见", "見"),
    ("让", "讓"), ("后", "後"), ("发", "發"), ("当", "當"), ("电", "電"),
    ("东", "東"), ("车", "車"), ("马", "馬"), ("鸟", "鳥"), ("鱼", "魚"),
    ("风", "風"), ("云", "雲"), ("书", "書"), ("写", "寫"), ("读", "讀"),
    ("学", "學"), ("门", "門"), ("问", "問"), ("间", "間"), ("时", "時"),
    ("语", "語"), ("谁", "誰"), ("么", "麼"), ("头", "頭"), ("关", "關"),
    ("开", "開"), ("与", "與"), ("无", "無"), ("从", "從"), ("众", "眾"),
    ("会", "會"), ("爱", "愛"), ("对", "對"), ("过", "過"), ("还", "還"),
    ("进", "進"), ("远", "遠"), ("边", "邊"), ("样", "樣"), ("种", "種"),
    ("业", "業"), ("现", "現"), ("为", "為"), ("亲", "親"), ("长", "長"),
    ("乐", "樂"), ("万", "萬"), ("岁", "歲"), ("纪", "紀"), ("级", "級"),
    ("给", "給"), ("结", "結"), ("红", "紅"), ("绿", "綠"), ("蓝", "藍"),
    ("钱", "錢"), ("铁", "鐵"), ("银", "銀"), ("宝", "寶"), ("实", "實"),
    ("际", "際"), ("场", "場"), ("报", "報"), ("传", "傳"), ("图", "圖"),
    ("团", "團"), ("应", "應"), ("态", "態"), ("听", "聽"), ("环", "環"),
    ("节", "節"), ("丽", "麗"), ("压", "壓"), ("许", "許"), ("论", "論"),
    ("访", "訪"), ("飞", "飛"), ("惊", "驚"), ("觉", "覺"), ("顾", "顧"),
    ("险", "險"), ("织", "織"), ("练", "練"), ("线", "線"), ("组", "組"),
    ("细", "細"), ("终", "終"), ("统", "統"), ("缘", "緣"), ("缩", "縮"),
    ("罗", "羅"), ("义", "義"), ("习", "習"), ("买", "買"), ("卖", "賣"),
    ("质", "質"), ("赛", "賽"), ("识", "識"), ("讲", "講"), ("认", "認"),
    ("词", "詞"), ("试", "試"), ("评", "評"), ("谢", "謝"), ("较", "較"),
    ("转", "轉"), ("输", "輸"), ("达", "達"), ("适", "適"), ("选", "選"),
    ("邮", "郵"), ("录", "錄"), ("复", "復"), ("单", "單"), ("双", "雙"),
    ("欢", "歡"), ("热", "熱"), ("题", "題"), ("难", "難"), ("总", "總"),
    ("张", "張"), ("响", "響"), ("阳", "陽"), ("积", "積"), ("静", "靜"),
    ("赞", "讚"), ("兰", "蘭"), ("厅", "廳"), ("阵", "陣"),
)
SIMPLIFIED_CHARS = frozenset(pair[0] for pair in CHINESE_VARIANT_PAIRS)
TRADITIONAL_CHARS = frozenset(pair[1] for pair in CHINESE_VARIANT_PAIRS)


def chinese_variant(entries) -> str:
    """判断中文是简体（hans）/ 繁体（hant）；判不出来（不是中文或无法区分）返回空串。"""
    text = "".join(str((entry or {}).get("text") or "") for entry in (entries or ()))
    simplified = sum(1 for char in text if char in SIMPLIFIED_CHARS)
    traditional = sum(1 for char in text if char in TRADITIONAL_CHARS)
    if simplified == traditional:
        return ""                       # 两边都没命中 / 一样多 → 不猜
    return CHINESE_VARIANT_HANS if simplified > traditional else CHINESE_VARIANT_HANT


def subtitle_language_code(language_name: str, default: str = "und") -> str:
    """翻译语言名（「中文（简体）」，也可直接给 zh-cn / zho）→ 轨道语言标记。

    中文区分 zh-cn（简中）/ zh-tw（繁中）/ zh-hk（香港繁中），其余语言走 ISO 639-2/B。
    """
    name = str(language_name or "").strip()
    if not name or name in ("自动检测", "auto"):
        return default
    if name in CHINESE_LANGUAGE_CODES:
        return CHINESE_LANGUAGE_CODES[name]
    lowered = name.lower()
    if lowered in ("zh-cn", "zh-tw", "zh-hk", "zh"):
        return lowered
    if lowered in ("zho", "chi"):
        return "zh"
    if len(name) == 3 and name.isascii() and name.isalpha():
        return lowered                  # 已经是 zho / jpn 这类代码
    short = str(WHISPER_LANGUAGE_CODES.get(name) or name).lower()
    if short in ("zh", "zho", "chi"):
        return "zh"
    if not short.isascii():
        return default                  # 认不出的语言名（含中日韩写法）→ 不写进轨道标记
    return ISO639_1_TO_2B.get(short, short if short.isalpha() else default)


def guess_subtitle_language(path: str | Path) -> str:
    """从字幕文件名推断语言标记（a.zh-CN.srt → zh-cn、a.cht.srt → zh-tw）；推断不出返回 und。"""
    stem = Path(path).stem.lower()
    flat = LANGUAGE_TOKEN_SPLIT_RE.sub("", stem)
    for pattern, code in CHINESE_FILENAME_PATTERNS:
        if pattern in flat:
            return code
    for token in LANGUAGE_TOKEN_SPLIT_RE.split(stem):
        if token in SUBTITLE_LANGUAGE_TOKENS:
            return SUBTITLE_LANGUAGE_TOKENS[token]
    for text, code in CJK_LANGUAGE_TOKENS.items():
        if text in stem:
            return code
    return "und"


def parse_subtitle_file(path: str | Path) -> list[dict]:
    """CLI/导出用：与 GUI 相同的解析（含 ASS 文本修正与预览样式）。"""
    return load_subtitle_document(path)


class _SubtitleMarkupParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, _attrs):
        if tag == "br" or (tag in {"p", "div"} and self.parts):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def clean_subtitle_entries(entries: list[dict]) -> list[dict]:
    cleaned = copy.deepcopy(entries)
    for entry in cleaned:
        parser = _SubtitleMarkupParser()
        parser.feed(entry["text"])
        parser.close()
        entry["text"] = re.sub(r"\n{3,}", "\n\n", "".join(parser.parts)).strip()
    return cleaned


def extract_embedded_subtitle(media_path: Path, stream_index: int) -> list[dict]:
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise StudioError("未找到 ffmpeg，请安装 FFmpeg 并加入 PATH。")
    with tempfile.TemporaryDirectory(prefix="media_subtitle_") as temp_dir:
        output = Path(temp_dir) / "embedded.srt"
        run_command([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i",
            str(media_path), "-map", f"0:{stream_index}", "-c:s", "srt", str(output),
        ], timeout=300)
        if not output.is_file() or not output.stat().st_size:
            raise StudioError("該內嵌字幕可能是圖像字幕（PGS/VobSub），無法直接轉成文字。")
        return load_subtitle_document(output)


def audio_to_wav(media_path: Path, audio_ordinal: int, output: Path,
                 duration: float | None = None) -> None:
    """抽取指定音轨为 16 kHz 单声道 wav；duration（秒）只取开头一段（探针用）。"""
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise StudioError("未找到 ffmpeg，请安装 FFmpeg 并加入 PATH。")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i",
        str(media_path), "-map", f"0:a:{audio_ordinal}", "-vn", "-ac", "1",
        "-ar", "16000", "-c:a", "pcm_s16le",
    ]
    if duration:
        command.extend(["-t", str(float(duration))])
    command.append(str(output))
    run_command(command, timeout=3600)


def _transcribe_faster_whisper(audio_path: Path, model: str, language: str,
                               progress=None) -> list[dict]:
    WhisperModel = importlib.import_module("faster_whisper").WhisperModel

    if progress:
        progress(f"加载 faster-whisper {model} 模型（首次运行可能下载模型）…")
    whisper_model = WhisperModel(model, device="auto", compute_type="int8")
    segments, _ = whisper_model.transcribe(
        str(audio_path), language=language or None, vad_filter=True,
        beam_size=5,
    )
    result = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            result.append({
                "index": len(result) + 1,
                "start_ms": max(0, round(segment.start * 1000)),
                "end_ms": max(1, round(segment.end * 1000)),
                "text": text,
                "style": None,
                "actor": None,
            })
    return result


def _transcribe_system_whisper(audio_path: Path, model_path: Path, language: str,
                               progress=None) -> list[dict]:
    python = system_whisper_python()
    if not python:
        raise StudioError("找到本地 Whisper 权重，但无法定位已安装 Whisper 的系统 Python。")
    if progress:
        progress(f"使用系统 Whisper 本地模型：{model_path.name}（不下载模型）…")
    script = (
        "import json, sys, whisper\n"
        "audio_path, model_path, language, output_path = sys.argv[1:5]\n"
        "model = whisper.load_model(model_path)\n"
        "result = model.transcribe(audio_path, language=language or None)\n"
        "with open(output_path, 'w', encoding='utf-8') as output:\n"
        "    json.dump(result.get('segments', []), output, ensure_ascii=False)\n"
    )
    with tempfile.TemporaryDirectory(prefix="media_whisper_") as temp_dir:
        output = Path(temp_dir) / "segments.json"
        run_command([
            python, "-c", script, str(audio_path), str(model_path), language, str(output),
        ], timeout=None)
        try:
            segments = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StudioError("系统 Whisper 没有生成有效的分段结果。") from exc
    return [{
        "index": index,
        "start_ms": max(0, round(segment["start"] * 1000)),
        "end_ms": max(1, round(segment["end"] * 1000)),
        "text": segment["text"].strip(), "style": None, "actor": None,
    } for index, segment in enumerate(segments, 1) if segment.get("text", "").strip()]


def _transcribe_transformers(audio_path: Path, model: str, language: str,
                             progress=None) -> list[dict]:
    pipeline = importlib.import_module("transformers").pipeline

    hf_model = f"openai/whisper-{model}"
    if progress:
        progress(f"加载 Transformers {hf_model}（首次运行需要下载模型）…")
    recognizer = pipeline(
        "automatic-speech-recognition", model=hf_model,
        chunk_length_s=30, stride_length_s=(5, 5),
    )
    generate_kwargs = {"task": "transcribe"}
    if language:
        generate_kwargs["language"] = language
    response = recognizer(str(audio_path), return_timestamps=True,
                          generate_kwargs=generate_kwargs)
    result = []
    for chunk in response.get("chunks", []):
        start, end = chunk.get("timestamp") or (None, None)
        if start is None or end is None:
            continue
        text = chunk.get("text", "").strip()
        if text:
            result.append({
                "index": len(result) + 1,
                "start_ms": max(0, round(start * 1000)),
                "end_ms": max(1, round(end * 1000)),
                "text": text,
                "style": None,
                "actor": None,
            })
    if not result and response.get("text", "").strip():
        raise StudioError("Whisper 未返回分段时间戳，请更新 Transformers 或安装 faster-whisper。")
    return result


def transcribe_audio(audio_path: Path, model: str = "small", language: str = "",
                     progress=None, label: str = "") -> list[dict]:
    """识别音频；label 只用于命令行回显的标记（识别 / 探针 / 计划识别…）。"""
    local_model = cached_whisper_model(model)
    engine = f"未知后端（{model}）"
    if local_model and importlib.util.find_spec("whisper"):
        whisper = importlib.import_module("whisper")

        engine = f"whisper（已链接模型 {local_model.name}）"
        if progress:
            progress(f"使用已链接的 Whisper 模型：{local_model.name}…")
        whisper_model = whisper.load_model(str(local_model))
        response = whisper_model.transcribe(str(audio_path), language=language or None)
        segments = response.get("segments", [])
        result = [{
            "index": index,
            "start_ms": max(0, round(segment["start"] * 1000)),
            "end_ms": max(1, round(segment["end"] * 1000)),
            "text": segment["text"].strip(), "style": None, "actor": None,
        } for index, segment in enumerate(segments, 1) if segment.get("text", "").strip()]
    elif local_model and system_whisper_python():
        engine = f"系统 Whisper（本地模型 {local_model.name}）"
        result = _transcribe_system_whisper(audio_path, local_model, language, progress)
    elif importlib.util.find_spec("faster_whisper"):
        engine = f"faster-whisper（{model}）"
        result = _transcribe_faster_whisper(audio_path, model, language, progress)
    elif importlib.util.find_spec("whisper"):
        whisper = importlib.import_module("whisper")

        engine = f"OpenAI Whisper（{model}）"
        if progress:
            progress(f"加载 OpenAI Whisper {model} 模型…")
        whisper_model = whisper.load_model(model)
        response = whisper_model.transcribe(str(audio_path), language=language or None)
        result = [{
            "index": index,
            "start_ms": max(0, round(segment["start"] * 1000)),
            "end_ms": max(1, round(segment["end"] * 1000)),
            "text": segment["text"].strip(), "style": None, "actor": None,
        } for index, segment in enumerate(response.get("segments", []), 1)
                if segment.get("text", "").strip()]
    elif importlib.util.find_spec("transformers"):
        engine = f"Transformers（openai/whisper-{model}）"
        result = _transcribe_transformers(audio_path, model, language, progress)
    else:
        raise StudioError("未安装本地 Whisper 引擎。请运行：python -m pip install faster-whisper")
    if not result:
        raise StudioError("Whisper 未识别出带时间戳的字幕。")
    echo_whisper_result(engine, model, language, result, label)
    return result


def translated_entries(entries: list[dict], source_lang: str, target_lang: str,
                       model_name: str | None = None, progress=None, log=None,
                       max_concurrent: int | None = None, batch_size: int = 0,
                       context_lines: int | None = None,
                       cancel_event: threading.Event | None = None) -> tuple[list[dict], bool]:
    """并发翻译字幕；progress(done, total) 直接上报进度，取消时返回 (原字幕, True)。

    context_lines：上下文句数（前后各 N 条非空字幕，仅作参考、不翻译）；
    None = 用默认值 DEFAULT_CONTEXT_LINES，0 = 关闭上下文。
    """
    config = subtitles.load_config()
    if not config:
        raise StudioError(f"AI 配置不可用：{subtitles.get_config_path()}")
    selected = model_name or config.get("default_model")
    model_cfg = next((item for item in config["models"]
                      if item.get("name") == selected), None)
    if not model_cfg:
        raise StudioError("AI 配置中找不到所选模型。")
    model_cfg = copy.deepcopy(model_cfg)
    if max_concurrent is not None:
        model_cfg["max_concurrent"] = max(1, min(100, int(max_concurrent)))
    if batch_size != 0 and not subtitles.BATCH_SIZE_MIN <= batch_size <= subtitles.BATCH_SIZE_MAX:
        raise StudioError(
            f"分组行数必须为 0（逐条）或 {subtitles.BATCH_SIZE_MIN}~"
            f"{subtitles.BATCH_SIZE_MAX}。"
        )

    source = LANGUAGES.get(source_lang, source_lang)
    target = LANGUAGES.get(target_lang, target_lang)
    source_value = subtitles.AUTO_SOURCE_LANG if source == "auto" else source
    context = (DEFAULT_CONTEXT_LINES if context_lines is None
               else max(0, min(int(context_lines), CONTEXT_LINES_MAX)))
    result = copy.deepcopy(entries)
    translated, cancelled = subtitles.translate_entries_concurrent(
        result, source_value, target, model_cfg,
        prev_count=context, next_count=context,
        batch_size=batch_size, progress_callback=progress, log_callback=log,
        cancel_event=cancel_event,
    )
    return translated, cancelled


def _ass_time(milliseconds: int) -> str:
    centiseconds = max(0, int(milliseconds)) // 10
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    seconds, centiseconds = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def generate_bilingual_ass(original: list[dict], translated: list[dict],
                           title: str = "Bilingual Subtitles") -> str:
    lines = [
        "[Script Info]", f"Title: {title}", "ScriptType: v4.00+",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "PlayResX: 1920",
        "PlayResY: 1080", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Original,Microsoft YaHei UI,46,&H00FFFFFF,&H000000FF,&H00101010,"
        "&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,80,80,58,1",
        "Style: Translation,Microsoft YaHei UI,44,&H0000D7FF,&H000000FF,&H00101010,"
        "&H64000000,0,0,0,0,100,100,0,0,1,3,1,2,80,80,18,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for source, target in zip(original, translated):
        source_text = source["text"].replace("{", "｛").replace("}", "｝").replace("\n", r"\N")
        target_text = target["text"].replace("{", "｛").replace("}", "｝").replace("\n", r"\N")
        text = r"{\rOriginal}" + source_text + r"\N{\rTranslation}" + target_text
        lines.append(
            f"Dialogue: 0,{_ass_time(source['start_ms'])},{_ass_time(source['end_ms'])},"
            "Original,,0,0,0,," + text
        )
    return "\n".join(lines) + "\n"


def write_subtitle(entries: list[dict], output: str | Path,
                   format_name: str = "srt") -> Path:
    output_path = Path(output)
    formats = {
        "srt": subtitles.SubFormat.SRT,
        "vtt": subtitles.SubFormat.VTT,
        "ass": subtitles.SubFormat.ASS,
    }
    fmt = formats.get(format_name.lower())
    if fmt is None:
        raise StudioError(f"不支持的字幕格式：{format_name}")
    content = subtitles.SubtitleGenerator.generate(entries, fmt)
    if fmt == subtitles.SubFormat.ASS:
        content = content.replace("Style: Default,Arial,48,", "Style: Default,Microsoft YaHei UI,46,")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8-sig", newline="\n")
    return output_path


def bilingual_entries(original: list[dict], translated: list[dict]) -> list[dict]:
    combined = copy.deepcopy(original)
    for index, entry in enumerate(combined):
        if index < len(translated):
            entry["text"] = f"{entry['text']}\n{translated[index]['text']}"
    return combined


def write_selected_subtitle(original: list[dict], translated: list[dict],
                            output: str | Path, format_name: str,
                            language_mode: str) -> Path:
    if language_mode == "原文":
        entries = original
    elif language_mode == "译文":
        entries = translated
    elif language_mode == "双语":
        if not translated:
            raise StudioError("双语输出需要先完成翻译。")
        if format_name.lower() == "ass":
            return write_bilingual_ass(original, translated, output)
        entries = bilingual_entries(original, translated)
    else:
        raise StudioError(f"不支持的字幕语言模式：{language_mode}")
    if not entries:
        raise StudioError(f"当前没有可导出的{language_mode}字幕。")
    return write_subtitle(entries, output, format_name)


def write_bilingual_ass(original: list[dict], translated: list[dict],
                        output: str | Path) -> Path:
    output_path = Path(output)
    content = generate_bilingual_ass(original, translated, output_path.stem)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8-sig", newline="\n")
    return output_path


def normalise_language_tag(value) -> str | None:
    """把用户写的语言（名称或代码）折成轨道标记：中文（简体）→ zh-cn、English→eng、ja→jpn。"""
    text = str(value or "").strip()
    if not text:
        return None
    return subtitle_language_code(text, default=text)


def normalize_mux_specs(subtitle_specs) -> list[dict]:
    """把「单个路径 / 路径列表 / 字幕轨 dict 列表」统一成 [{path, language, title, default}]。"""
    if subtitle_specs is None:
        return []
    if isinstance(subtitle_specs, (str, Path)):
        items = [subtitle_specs]
    else:
        items = list(subtitle_specs)
    specs: list[dict] = []
    for item in items:
        if isinstance(item, (str, Path)):
            item = {"path": item}
        if not isinstance(item, dict):
            raise StudioError("字幕轨设置格式不正确。")
        raw_path = item.get("path")
        if raw_path in (None, ""):
            raise StudioError("字幕轨缺少文件路径。")
        specs.append({
            "path": Path(raw_path).expanduser(),
            "language": normalise_language_tag(item.get("language")),
            "title": (str(item.get("title")) if item.get("title") else None),
            "default": bool(item.get("default")),
        })
    return specs


def normalize_export_tracks(mux_tracks) -> list[dict]:
    """把导出 / 计划任务里的字幕轨设置统一成
    [{kind, mode, path, language, title, bind}]。

    kind = "generated"（用当前字幕内容现场生成）或 "external"（已有字幕文件）；
    外部文件不存在时报错。bind 是外部字幕相对「加入时那个媒体文件」的命名关系
    （见 subtitle_binding），批量执行时用它为每个文件找对应的字幕。
    """
    tracks: list[dict] = []
    for item in (mux_tracks or []):
        if isinstance(item, (str, Path)):
            item = {"path": item}
        if not isinstance(item, dict):
            raise StudioError("字幕轨设置格式不正确。")
        mode = str(item.get("mode") or "").strip()
        raw_path = item.get("path")
        path = Path(raw_path).expanduser() if raw_path not in (None, "") else None
        kind = str(item.get("kind") or ("external" if (path and not mode) else "generated"))
        if kind == "external":
            if path is None:
                raise StudioError("外部字幕轨缺少文件路径。")
            if not path.is_file():
                raise StudioError(f"外部字幕文件不存在：{path}")
            language = normalise_language_tag(item.get("language")) or guess_subtitle_language(path)
            title = item.get("title") or path.stem
        else:
            kind, mode = "generated", (mode or "原文")
            language, title = normalise_language_tag(item.get("language")), item.get("title")
        bind = item.get("bind")
        tracks.append({"kind": kind, "mode": mode, "path": path,
                       "language": language, "title": title,
                       "bind": dict(bind) if isinstance(bind, dict) else {}})
    return tracks


# ============================================================
# 外部字幕轨：按「字幕与媒体文件的命名关系」匹配
#   加入计划时记下字幕相对当时那个媒体文件的位置（同目录 / 子目录 + 命名后缀），
#   批量执行时按同样的关系在当前文件旁边找对应字幕 ——
#   每个文件压它自己的字幕，而不是把同一个字幕硬压进所有文件。
# ============================================================
def subtitle_binding(media, subtitle) -> dict:
    """记下字幕相对媒体的命名关系：{"sub_dir", "suffix", "extension"}。

    例：foo.mkv + foo.zh-CN.srt → {"sub_dir": "", "suffix": ".zh-CN",
    "extension": ".srt"}；foo.mkv + subs/foo.srt → sub_dir = "subs"。
    名字或目录对不上（跨盘、随意命名）→ {}，表示建立不了对应关系，
    只能用当初指定的那个文件。
    """
    if media in (None, ""):
        return {}
    media_path, subtitle_path = Path(media), Path(subtitle)
    stem = subtitle_path.stem
    if not stem.startswith(media_path.stem):
        return {}
    try:
        relative = subtitle_path.parent.resolve().relative_to(media_path.parent.resolve())
    except (OSError, ValueError):
        return {}
    return {"sub_dir": "" if str(relative) in ("", ".") else str(relative),
            "suffix": stem[len(media_path.stem):],
            "extension": subtitle_path.suffix}


def _same_language_token(left: str, right: str) -> bool:
    """两个语言标记是否指同一种语言（zh 视为中文的通配写法）。"""
    if not left or not right:
        return False
    if left == right:
        return True
    return "zh" in (left, right) and left.startswith("zh") and right.startswith("zh")


def find_bound_subtitle(media, binding) -> Path | None:
    """按绑定关系在当前媒体旁边找对应字幕；找不到返回 None。

    先找完全同名（媒体名 + 后缀 + 扩展名），再在同目录找语言标记写法不同、
    但表示同一语言的（.zh.srt ↔ .zh-CN.srt）。
    """
    if not binding or media in (None, ""):
        return None
    media_path = Path(media)
    suffix = str(binding.get("suffix") or "")
    extension = str(binding.get("extension") or "")
    if not extension:
        return None
    folder = media_path.parent
    sub_dir = str(binding.get("sub_dir") or "")
    if sub_dir:
        folder = folder / sub_dir
    exact = folder / f"{media_path.stem}{suffix}{extension}"
    if exact.is_file():
        return exact
    wanted = guess_subtitle_language(f"subtitle{suffix}{extension}")
    if wanted == "und":
        return None
    try:
        entries = sorted(folder.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return None
    for candidate in entries:
        try:
            if not candidate.is_file() or candidate.suffix.lower() != extension.lower():
                continue
        except OSError:
            continue
        if not candidate.stem.startswith(media_path.stem):
            continue
        remainder = candidate.stem[len(media_path.stem):]
        if not remainder:
            continue
        found = guess_subtitle_language(candidate)
        if _same_language_token(wanted, found):
            return candidate
    return None


def resolve_export_tracks(media, tracks, *, log=None) -> tuple[list[dict], list[dict]]:
    """把字幕轨落到当前媒体上：返回 (可用轨, 被跳过的轨)。

    - 生成的字幕轨（原文 / 译文 / 双语）原样保留；
    - 外部字幕轨记了命名关系（bind）的 → 按同样的关系在当前文件旁边找对应字幕，
      找不到就跳过这一轨（绝不把别的文件的字幕硬压进来）；
    - 没记关系的（跨目录 / 随意命名）→ 仍用当初指定的那个文件。
    """
    media_path = None if media in (None, "") else Path(media)
    resolved: list[dict] = []
    skipped: list[dict] = []
    for index, track in enumerate(tracks or []):
        track = dict(track)
        if str(track.get("kind") or "") != "external":
            resolved.append(track)
            continue
        configured = track.get("path")
        path = None if configured in (None, "") else Path(str(configured))
        binding = track.get("bind") or {}
        found = find_bound_subtitle(media_path, binding) if binding else None
        if found is not None:
            if path is not None and str(found) != str(path) and log:
                log(f"外部字幕按文件名关系匹配：{path.name} → {found.name}")
            path = found
        elif binding:
            name = path.name if path is not None else str(track.get("title") or "外部字幕")
            skipped.append({"index": index, "label": f"外部字幕 {name}",
                            "reason": "该文件旁边没有对应的字幕",
                            "path": str(path) if path is not None else None})
            if log:
                log(f"跳过字幕轨：{name} —— 这个文件旁边没有对应的字幕")
            continue
        try:
            exists = path is not None and path.is_file()
        except OSError:
            exists = False
        if not exists:
            name = path.name if path is not None else str(track.get("title") or "外部字幕")
            skipped.append({"index": index, "label": f"外部字幕 {name}",
                            "reason": "字幕文件不存在",
                            "path": str(path) if path is not None else None})
            if log:
                log(f"跳过字幕轨：字幕文件不存在（{path}）")
            continue
        if path is None:                    # 上面已处理 None；显式判断，供类型检查收窄
            continue
        track["path"] = path
        if not track.get("title"):
            track["title"] = path.stem
        resolved.append(track)
    return resolved, skipped


def _pending_mux_record(media, tracks, missing, settings, options, entries,
                        original, translated, *, skipped: bool) -> dict:
    """记下「这个文件缺哪些外部字幕」，供全部任务结束后让用户补选 / 放弃。

    连同识别 / 翻译结果与压制设置一起存下：补选字幕时只需重跑压制步骤，
    不必再识别一次（也不台再来一轮翻译 token）。
    """
    prepared: dict = {}
    if entries is not None:
        prepared["entries"] = entries
    if original:
        prepared["original"] = original
    if translated:
        prepared["translated"] = translated
    return {
        "media": str(media),
        "tracks": list(tracks),
        "missing": [dict(item) for item in missing],
        "format": str(settings.get("format") or "srt").lower(),
        "language": str(settings.get("language") or "原文"),
        "drop_subtitles": list(settings.get("drop_subtitles") or []),
        "options": {key: options.get(key) for key in
                    ("check_duplicates", "duplicate_threshold", "check_ai", "ai_model")},
        "prepared": prepared or None,
        "skipped": bool(skipped),
    }


def container_language_code(language: str, extension: str) -> str:
    """按容器规整语言标记：MP4/MOV 只认 3 字母代码，zh-cn / zh-tw 会被静默丢掉 → 归并成 zho。"""
    code = str(language or "").strip().lower()
    if extension in (".mp4", ".m4v", ".mov") and code.startswith("zh"):
        return "zho"
    return code or "und"


def mux_subtitle(media_path: str | Path, subtitle_specs,
                 output_path: str | Path | None = None, container: str = "auto",
                 drop_subtitles=None) -> Path:
    """把一条或多条字幕封装为独立字幕轨（不烧录画面）。

    subtitle_specs：字幕文件路径，或它的列表；每项也可以写成 dict：
        {"path": 字幕文件, "language": "zho", "title": "中文", "default": True}
    （language 缺省时从文件名推断，title 缺省时写入文件名）。第一个字幕轨为默认轨，
    除非有某一项显式写了 default=True。
    drop_subtitles：要删除的内嵌字幕**序号**（0 起，按字幕流顺序）；其余视频 / 音频 /
    字幕轨原样复制；被保留的内嵌字幕只清掉 default 标记（forced 等其它标记不动）。
    """
    media_path = Path(media_path)
    specs = normalize_mux_specs(subtitle_specs)
    if not specs:
        raise StudioError("没有要压制的字幕文件。")
    missing = next((spec["path"] for spec in specs if not spec["path"].is_file()), None)
    if missing is not None:
        raise StudioError(f"字幕文件不存在：{missing}")
    info = probe_media(media_path)
    _audio, embedded, videos = probe_tracks(info)
    drop = {int(item) for item in (drop_subtitles or [])}
    kept = [item for item in embedded if item["ordinal"] not in drop]
    ordinal_of = {item["stream_index"]: item["ordinal"] for item in embedded}
    raw_of = {stream.get("index"): stream for stream in (info.get("streams") or [])}
    formats = [subtitles.detect_format(str(spec["path"])) for spec in specs]
    ass_input = any(fmt in (subtitles.SubFormat.ASS, subtitles.SubFormat.SSA)
                    for fmt in formats)
    supported_extensions = {".mkv", ".mka", ".mp4", ".m4v", ".mov", ".webm"}
    requested_extension = Path(output_path).suffix.lower() if output_path else ""
    if container == "auto":
        extension = requested_extension or (".mkv" if videos else ".mka")
    else:
        extension = "." + container.lower().lstrip(".")
    if extension not in supported_extensions:
        raise StudioError(f"不支持的封装格式：{extension}")
    if extension in (".mp4", ".m4v", ".mov") and ass_input:
        raise StudioError("MP4/MOV 不支持 ASS 字幕流；请选择 MKV，或先导出 SRT。")
    if extension == ".webm" and ass_input:
        raise StudioError("WebM 不支持 ASS 字幕流；请选择 MKV，或先导出 SRT。")
    # MP4/MOV/WebM 只容纳特定字幕编解码器，保留的内嵌字幕不兼容时先给明确提示
    container_sub_codecs = {
        ".mp4": ("mov_text", "tx3g"), ".m4v": ("mov_text", "tx3g"),
        ".mov": ("mov_text", "tx3g"), ".webm": ("webvtt",),
    }
    if extension in container_sub_codecs:
        allowed = container_sub_codecs[extension]
        unsupported = None
        for item in kept:
            codec = (raw_of.get(item["stream_index"]) or {}).get("codec_name", "")
            if codec not in allowed:
                unsupported = item
                break
        if unsupported is not None:
            raise StudioError(
                f"{extension.lstrip('.').upper()} 只能保存 {'/'.join(allowed)} 字幕，"
                f"当前保留的内嵌字幕是 {unsupported['codec']}，无法复制进去："
                "请改用 MKV，或把该内嵌字幕设为删除。")
    if output_path is None:
        output_path = media_path.with_name(f"{media_path.stem}_subtitled{extension}")
    output_path = Path(output_path)
    if not output_path.suffix:
        output_path = output_path.with_suffix(extension)
    elif output_path.suffix.lower() != extension:
        raise StudioError(
            f"输出扩展名 {output_path.suffix} 与封装格式 {extension} 不一致。"
        )
    if output_path.resolve() == media_path.resolve():
        raise StudioError("输出文件不能覆盖输入媒体。")
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise StudioError("未找到 ffmpeg，请安装 FFmpeg 并加入 PATH。")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i",
               str(media_path)]
    for spec in specs:
        command.extend(["-i", str(spec["path"])])
    # 逐流显式映射：要删掉的内嵌字幕不映射 = 不进入输出，其余全部原样复制
    for stream in info.get("streams") or []:
        index = stream.get("index")
        if stream.get("codec_type") == "subtitle" and ordinal_of.get(index) in drop:
            continue
        command.extend(["-map", f"0:{index}"])
    for position in range(len(specs)):            # 每条新字幕各占一条输出字幕轨
        command.extend(["-map", f"{position + 1}:0"])
    command.extend(["-map_metadata", "0", "-map_chapters", "0", "-c", "copy"])
    new_base = len(kept)
    if extension in (".mp4", ".m4v", ".mov"):
        for position in range(len(specs)):
            command.extend([f"-c:s:{new_base + position}", "mov_text"])
    elif extension == ".webm":
        for position in range(len(specs)):
            command.extend([f"-c:s:{new_base + position}", "webvtt"])
    for position, item in enumerate(kept):        # 保留的字幕不再标 default
        flags = disposition_value(raw_of.get(item["stream_index"]) or {})
        command.extend([f"-disposition:s:{position}",
                        str(flags & ~DISPOSITION_DEFAULT)])
    default_position = next((index for index, spec in enumerate(specs)
                             if spec.get("default")), 0)
    for position, spec in enumerate(specs):
        index = new_base + position
        flags = DISPOSITION_DEFAULT if position == default_position else 0
        language = container_language_code(
            spec["language"] or guess_subtitle_language(spec["path"]), extension)
        command.extend([f"-disposition:s:{index}", str(flags),
                        f"-metadata:s:s:{index}", f"language={language}"])
        if spec["title"]:                        # 播放器里能看出这条轨是什么
            command.extend([f"-metadata:s:s:{index}", f"title={spec['title']}"])
    command.append(str(output_path))
    run_command(command, timeout=3600)
    if not output_path.is_file():
        raise StudioError("FFmpeg 未生成封装文件。")
    return output_path


def export_subtitles(media: str | Path, format_name: str, location: str,
                     language_mode: str, original: list[dict],
                     translated: list[dict], drop_subtitles=None,
                     mux_tracks=None) -> list[Path]:
    """导出单个字幕文件（location="外挂字幕"）或压制字幕轨（location="内嵌字幕"）。

    mux_tracks：要压制的字幕轨列表（可多条），每项为
        {"kind": "generated", "mode": "原文"/"译文"/"双语"} 或
        {"kind": "external", "path": 字幕文件}（可选 language / title）；
        外挂时不传 → 按 language_mode 写 1 个文件，压制时不传 → 按 language_mode 生成 1 条轨。
    返回**输出文件列表**。
    """
    media = Path(media)
    fmt = str(format_name or "srt").lower()
    tracks = normalize_export_tracks(mux_tracks)
    if location == "外挂字幕":
        modes: list[str] = []
        for track in tracks:
            if track["kind"] == "generated" and track["mode"] not in modes:
                modes.append(track["mode"])
        outputs = []
        for mode in (modes or [language_mode]):
            suffix = SUBTITLE_OUTPUT_SUFFIX.get(mode, "original")
            outputs.append(write_selected_subtitle(
                original, translated, media.with_name(f"{media.stem}_{suffix}.{fmt}"),
                fmt, mode))
        return outputs
    if tracks:
        with tempfile.TemporaryDirectory(prefix="subtitle_mux_") as temp_dir:
            specs: list[dict] = []
            for position, track in enumerate(tracks, 1):
                if track["kind"] == "external":
                    specs.append(track)
                    continue
                path = Path(temp_dir) / f"subtitle_{position}.{fmt}"
                write_selected_subtitle(original, translated, path, fmt, track["mode"])
                specs.append({"path": path, "language": track["language"],
                              "title": track["title"] or track["mode"],
                              "default": False})
            return [mux_subtitle(media, specs, drop_subtitles=drop_subtitles)]
    with tempfile.TemporaryDirectory(prefix="subtitle_mux_") as temp_dir:
        subtitle_path = Path(temp_dir) / f"subtitle.{fmt}"
        write_selected_subtitle(original, translated, subtitle_path, fmt, language_mode)
        return [mux_subtitle(media, subtitle_path, drop_subtitles=drop_subtitles)]


# ============================================================
# 压制前检查：语义重复 / 语言判定 / 3 分钟探针
# 设计要点（与用户逐条确认过）：
#  - 识别一律用「音轨」选择的那条；一旦计划里指定了识别，就一定完整识别。
#  - 只有「计划里没加识别步骤」或「文件里选不到那条音轨」时，才走探针分支：
#    取前 3 分钟音频用 medium 识别，与已有内嵌字幕比对；对得上就直接用这份字幕当来源，
#    对不上就补跑完整识别。
#  - 来源是已有字幕时先让 AI 判语言：已是目标语言 / 双语 → 不翻译，把它当作「译文」直接压制；
#    判不了（无模型 / 请求失败）→ 跳过该文件（宁可不输出）。
#  - 压制前对**每一条将要压制的字幕轨**做语义重复检查（与已有内嵌字幕、与其它待压轨），
#    默认开启、可关掉；本地相似度 ≥阈值直接判重复，中间区间交 AI 判语义。
# ============================================================
PROBE_WHISPER_MODEL = "medium"          # 探针固定用 medium
PROBE_SAMPLE_SECONDS = 180              # 探针只取开头 3 分钟
DUPLICATE_THRESHOLD_DEFAULT = 70        # 本地相似度阈值（百分比）
DUPLICATE_AI_LOW = 40                   # 低于此值直接放过；阈值~LOW 之间交 AI 判语义

TRANSLATE_SOURCE_ASR = "识别所选音轨"
TRANSLATE_SOURCE_PROBE = "自动：先探针校验已有字幕"
TRANSLATE_SOURCE_EMBEDDED = "内嵌字幕"
TRANSLATE_SOURCE_SIDECAR = "同目录字幕文件"
TRANSLATE_SOURCES = (TRANSLATE_SOURCE_ASR, TRANSLATE_SOURCE_PROBE,
                     TRANSLATE_SOURCE_EMBEDDED, TRANSLATE_SOURCE_SIDECAR)

LANGUAGE_TARGET = "target"
LANGUAGE_BILINGUAL = "bilingual"
LANGUAGE_OTHER = "other"
LANGUAGE_UNKNOWN = "unknown"

DUPLICATE_YES = "duplicate"
DUPLICATE_NO = "different"
DUPLICATE_OTHER_LANGUAGE = "different_language"   # 语言不同 → 一律不算重复
DUPLICATE_UNKNOWN = "unknown"

# 文字体系 → 码位区间（用于「不同语言不算重复」的前置判断）
SCRIPT_RANGES = {
    "han": ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)),
    "kana": ((0x3040, 0x30FF), (0xFF66, 0xFF9F)),
    "hangul": ((0x1100, 0x11FF), (0xAC00, 0xD7AF)),
    "latin": ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F)),
    "cyrillic": ((0x0400, 0x04FF),),
    "greek": ((0x0370, 0x03FF),),
    "arabic": ((0x0600, 0x06FF),),
    "thai": ((0x0E00, 0x0E7F),),
}
# 这些文字体系只属于特定语言：一边有一边没有 → 直接当不同语言
SCRIPT_LANGUAGE_MARKERS = ("kana", "hangul", "thai", "arabic", "cyrillic", "greek")

CHECK_SAMPLE_LINES = 40                 # 交 AI 判定的行数上限
OVERLAP_MAX_LINES = 400                 # 本地比对的行数上限（防超长字幕拖慢）


class PlanSkipped(StudioError):
    """计划执行中被自动跳过（字幕重复 / 语言判定 / 没有可用来源）。"""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = str(reason)
        self.detail = str(detail)


SUBTITLE_TEXT_CLEAN_RE = re.compile(r"[^0-9a-z\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff"
                                    r"\uff66-\uff9f]+", re.IGNORECASE)


def normalise_subtitle_lines(entries) -> list[str]:
    """把字幕条目归一化成可比对的行（去空白 / 标点、统一小写，保留中日韩字符）。"""
    lines: list[str] = []
    for entry in entries or ():
        text = str((entry or {}).get("text") or "")
        cleaned = SUBTITLE_TEXT_CLEAN_RE.sub("", text).strip().lower()
        if cleaned:
            lines.append(cleaned)
    return lines


def script_signature(entries) -> frozenset:
    """文字体系集合（han / kana / latin …），用来判断「是不是同一种语言」。"""
    found: set[str] = set()
    for entry in entries or ():
        for char in str((entry or {}).get("text") or ""):
            point = ord(char)
            for name, ranges in SCRIPT_RANGES.items():
                if name in found:
                    continue
                if any(low <= point <= high for low, high in ranges):
                    found.add(name)
        if len(found) == len(SCRIPT_RANGES):
            break
    return frozenset(found)


def scripts_may_match(left_entries, right_entries) -> bool:
    """两份字幕是否可能是同一种语言：文字体系不相交 / 一方有独有体系 / 中文简繁不同 → 不同语言。"""
    left, right = script_signature(left_entries), script_signature(right_entries)
    if not left or not right:
        return True                      # 没有文字（空字幕）→ 交给后面的判定
    if not (left & right):
        return False
    if not all((name in left) == (name in right) for name in SCRIPT_LANGUAGE_MARKERS):
        return False
    if left == frozenset({"han"}) and right == frozenset({"han"}):
        left_variant, right_variant = chinese_variant(left_entries), chinese_variant(right_entries)
        if left_variant and right_variant and left_variant != right_variant:
            return False                 # 简体 vs 繁体 → 算不同语言
    return True


def _line_similarity(left: str, right: str) -> float:
    """两行文字的相似度（0–1）。"""
    if left == right:
        return 1.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def subtitle_overlap(left_entries, right_entries) -> float:
    """两份字幕的相似度（0–1）：逐行取另一份里最像的一行再平均（语言不同也会算得很低）。"""
    left = normalise_subtitle_lines(left_entries)[:OVERLAP_MAX_LINES]
    right = normalise_subtitle_lines(right_entries)[:OVERLAP_MAX_LINES]
    if not left or not right:
        return 0.0
    total = 0.0
    for line in left:
        total += max(_line_similarity(line, other) for other in right)
    return total / len(left)


def _subtitle_sample(entries, limit: int = CHECK_SAMPLE_LINES) -> str:
    return "\n".join(str((entry or {}).get("text") or "").strip()
                     for entry in (entries or ())[:limit]
                     if str((entry or {}).get("text") or "").strip())


def _ai_ask_line(model_name, system_prompt: str, user_content: str, max_tokens: int,
                 cancel_event=None) -> tuple[str, int, str]:
    """问模型一个只要一行答案的问题；返回 (答案, tokens, 错误说明)。tokens 计入内核统计。"""
    model_cfg = translation_model_by_name(model_name)
    if not model_cfg:
        return "", 0, "没有可用的 AI 模型配置"
    if cancel_event is not None and cancel_event.is_set():
        return "", 0, "已取消"
    try:
        content, usage = _chat_completion(copy.deepcopy(model_cfg), system_prompt,
                                          user_content, max_tokens)
    except Exception as exc:                     # 网络 / 配置问题 → 交给调用方按保守策略处理
        return "", 0, str(exc)[:200]
    usage = usage or (0, 0, 0)
    if usage[2]:
        _add_tokens(usage)
    return content.strip(), int(usage[2]), ""


def ai_language_verdict(entries, target_lang: str, model_name=None,
                        cancel_event=None) -> dict:
    """AI 判这份字幕的语言：target（已是目标语言）/ bilingual（含目标语言的双语）/
    other（其它语言，附语言名）/ unknown（判不了）。"""
    sample = _subtitle_sample(entries)
    if not sample:
        return {"verdict": LANGUAGE_UNKNOWN, "language": "", "tokens": 0,
                "error": "字幕内容为空"}
    target = LANGUAGES.get(target_lang, target_lang)
    # 目标是中文时先本地判简繁（快、不花 token）：同写法 = 已是目标语言，异写法 = 需要翻译
    target_variant = CHINESE_TARGET_VARIANTS.get(subtitle_language_code(target_lang))
    if target_variant:
        variant = chinese_variant(entries)
        if variant:
            language = CHINESE_VARIANT_LANGUAGES.get(variant, "")
            if variant == target_variant:
                return {"verdict": LANGUAGE_TARGET, "language": language,
                        "tokens": 0, "error": ""}
            return {"verdict": LANGUAGE_OTHER, "language": language,
                    "tokens": 0, "error": ""}
    system = "你是字幕语言检查器。只输出一行结果，不要任何解释。"
    user = (f"目标语言是「{target}」。下面是待检查字幕的前几行：\n---\n{sample}\n---\n"
            "请判断：\n"
            f"- 整份字幕都是「{target}」 → 输出 TARGET\n"
            f"- 同时包含「{target}」和其它语言（双语字幕） → 输出 BILINGUAL\n"
            "- 其它情况 → 输出 OTHER:<这份字幕的主要语言>，例如 OTHER:Japanese；"
            "中文要写明写法（OTHER:简体中文 / OTHER:繁体中文）\n"
            "只输出上面三种之一。")
    answer, tokens, error = _ai_ask_line(model_name, system, user, 64, cancel_event)
    upper = answer.upper()
    if upper.startswith("TARGET"):
        verdict, language = LANGUAGE_TARGET, target
    elif upper.startswith("BILINGUAL"):
        verdict, language = LANGUAGE_BILINGUAL, ""
    elif upper.startswith("OTHER"):
        verdict = LANGUAGE_OTHER
        language = answer.split(":", 1)[1].strip() if ":" in answer else ""
    else:
        verdict, language = LANGUAGE_UNKNOWN, ""
    if verdict == LANGUAGE_UNKNOWN and not error:
        error = f"返回值无法解析：{answer[:60]}"
    return {"verdict": verdict, "language": language, "tokens": tokens, "error": error}


def ai_semantic_duplicate(candidate, existing, model_name=None, cancel_event=None) -> dict:
    """AI 判两份字幕是否**同一种语言**且内容基本雷同（同一批台词）。

    前提：不同语言 **不算**重复（哪怕意思一样、互为翻译）；由 `scripts_may_match()`
    先做便宜的文字体系排除，只有可能是同语言时才会调到这里。
    """
    left, right = _subtitle_sample(candidate), _subtitle_sample(existing)
    if not left or not right:
        return {"verdict": DUPLICATE_UNKNOWN, "tokens": 0, "error": "字幕内容为空"}
    system = "你是字幕内容比对器。只输出一行结果，不要任何解释。"
    user = ("下面是两份字幕各自的前若干行。请判断它们是不是**同一种语言**、"
            "并且内容基本相同（同一批台词，措辞可以略有差别）。\n"
            "注意：语言不同的两份字幕（哪怕意思一样、是翻译关系）都不算重复。\n"
            f"【字幕 A】\n{left}\n\n【字幕 B】\n{right}\n\n"
            "只输出 DUPLICATE（同语言且内容雷同）或 DIFFERENT（其它情况）。")
    answer, tokens, error = _ai_ask_line(model_name, system, user, 16, cancel_event)
    upper = answer.upper()
    if upper.startswith("DUPLICATE"):
        verdict = DUPLICATE_YES
    elif upper.startswith("DIFFERENT"):
        verdict = DUPLICATE_NO
    else:
        verdict = DUPLICATE_UNKNOWN
    if verdict == DUPLICATE_UNKNOWN and not error:
        error = f"返回值无法解析：{answer[:60]}"
    return {"verdict": verdict, "tokens": tokens, "error": error}


def compare_subtitles(candidate, existing, *, threshold: float = DUPLICATE_THRESHOLD_DEFAULT,
                      use_ai: bool = True, model_name=None, cancel_event=None,
                      label: str = "") -> dict:
    """两份字幕是否算重复：**同一种语言**且内容雷同才算。

    1. 文字体系不相交（中/日 ↔ 英俄阿泰…）→ 直接判不重复，不调 AI；
    2. 本地相似度 ≥阈值 → 判重复；
    3. 落在于 40%–阈值之间 → 交 AI 判「同语言且内容雷同」；
    4. AI 判不了 → **按不重复处理**（用户要求：拿不准就不要当重复）。
    返回 {"duplicate", "ratio", "verdict", "tokens", "error", "label"}。
    """
    ratio = subtitle_overlap(candidate, existing)
    verdict = {"duplicate": False, "ratio": ratio, "verdict": DUPLICATE_NO,
               "tokens": 0, "error": "", "label": label}
    if not scripts_may_match(candidate, existing):
        verdict["verdict"] = DUPLICATE_OTHER_LANGUAGE
        return verdict
    limit = max(1, int(threshold)) / 100.0
    low = min(DUPLICATE_AI_LOW / 100.0, limit)
    if ratio >= limit:
        verdict.update(duplicate=True, verdict=DUPLICATE_YES)
        return verdict
    if ratio < low or not use_ai:
        return verdict
    answer = ai_semantic_duplicate(candidate, existing, model_name, cancel_event)
    verdict["tokens"] = int(answer.get("tokens") or 0)
    verdict["error"] = str(answer.get("error") or "")
    if answer.get("verdict") == DUPLICATE_YES:
        verdict.update(duplicate=True, verdict=DUPLICATE_YES)
    return verdict


def embedded_subtitle_documents(media: Path, log=None) -> list[dict]:
    """读回媒体里每条内嵌字幕的文字（图像字幕 / 读不出来就跳过这一条）。"""
    try:
        info = probe_media(media)
    except StudioError:
        return []
    _audio, embedded, _videos = probe_tracks(info)
    documents = []
    for item in embedded:
        try:
            entries = extract_embedded_subtitle(media, item["stream_index"])
        except StudioError as exc:
            if log:
                log(f"内嵌字幕 {item['label']} 读不出文字（{exc}），不参与检查")
            continue
        documents.append({"label": item["label"], "entries": entries})
    return documents


def probe_subtitle_against_audio(media: Path, audio_ordinal: int, candidate, *,
                                 language: str = "", model: str = PROBE_WHISPER_MODEL,
                                 seconds: int = PROBE_SAMPLE_SECONDS,
                                 threshold: float = DUPLICATE_THRESHOLD_DEFAULT,
                                 use_ai: bool = True, model_name=None,
                                 log=None, cancel_event=None) -> dict:
    """取音频前 N 秒用 medium 识别，判断候选字幕是否就是这段音频的听写。

    返回 {"matched": True/False/None, "ratio", "verdict", "tokens", "error", ...}；
    matched=None 表示判不了（调用方自行决定补跑完整识别）。
    """
    result = {"matched": None, "ratio": 0.0, "verdict": DUPLICATE_UNKNOWN,
              "tokens": 0, "seconds": int(seconds), "model": model, "error": "",
              "probe_lines": 0}
    if cancel_event is not None and cancel_event.is_set():
        result["error"] = "已取消"
        return result
    if log:
        log(f"探针：取开头 {int(seconds) // 60} 分钟音频，用 {model} 识别…")
    try:
        with tempfile.TemporaryDirectory(prefix="probe_asr_") as temp_dir:
            audio = Path(temp_dir) / "probe.wav"
            audio_to_wav(Path(media), int(audio_ordinal), audio, duration=seconds)
            entries = transcribe_audio(audio, model, language,
                                       progress=(lambda text: log(text)) if log else None,
                                       label="探针")
    except Exception as exc:
        result["error"] = f"探针识别失败：{exc}"
        return result
    result["probe_lines"] = len(entries)
    sample = [entry for entry in (candidate or [])
              if int(entry.get("end_ms") or 0) <= int(seconds) * 1000]
    verdict = compare_subtitles(entries, sample, threshold=threshold, use_ai=use_ai,
                                model_name=model_name, cancel_event=cancel_event,
                                label="探针")
    result.update(ratio=verdict["ratio"], verdict=verdict["verdict"],
                  tokens=verdict["tokens"], error=verdict["error"])
    # 只有「同一种语言且内容雷同」才算命中（语言不同 / 拿不准 → 不算命中，改为完整识别）
    result["matched"] = verdict["verdict"] == DUPLICATE_YES
    return result


def check_mux_tracks(media: Path, candidates: list[dict], *,
                     threshold: float = DUPLICATE_THRESHOLD_DEFAULT,
                     use_ai: bool = True, model_name=None, log=None,
                     cancel_event=None, existing=None) -> dict:
    """压制前检查：每条待压字幕轨与「已有内嵌字幕」「其它待压轨」比，**同语言且内容雷同**才算重复。

    candidates：[{"label": 显示名, "entries": 内容, "spec": 原设置}]，按将压入的顺序。
    返回 {"keep": [...], "dropped": [{"label","ratio","target","verdict"}], "tokens": int}
    """
    documents = existing if existing is not None else embedded_subtitle_documents(media, log=log)
    kept: list[dict] = []
    dropped: list[dict] = []
    tokens = 0
    for candidate in candidates:
        entries = candidate.get("entries") or []
        if not entries:
            dropped.append({"label": candidate.get("label"), "ratio": 0.0,
                            "target": "内容为空", "verdict": DUPLICATE_UNKNOWN})
            continue
        hit = None
        for name, other in ([(f"已有内嵌字幕 {item['label']}", item["entries"])
                             for item in documents]
                            + [(f"本次要压的 {item['label']}", item.get("entries") or [])
                               for item in kept]):
            verdict = compare_subtitles(entries, other, threshold=threshold,
                                        use_ai=use_ai, model_name=model_name,
                                        cancel_event=cancel_event, label=name)
            tokens += int(verdict.get("tokens") or 0)
            if verdict["duplicate"]:
                hit = {"label": candidate.get("label"),
                       "ratio": round(float(verdict["ratio"]), 3),
                       "target": name, "verdict": verdict["verdict"],
                       "error": verdict["error"]}
                break
        if hit:
            dropped.append(hit)
            if log:
                log(f"检查：{hit['label']} 与「{hit['target']}」重复"
                    f"（相似度 {hit['ratio']:.0%}）→ 不压制")
        else:
            kept.append(candidate)
    return {"keep": kept, "dropped": dropped, "tokens": tokens}


def plan_subtitle_source(media: Path, log=None) -> tuple[list[dict], str]:
    """计划里没有识别步骤时，为翻译 / 导出步骤找一份可用字幕（内嵌 → 同目录）。"""
    info = probe_media(media)
    _audio, embedded, _videos = probe_tracks(info)
    if embedded:
        entries = extract_embedded_subtitle(media, embedded[0]["stream_index"])
        description = f"内嵌字幕 {embedded[0]['label']}"
    else:
        candidates = subtitle_candidates(media)
        if not candidates:
            raise StudioError("没有内嵌字幕，也没有同目录同名字幕")
        entries = load_subtitle_document(candidates[0])
        description = f"同目录字幕 {candidates[0].name}"
    if log:
        log(f"未识别字幕，自动改用{description}")
    return entries, description


def _plan_track_contents(track: dict, original, translated) -> list[dict]:
    """一条待压字幕轨的内容（外部文件读盘；生成轨用当前原文 / 译文）。"""
    if str(track.get("kind") or "") == "external":
        return load_subtitle_document(Path(str(track.get("path"))))
    mode = str(track.get("mode") or "原文")
    if mode == "译文":
        return list(translated or [])
    if mode == "双语":
        return bilingual_entries(original, translated) if translated else []
    return list(original or [])


def run_plan_for_media(media_path, steps, log=None, progress=None,
                       cancel_event=None, step_callback=None,
                       prepared=None, options=None, pending_mux=None) -> dict:
    """对单个媒体按顺序执行整套计划步骤（识别 → 翻译 → 导出 / 压制）。

    prepared：识别线程预先算好的「翻译来源」（见 prepare_plan_source）——给了就跳过 asr
    步骤，并按其中的 translation_skipped 决定要不要真的调 AI 翻译。
    options：{"check_duplicates", "duplicate_threshold", "check_ai", "ai_model", ...}。
    pending_mux：给了列表就把「没找到对应外部字幕」的补选信息记进去（见 _pending_mux_record），
    整批任务结束后由界面弹窗让用户选择放弃还是补选字幕。
    步骤 kind：asr / translate / export（只导出单个字幕文件）/ mux（压制字幕轨，
    必须带 settings["mux_tracks"]）。
    被自动跳过时抛 PlanSkipped（调用方据此记为「跳过」而不是「失败」）。
    """
    media = Path(media_path)
    if not media.is_file():
        raise StudioError(f"文件不存在：{media}")
    if not steps:
        raise StudioError("计划里还没有任何步骤")
    options = dict(options or {})
    entries: list[dict] | None = None
    original: list[dict] = []
    translated: list[dict] = []
    outputs: list[Path] = []
    tokens = 0
    translation_skipped = False
    total_steps = len(steps)

    if prepared:
        entries = copy.deepcopy(prepared.get("entries") or [])
        original = copy.deepcopy(prepared.get("original") or entries)
        translated = copy.deepcopy(prepared.get("translated") or [])
        tokens += int(prepared.get("tokens") or 0)
        translation_skipped = bool(prepared.get("translation_skipped"))
        if log and prepared.get("note"):
            log(f"来源：{prepared['note']}")

    def report_step(order, label, kind, phase, step_tokens=0):
        if step_callback:
            step_callback({"order": order, "total": total_steps, "label": label,
                           "kind": kind, "phase": phase, "tokens": int(step_tokens)})

    for order, step in enumerate(steps, 1):
        if cancel_event is not None and cancel_event.is_set():
            raise StudioError("计划已停止")
        kind = str(step.get("kind") or "")
        settings = dict(step.get("settings") or {})
        label = str(step.get("label") or kind)
        step_tokens = 0
        if kind == "asr" and prepared:
            continue                    # 识别线程已经执行并上报过这一步
        if log:
            log(f"步骤 {order}/{total_steps} · {label}")
        report_step(order, label, kind, "begin")
        if kind == "asr":
            info = probe_media(media)
            audio, _embedded, _videos = probe_tracks(info)
            if not audio:
                raise StudioError("该文件没有音轨，无法识别")
            wanted = int(settings.get("audio_ordinal") or 0)
            ordinal = max(0, min(wanted, len(audio) - 1))
            if log and ordinal != wanted:
                log(f"该文件只有 {len(audio)} 条音轨，改用第 {ordinal + 1} 条")
            with tempfile.TemporaryDirectory(prefix="plan_asr_") as temp_dir:
                wav = Path(temp_dir) / "audio.wav"
                audio_to_wav(media, ordinal, wav)
                entries = transcribe_audio(
                    wav, str(settings.get("model") or "small"),
                    str(settings.get("whisper_language") or ""),
                    progress=(lambda text: log(text)) if log else None,
                    label="计划识别")
            original = copy.deepcopy(entries)
            translated = []
        elif kind == "translate":
            if translation_skipped:
                if log:
                    log("已有目标语言字幕，跳过翻译（直接进入压制）")
                report_step(order, label, kind, "done", 0)
                continue
            if entries is None:
                entries, _description = plan_subtitle_source(media, log=log)
                original = copy.deepcopy(entries)
            source_lang = str(settings.get("source") or "自动检测")
            if prepared and prepared.get("language"):
                source_lang = str(prepared["language"])    # AI 判出来的语言优先
            result, cancelled = translated_entries(
                copy.deepcopy(entries), source_lang,
                str(settings.get("target") or "中文（简体）"),
                settings.get("model_name"), progress=progress, log=log,
                max_concurrent=int(settings.get("concurrency") or 5),
                batch_size=int(settings.get("batch_size") or 0),
                context_lines=settings.get("context_lines"),
                cancel_event=cancel_event)
            if cancelled:
                raise StudioError("翻译已取消")
            translated = result
            try:
                step_tokens = int(subtitles.get_token_stats()[2])
            except Exception:
                step_tokens = 0
            tokens += step_tokens
        elif kind == "mux":
            configured_tracks = settings.get("mux_tracks") or None
            if not configured_tracks:
                raise StudioError("压制步骤缺少字幕轨设置（mux_tracks）")
            # 按「加入计划时字幕与那个文件的命名关系」找当前文件对应的字幕：
            # 每个文件压它自己的字幕，而不是把同一个字幕硬压进所有文件
            tracks, missing_tracks = resolve_export_tracks(media, configured_tracks, log=log)
            if entries is None and any(str(item.get("kind") or "") != "external"
                                       for item in configured_tracks):
                entries, _description = plan_subtitle_source(media, log=log)
                original = copy.deepcopy(entries)
            if missing_tracks and pending_mux is not None:
                pending_mux.append(_pending_mux_record(
                    media, configured_tracks, missing_tracks, settings, options,
                    entries, original, translated, skipped=not tracks))
            if not tracks:
                raise PlanSkipped(
                    "该文件旁边找不到对应的外部字幕",
                    "；".join(f"{item['label']}：{item['reason']}" for item in missing_tracks))
            candidates: list[dict] = []
            for position, track in enumerate(tracks, 1):
                if str(track.get("kind") or "") == "external":
                    item_label = f"外部字幕 {Path(str(track.get('path'))).name}"
                else:
                    item_label = f"生成的字幕·{track.get('mode') or '原文'}"
                candidates.append({
                    "key": position, "label": item_label, "spec": track,
                    "entries": _plan_track_contents(track, original, translated)})
            dropped: list[dict] = []
            if candidates and options.get("check_duplicates", True):
                outcome = check_mux_tracks(
                    media, candidates,
                    threshold=options.get("duplicate_threshold", DUPLICATE_THRESHOLD_DEFAULT),
                    use_ai=bool(options.get("check_ai", True)),
                    model_name=options.get("ai_model"), log=log,
                    cancel_event=cancel_event)
                tokens += int(outcome.get("tokens") or 0)
                candidates, dropped = outcome["keep"], outcome["dropped"]
                if not candidates:
                    raise PlanSkipped(
                        "待压字幕与视频里已有字幕同语言且内容雷同，已全部去掉",
                        "；".join(f"{item['label']} ≈ {item['target']}"
                                  f"（{item['ratio']:.0%}）" for item in dropped))
            if log:
                for item in dropped:
                    log(f"跳过字幕轨：{item['label']}（与 {item['target']} 同语言且内容雷同 "
                        f"{item['ratio']:.0%}）")
            for output in export_subtitles(
                    media, str(settings.get("format") or "srt").lower(), "内嵌字幕",
                    str(settings.get("language") or "原文"),
                    copy.deepcopy(original), copy.deepcopy(translated),
                    drop_subtitles=settings.get("drop_subtitles") or None,
                    mux_tracks=[item["spec"] for item in candidates]):
                outputs.append(output)
                if log:
                    log(f"已输出：{output}")
        elif kind == "export":
            mode = str(settings.get("language") or "原文")
            if entries is None:
                entries, _description = plan_subtitle_source(media, log=log)
                original = copy.deepcopy(entries)
            if mode in ("译文", "双语") and not translated:
                raise PlanSkipped(f"没有{mode}内容可导出",
                                  "该文件没有译文，来源也不是目标语言字幕")
            for output in export_subtitles(
                    media, str(settings.get("format") or "srt").lower(),
                    "外挂字幕", mode, copy.deepcopy(original),
                    copy.deepcopy(translated)):
                outputs.append(output)
                if log:
                    log(f"已输出：{output}")
        else:
            raise StudioError(f"未知的计划步骤：{kind}")
        report_step(order, label, kind, "done", step_tokens)
    return {"media": str(media), "outputs": outputs, "entries": len(original),
            "translated": len(translated), "tokens": tokens}


def prepare_plan_source(media, steps, options=None, *, log=None, cancel_event=None,
                        step_callback=None) -> dict:
    """为单个文件准备「翻译来源」（在识别线程里跑，保证 Whisper 同时只跑一个）。

    规则：
    - 计划里有识别步骤、且音轨选得到 → **一律完整识别所选音轨**（用户要求）；
    - 没有识别步骤 / 音轨号选不到 → 看「翻译来源」：
        · 识别所选音轨：完整识别；
        · 自动：先取开头 3 分钟用 medium 探针，与已有内嵌字幕比对，对得上就用它当来源，
          对不上 / 没有内嵌字幕 → 补跑完整识别；
        · 内嵌字幕 / 同目录字幕文件：直接用指定字幕；
    - 来源是已有字幕时让 AI 判语言：已是目标语言 / 双语 → 不翻译，把它当「译文」；
      判定失败 → 抛 PlanSkipped（宁可不输出）。
    """
    media = Path(media)
    options = dict(options or {})
    asr_steps = [step for step in steps if str(step.get("kind") or "") == "asr"]
    settings = dict(asr_steps[0].get("settings") or {}) if asr_steps else {}
    asr_order = next((index for index, step in enumerate(steps, 1)
                      if str(step.get("kind") or "") == "asr"), 0)
    asr_label = str(asr_steps[0].get("label") or "识别") if asr_steps else "识别"

    def report(phase, step_tokens=0):
        if step_callback and asr_order:
            step_callback({"order": asr_order, "total": len(steps), "label": asr_label,
                           "kind": "asr", "phase": phase, "tokens": int(step_tokens)})

    def target_language() -> str:
        translate = next((step for step in steps
                          if str(step.get("kind") or "") == "translate"), None)
        return str(((translate or {}).get("settings") or {}).get("target")
                   or options.get("target") or "中文（简体）")

    info = probe_media(media)
    audio, _embedded, _videos = probe_tracks(info)
    wanted_value = settings.get("audio_ordinal")
    if wanted_value is None:
        wanted_value = options.get("audio_ordinal") or 0
    wanted = int(wanted_value or 0)
    ordinal = max(0, min(wanted, len(audio) - 1)) if audio else None
    track_missing = ordinal is None or ordinal != wanted
    source_mode = str(options.get("translate_source") or TRANSLATE_SOURCE_ASR)
    result = {"entries": None, "original": [], "translated": [],
              "translation_skipped": False, "note": "", "language": None,
              "tokens": 0, "probe": None}
    model = str(settings.get("model") or options.get("asr_model") or "small")
    language = str(settings.get("whisper_language") or options.get("asr_language") or "")

    def full_recognition(note: str) -> dict:
        if ordinal is None:
            raise PlanSkipped("该文件没有音轨，无法识别",
                              "已跳过：请改用内嵌 / 同目录字幕或换成有音轨的文件")
        if log:
            log(f"步骤 {asr_order}/{len(steps)} · {asr_label}" if asr_order
                else f"自动识别音轨 {ordinal + 1}（计划里没有识别步骤）")
        def forward_progress(text):
            if log is not None:
                log(text)

        report("begin")
        with tempfile.TemporaryDirectory(prefix="plan_asr_") as temp_dir:
            wav = Path(temp_dir) / "audio.wav"
            audio_to_wav(media, ordinal, wav)
            recognized = transcribe_audio(wav, model, language,
                                          progress=forward_progress if log else None,
                                          label="计划识别")
        report("done")
        result.update(entries=recognized, original=copy.deepcopy(recognized), note=note)
        return result

    if asr_steps and ordinal is not None and not track_missing:
        return full_recognition(f"完整识别音轨 {ordinal + 1}")
    if asr_steps and log:
        log(f"选不到第 {wanted + 1} 条音轨（该文件只有 {len(audio)} 条），改用自动兜底")

    candidate: dict | None = None
    if source_mode == TRANSLATE_SOURCE_SIDECAR:
        sidecars = subtitle_candidates(media)
        if not sidecars:
            raise PlanSkipped("没有同目录同名字幕文件", f"{media.name} 旁边没有可用字幕")
        candidate = {"label": f"同目录字幕 {sidecars[0].name}",
                     "entries": load_subtitle_document(sidecars[0])}
    elif source_mode in (TRANSLATE_SOURCE_EMBEDDED, TRANSLATE_SOURCE_PROBE):
        documents = embedded_subtitle_documents(media, log=log)
        if documents:
            candidate = documents[0]
        elif source_mode == TRANSLATE_SOURCE_EMBEDDED:
            raise PlanSkipped("该文件没有内嵌字幕", "")

    if source_mode == TRANSLATE_SOURCE_PROBE and candidate is not None and ordinal is not None:
        probe = probe_subtitle_against_audio(
            media, ordinal, candidate["entries"], language=language,
            model=str(options.get("probe_model") or PROBE_WHISPER_MODEL),
            seconds=int(options.get("probe_seconds") or PROBE_SAMPLE_SECONDS),
            threshold=float(options.get("duplicate_threshold", DUPLICATE_THRESHOLD_DEFAULT)),
            use_ai=bool(options.get("check_ai", True)), model_name=options.get("ai_model"),
            log=log, cancel_event=cancel_event)
        result["probe"] = probe
        result["tokens"] += int(probe.get("tokens") or 0)
        if probe.get("matched") is True:
            if log:
                log(f"探针：{candidate['label']} 与音频吻合"
                    f"（相似度 {probe['ratio']:.0%}），不再完整识别")
        else:
            if log:
                log("探针：与音频对不上（语言不同或内容不符），改为完整识别"
                    if probe.get("verdict") != DUPLICATE_UNKNOWN
                    else f"探针：无法判定（{probe.get('error') or '未知原因'}），改为完整识别")
            candidate = None

    if candidate is not None:
        verdict = ai_language_verdict(candidate["entries"], target_language(),
                                      options.get("ai_model"), cancel_event)
        result["tokens"] += int(verdict.get("tokens") or 0)
        kind = verdict.get("verdict")
        if kind in (LANGUAGE_TARGET, LANGUAGE_BILINGUAL):
            entries = copy.deepcopy(candidate["entries"])
            result.update(
                entries=entries, original=copy.deepcopy(entries),
                translated=copy.deepcopy(entries), translation_skipped=True,
                note=(f"{candidate['label']} 已经是目标语言"
                      f"{'（含目标语言的双语）' if kind == LANGUAGE_BILINGUAL else ''}，"
                      "跳过翻译，直接进入压制"))
            if log:
                log(result["note"])
            return result
        if kind == LANGUAGE_OTHER:
            entries = copy.deepcopy(candidate["entries"])
            result.update(entries=entries, original=copy.deepcopy(entries),
                          language=str(verdict.get("language") or ""),
                          note=f"用{candidate['label']}作翻译来源"
                               f"（AI 判定语言：{verdict.get('language') or '未知'}）")
            return result
        raise PlanSkipped("无法判定已有字幕的语言，已跳过该文件",
                          str(verdict.get("error") or "AI 判定失败"))

    return full_recognition(f"完整识别音轨 {(ordinal or 0) + 1}")


def run_plan_for_files(files, steps, *, log=None, progress=None, cancel_event=None,
                       step_callback=None, file_callback=None, options=None,
                       continue_on_error: bool = True, pending_mux=None) -> dict:
    """多文件流水线：识别线程连续刷文件（Whisper 同时只有一个），主线程拿到某个文件的
    识别结果就立即翻译 + 压制，两者重叠，最大化利用时间。

    log(text, name=None)；file_callback(index, total, path_text)；
    step_callback(event, index, path)；options 见 prepare_plan_source。
    pending_mux：列表时把「没找到对应外部字幕」的补选信息记进去（不中断任务）。
    返回 {"results": [...], "skipped": [...], "errors": [...], "tokens": int}。
    """
    options = dict(options or {})
    file_list = [Path(item) for item in files]
    prepared: dict[int, dict] = {}
    failures: dict[int, BaseException] = {}
    ready = {index: threading.Event() for index in range(1, len(file_list) + 1)}

    def file_log(path):
        if log is None:
            return None

        def forward(text):
            if log is not None:
                log(text, path.name)

        return forward

    def file_step(path, index):
        if not step_callback:
            return None

        def forward(event):
            if step_callback:
                step_callback(event, index, path)

        return forward

    def recognition_worker():
        for index, path in enumerate(file_list, 1):
            if cancel_event is not None and cancel_event.is_set():
                break
            try:
                prepared[index] = prepare_plan_source(
                    path, steps, options, log=file_log(path),
                    cancel_event=cancel_event, step_callback=file_step(path, index))
            except BaseException as exc:                 # 含 PlanSkipped
                failures[index] = exc
            finally:
                ready[index].set()

    threading.Thread(target=recognition_worker, daemon=True,
                     name="plan-recognition").start()

    results: list[dict] = []
    skipped: list[dict] = []
    errors: list[dict] = []
    tokens = 0
    for index, path in enumerate(file_list, 1):
        if cancel_event is not None and cancel_event.is_set():
            break
        if file_callback:
            file_callback(index, len(file_list), str(path))
        ready[index].wait()                              # 等本文件的来源就绪（可能早就好了）
        failure = failures.get(index)
        if isinstance(failure, PlanSkipped):
            skipped.append({"path": str(path), "reason": failure.reason,
                            "detail": failure.detail})
            if log:
                log(f"跳过该文件：{failure.reason}"
                    + (f"（{failure.detail}）" if failure.detail else ""), path.name)
            continue
        if isinstance(failure, BaseException):
            errors.append({"path": str(path), "message": str(failure)})
            if log:
                log(f"失败：{failure}", path.name)
            if not continue_on_error:
                break
            continue
        try:
            outcome = run_plan_for_media(
                path, steps, log=file_log(path), progress=progress,
                cancel_event=cancel_event, step_callback=file_step(path, index),
                prepared=prepared.get(index), options=options,
                pending_mux=pending_mux)
        except PlanSkipped as exc:
            skipped.append({"path": str(path), "reason": exc.reason, "detail": exc.detail})
            if log:
                log(f"跳过该文件：{exc.reason}"
                    + (f"（{exc.detail}）" if exc.detail else ""), path.name)
            continue
        except Exception as exc:
            errors.append({"path": str(path), "message": str(exc)})
            if log:
                log(f"失败：{exc}", path.name)
            if not continue_on_error:
                break
            continue
        tokens += int(outcome.get("tokens") or 0)
        results.append(outcome)
    return {"results": results, "skipped": skipped, "errors": errors, "tokens": tokens}


def _font(size: int):
    if ImageFont is None:
        return None
    for path in FONT_PATHS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


# ============================================================
# 预览渲染：解析字幕文件自身的格式（ASS 样式表 / SRT 内联标签）
# ============================================================
ASS_BLOCK_RE = re.compile(r"\{([^}]*)\}")
ASS_LEGACY_ALIGNMENT = {1: 1, 2: 2, 3: 3, 5: 7, 6: 8, 7: 9, 9: 4, 10: 5, 11: 6}
ASS_FONT_FILES = {
    "arial": ("arial.ttf", "arialbd.ttf"),
    "segoe ui": ("segoeui.ttf", "segoeuib.ttf"),
    "microsoft yahei": ("msyh.ttc", "msyhbd.ttc"),
    "microsoft yahei ui": ("msyh.ttc", "msyhbd.ttc"),
    "微软雅黑": ("msyh.ttc", "msyhbd.ttc"),
    "yahei": ("msyh.ttc", "msyhbd.ttc"),
    "simhei": ("simhei.ttf", "simhei.ttf"),
    "黑体": ("simhei.ttf", "simhei.ttf"),
    "simsun": ("simsun.ttc", "simsun.ttc"),
    "宋体": ("simsun.ttc", "simsun.ttc"),
    "kaiti": ("simkai.ttf", "simkai.ttf"),
    "楷体": ("simkai.ttf", "simkai.ttf"),
    "consolas": ("consola.ttf", "consolab.ttf"),
    "times new roman": ("times.ttf", "timesbd.ttf"),
    "verdana": ("verdana.ttf", "verdanab.ttf"),
}
FONTS_DIR = Path(r"C:\Windows\Fonts")
CSS_COLOURS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "yellow": (255, 255, 0), "lime": (0, 255, 0), "green": (0, 128, 0),
    "blue": (0, 0, 255), "cyan": (0, 255, 255), "aqua": (0, 255, 255),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "grey": (128, 128, 128),
    "gray": (128, 128, 128), "silver": (192, 192, 192), "orange": (255, 165, 0),
    "purple": (128, 0, 128), "pink": (255, 192, 203), "brown": (165, 42, 42),
}


def default_preview_block(text: str = "") -> dict:
    """默认（无样式）预览块：白字、底部居中。"""
    lines = [[{"text": line, "bold": False, "italic": False, "underline": False,
               "colour": None}] if line else []
             for line in (text or "").split("\n")]
    return {
        "lines": lines, "alignment": 2,
        "margin_l": 0.0, "margin_r": 0.0, "margin_v": 0.0,
        "size": 0.0, "family": "", "bold": False, "italic": False,
        "primary": (255, 255, 255), "outline": (17, 25, 20),
        "border": 2.0, "shadow": 0.0, "res_x": 0, "res_y": 0, "background": True,
    }


CJK_CHAR_RE = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff01-\uff60\u3000-\u303f]")
CJK_FONT_KEYS = ("microsoft yahei", "microsoft yahei ui", "微软雅黑", "yahei",
                 "simhei", "黑体", "simsun", "宋体", "kaiti", "楷体", "ms mincho",
                 "meiryo", "malgun gothic", "noto sans", "source han", "思源")


def needs_cjk(text: str) -> bool:
    return bool(CJK_CHAR_RE.search(text or ""))


@functools.lru_cache(maxsize=192)
def preview_font(size: int, bold: bool = False, family: str = "", cjk: bool = False):
    """按 ASS 字体名取 PIL 字体（带缓存）；拉丁字体排不下中文时回退到微软雅黑。"""
    if ImageFont is None:
        return None
    size = max(6, int(size))
    key = (family or "").strip().casefold()
    candidates: list[Path] = []
    entry = ASS_FONT_FILES.get(key)
    if entry and not (cjk and not any(token in key for token in CJK_FONT_KEYS)):
        regular, bold_file = entry
        candidates.append(FONTS_DIR / (bold_file if bold else regular))
        candidates.append(FONTS_DIR / regular)
    if bold:
        candidates.append(FONTS_DIR / "msyhbd.ttc")
    candidates.extend(Path(path) for path in FONT_PATHS)
    for candidate in candidates:
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return _font(size)


def css_colour(value: str):
    text = (value or "").strip().lower()
    if not text:
        return None
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        if len(digits) >= 6:
            try:
                return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
            except ValueError:
                return None
        return None
    return CSS_COLOURS.get(text)


def ass_colour(value, default=(255, 255, 255)) -> tuple[int, int, int]:
    """ASS 颜色 &HAABBGGRR / &HBBGGRR（可带 \\c / \\1c 前缀）→ RGB。"""
    text = str(value or "").strip()
    marker = text.casefold().find("&h")
    if marker != -1:
        text = text[marker + 2:]
    else:
        text = text.lstrip("0123456789cChH&")
    text = text.rstrip("&")
    if text[:1].casefold() == "h":
        text = text[1:]
    try:
        number = int(text, 16)
    except ValueError:
        return default
    if len(text) > 6:                      # &HAABBGGRR：丢弃 AA
        number &= 0xFFFFFF
    return (number & 0xFF, number >> 8 & 0xFF, number >> 16 & 0xFF)


def ass_number(value, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float(default)


def ass_flag(value, default: bool = False) -> bool:
    try:
        return float(str(value).strip()) != 0
    except (TypeError, ValueError):
        return default


def parse_ass_metadata(content: str) -> dict:
    """提取 [Script Info] 的 PlayRes 与 [V4+ Styles] 样式表。"""
    play_res = (384, 288)
    styles: dict[str, dict] = {}
    section = ""
    style_format: list[str] = []
    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().casefold()
            style_format = []
            continue
        if not line or line.startswith(";") or line.startswith("!"):
            continue
        if section == "script info" and ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().casefold()
            if key == "playresx":
                play_res = (int(ass_number(value, play_res[0])), play_res[1])
            elif key == "playresy":
                play_res = (play_res[0], int(ass_number(value, play_res[1])))
        elif section in ("v4+ styles", "v4 styles"):
            lowered = line.casefold()
            if lowered.startswith("format:"):
                style_format = [part.strip().casefold() for part in line[7:].split(",")]
            elif lowered.startswith("style:") and style_format:
                values = line[6:].split(",", len(style_format) - 1)
                values += [""] * (len(style_format) - len(values))
                data = dict(zip(style_format, (value.strip() for value in values)))
                if data.get("name"):
                    styles[data["name"]] = data
    return {"play_res": play_res, "styles": styles}


def parse_ass_dialogues(content: str) -> dict[tuple[int, int], tuple[str, str]]:
    """(start_ms, end_ms) → (样式名, 原始对白文本)，用于按 ASS 标签渲染预览。"""
    result: dict[tuple[int, int], tuple[str, str]] = {}
    in_events = False
    field_count = 0
    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_events = line[1:-1].strip().casefold() == "events"
            field_count = 0
            continue
        if not in_events or not line:
            continue
        lowered = line.casefold()
        if lowered.startswith("format:"):
            field_count = len(line[7:].split(","))
            continue
        if not lowered.startswith("dialogue:"):
            continue
        total_fields = field_count or 10
        parts = line[9:].split(",", max(0, total_fields - 1))
        if len(parts) < 10:
            continue
        try:
            start_ms = subtitles.parse_ass_time(parts[1].strip())
            end_ms = subtitles.parse_ass_time(parts[2].strip())
        except (ValueError, AttributeError):
            continue
        result[(int(start_ms), int(end_ms))] = (parts[3].strip(), parts[-1])
    return result


def ass_style_to_render(style: dict | None) -> dict:
    style = style or {}
    alignment = int(ass_number(style.get("alignment", 2), 2))
    if not 1 <= alignment <= 9:
        alignment = 2
    return {
        "alignment": alignment,
        "size": max(1.0, ass_number(style.get("fontsize", 48), 48.0)),
        "family": str(style.get("fontname") or ""),
        "primary": ass_colour(style.get("primarycolour")),
        "outline": ass_colour(style.get("outlinecolour"), (16, 16, 16)),
        "border": max(0.0, ass_number(style.get("outline", 2), 2.0)),
        "shadow": max(0.0, ass_number(style.get("shadow", 0), 0.0)),
        "bold": ass_flag(style.get("bold", 0)),
        "italic": ass_flag(style.get("italic", 0)),
        "margin_l": ass_number(style.get("marginl", 10), 10.0),
        "margin_r": ass_number(style.get("marginr", 10), 10.0),
        "margin_v": ass_number(style.get("marginv", 10), 10.0),
    }


def apply_ass_overrides(body: str, state: dict, base: dict,
                        alignment: int, drawing: bool) -> tuple[int, bool]:
    for part in body.split("\\"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("an") and part[2:].isdigit():
            alignment = int(part[2:])
        elif part.startswith("a") and part[1:].isdigit():
            alignment = ASS_LEGACY_ALIGNMENT.get(int(part[1:]), alignment)
        elif part.startswith("i") and (part[1:].isdigit() or len(part) == 1):
            state["italic"] = len(part) > 1 and part[1:] != "0"
        elif part.startswith("b") and (part[1:].isdigit() or len(part) == 1):
            state["bold"] = len(part) > 1 and part[1:] != "0"
        elif "&h" in part.casefold() and part[:1] in ("c", "C", "1"):
            state["colour"] = ass_colour(part)
        elif part.startswith("p") and part[1:].isdigit():
            drawing = int(part[1:]) > 0
        elif part == "r":
            state.update(bold=base["bold"], italic=base["italic"],
                         colour=base["primary"])
    return alignment, drawing


def build_ass_caption(raw_text: str, base: dict) -> dict:
    """把 ASS 对白文本解析为预览块：处理 {} 覆盖标签、\\N/\\n/\\h 与矢量绘图。"""
    block = default_preview_block("")
    for key in ("alignment", "size", "family", "primary", "outline", "border",
                "shadow", "bold", "italic", "margin_l", "margin_r", "margin_v"):
        block[key] = base.get(key, block[key])
    state = {"bold": block["bold"], "italic": block["italic"], "colour": block["primary"]}
    alignment = int(block["alignment"])
    drawing = False
    lines: list[list[dict]] = [[]]
    for index, token in enumerate(ASS_BLOCK_RE.split(raw_text or "")):
        if index % 2 == 1:
            if token.strip():
                alignment, drawing = apply_ass_overrides(token, state, block,
                                                         alignment, drawing)
            continue
        text = re.sub(r"\\[Nn]", "\n", token).replace("\\h", "\u00a0")
        if not text or drawing:
            continue
        for offset, chunk in enumerate(text.split("\n")):
            if offset:
                lines.append([])
            if chunk:
                lines[-1].append({"text": chunk, "bold": state["bold"],
                                  "italic": state["italic"], "underline": False,
                                  "colour": state["colour"]})
    block["lines"] = lines
    block["alignment"] = alignment
    return block


class _SubtitleRunsParser(HTMLParser):
    """把 SRT/VTT/SMI 的内联标签转成带样式的片段。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[list[dict]] = [[]]
        self._bold = 0
        self._italic = 0
        self._underline = 0
        self._colour = None
        self._colour_stack: list = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.lines.append([])
        elif tag in ("b", "strong"):
            self._bold += 1
        elif tag in ("i", "em"):
            self._italic += 1
        elif tag == "u":
            self._underline += 1
        elif tag == "font":
            self._colour_stack.append(self._colour)
            for name, value in attrs:
                if name == "color" and value:
                    parsed = css_colour(value)
                    if parsed:
                        self._colour = parsed
        elif tag in ("p", "div") and self.lines and self.lines[-1]:
            self.lines.append([])

    def handle_endtag(self, tag):
        if tag in ("b", "strong"):
            self._bold = max(0, self._bold - 1)
        elif tag in ("i", "em"):
            self._italic = max(0, self._italic - 1)
        elif tag == "u":
            self._underline = max(0, self._underline - 1)
        elif tag == "font" and self._colour_stack:
            self._colour = self._colour_stack.pop()

    def handle_data(self, data):
        if not data:
            return
        for offset, chunk in enumerate(data.split("\n")):
            if offset:
                self.lines.append([])
            if chunk:
                self.lines[-1].append({
                    "text": chunk, "bold": bool(self._bold), "italic": bool(self._italic),
                    "underline": bool(self._underline), "colour": self._colour})


def lookup_ass_style(ass_meta: dict, name: str | None) -> dict:
    styles = ass_meta.get("styles") or {}
    wanted = (name or "").strip()
    for key, value in styles.items():
        if key.casefold() == wanted.casefold():
            return ass_style_to_render(value)
    if styles:
        return ass_style_to_render(next(iter(styles.values())))
    return ass_style_to_render(None)


def build_preview_caption(fmt, parsed_text: str, style_name,
                          ass_meta: dict | None, ass_dialogue) -> dict:
    """按字幕文件格式生成预览块：ASS 用样式表 + 覆盖标签，SRT/VTT 用内联标签。"""
    if ass_meta is not None:
        raw_text, name = ((ass_dialogue[1], ass_dialogue[0]) if ass_dialogue
                          else (parsed_text, style_name))
        block = build_ass_caption(raw_text, lookup_ass_style(ass_meta, name))
        block["res_x"], block["res_y"] = ass_meta["play_res"]
        return block
    if fmt in (subtitles.SubFormat.SRT, subtitles.SubFormat.VTT,
               subtitles.SubFormat.SMI, subtitles.SubFormat.SUB):
        parser = _SubtitleRunsParser()
        try:
            parser.feed(parsed_text or "")
            parser.close()
        except Exception:
            return default_preview_block(parsed_text)
        block = default_preview_block("")
        block["lines"] = parser.lines
        return block
    return default_preview_block(parsed_text)


def ass_text_to_plain(raw_text: str) -> str:
    """ASS 原始对白 → 纯文本：去掉 {} 标签，\\N/\\n 转换行，\\h 转空格。"""
    text = ASS_BLOCK_RE.sub("", raw_text or "")
    text = re.sub(r"\\[Nn]", "\n", text).replace("\\h", " ")
    return text.strip()


def load_subtitle_document(path: str | Path) -> list[dict]:
    """解析字幕文件，并为每条字幕附上按文件自身格式解析的预览样式（_preview）。"""
    fmt = subtitles.detect_format(str(path))
    if fmt == subtitles.SubFormat.TXT:
        raise StudioError("纯文本文件没有时间轴，无法用于预览或封装。")
    raw_entries = subtitles.SubtitleParser.parse(str(path), fmt)
    if not raw_entries:
        raise StudioError(f"没有从字幕文件中解析到条目：{path}")
    entries = clean_subtitle_entries(raw_entries)
    ass_meta = None
    ass_dialogues: dict = {}
    if fmt in (subtitles.SubFormat.ASS, subtitles.SubFormat.SSA):
        try:
            content = subtitles.read_file_content(str(path))
        except Exception:
            content = ""
        if content:
            ass_meta = parse_ass_metadata(content)
            ass_dialogues = parse_ass_dialogues(content)
    for entry, raw in zip(entries, raw_entries):
        key = (int(raw.get("start_ms", 0)), int(raw.get("end_ms", 0)))
        dialogue = ass_dialogues.get(key)
        if dialogue is not None:
            # S_subtitles 的 ASS 解析会多切一个字段分隔符，这里按原始对白重新取文本
            entry["text"] = ass_text_to_plain(dialogue[1])
        entry["_preview"] = build_preview_caption(
            fmt, dialogue[1] if dialogue else raw.get("text", ""), raw.get("style"),
            ass_meta, dialogue)
    return entries


# ============================================================
# 播放时钟：以「可查询的音频位置」为主时钟（画面跟随音频）
#   1) libmpv  —— 进程内调用，audio-pts 精确、可在线 seek、暂停可续（首选）
#   2) waveOut —— 纯标准库 ctypes 流式播放，用「缓冲区播完事件」重新锚定
#   3) 都不可用 → 退回 ffplay + 墙钟（旧行为，仅作最后兜底）
# ============================================================
LIBMPV_ENV_KEYS = ("MSS_LIBMPV", "LIBMPV_PATH")
LIBMPV_FILENAME = "libmpv-2.dll"


def find_libmpv() -> Path | None:
    """在环境变量、程序目录与常见安装位置中查找 libmpv-2.dll。"""
    candidates: list[Path] = []
    for key in LIBMPV_ENV_KEYS:
        raw = os.environ.get(key)
        if raw:
            candidates.append(Path(raw))
    try:
        candidates.append(Path(__file__).resolve().parent / LIBMPV_FILENAME)
    except NameError:
        candidates.append(Path.cwd() / LIBMPV_FILENAME)
    except OSError:
        pass
    for root in (Path(r"D:\Program Files"), Path(r"C:\Program Files"),
                 Path(r"C:\Program Files (x86)")):
        candidates.append(root / "mpv" / LIBMPV_FILENAME)
        try:
            candidates.extend(sorted(root.glob(f"mpv*/{LIBMPV_FILENAME}")))
        except OSError:
            pass
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


_MPV_LIBRARY: dict = {"ready": False, "lib": None, "error": ""}


def _mpv_library():
    """加载 libmpv 并声明签名（成功一次后缓存）。"""
    if _MPV_LIBRARY["ready"]:
        return _MPV_LIBRARY["lib"]
    _MPV_LIBRARY["ready"] = True
    if os.name != "nt":
        _MPV_LIBRARY["error"] = "非 Windows 平台"
        return None
    path = find_libmpv()
    if path is None:
        _MPV_LIBRARY["error"] = f"未找到 {LIBMPV_FILENAME}"
        return None
    try:
        lib = ctypes.CDLL(str(path))
        lib.mpv_create.restype = ctypes.c_void_p
        lib.mpv_set_option_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                              ctypes.c_char_p]
        lib.mpv_set_option_string.restype = ctypes.c_int
        lib.mpv_initialize.argtypes = [ctypes.c_void_p]
        lib.mpv_initialize.restype = ctypes.c_int
        lib.mpv_command.argtypes = [ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_char_p)]
        lib.mpv_command.restype = ctypes.c_int
        lib.mpv_get_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                         ctypes.c_int, ctypes.c_void_p]
        lib.mpv_get_property.restype = ctypes.c_int
        lib.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
        lib.mpv_terminate_destroy.restype = None
        lib.mpv_error_string.argtypes = [ctypes.c_int]
        lib.mpv_error_string.restype = ctypes.c_char_p
    except OSError as exc:
        _MPV_LIBRARY["error"] = f"加载失败: {exc}"
        return None
    _MPV_LIBRARY["lib"] = lib
    return lib


class MpvAudioClock:
    """用 libmpv 只播音频，并以 audio-pts 作为主时钟。"""

    name = "mpv"
    supports_seek = True
    supports_pause = True
    MPV_FORMAT_FLAG = 3
    MPV_FORMAT_INT64 = 4
    MPV_FORMAT_DOUBLE = 5

    def __init__(self, lib, media_path, audio_ordinal: int = 0):
        self.lib = lib
        self.media_path = str(media_path)
        self.audio_ordinal = max(0, int(audio_ordinal or 0))
        self.handle = None
        self.error = ""
        self.started_at: float | None = None

    @classmethod
    def create(cls, media_path, audio_ordinal: int = 0) -> "MpvAudioClock | None":
        lib = _mpv_library()
        if lib is None:
            return None
        return cls(lib, media_path, audio_ordinal)

    # ------------------------------------------------------------ 内部
    def _command(self, *args) -> int:
        if self.handle is None:
            return -1
        argv = (ctypes.c_char_p * (len(args) + 1))(*[str(a).encode() for a in args], None)
        return self.lib.mpv_command(self.handle, argv)

    def _double(self, name: str) -> float | None:
        if self.handle is None:
            return None
        value = ctypes.c_double(0.0)
        if self.lib.mpv_get_property(self.handle, name.encode(), self.MPV_FORMAT_DOUBLE,
                                     ctypes.byref(value)) < 0:
            return None
        return float(value.value)

    def _flag(self, name: str) -> bool | None:
        if self.handle is None:
            return None
        value = ctypes.c_int(0)
        if self.lib.mpv_get_property(self.handle, name.encode(), self.MPV_FORMAT_FLAG,
                                     ctypes.byref(value)) < 0:
            return None
        return bool(value.value)

    def _int(self, name: str) -> int | None:
        if self.handle is None:
            return None
        value = ctypes.c_int64(0)
        if self.lib.mpv_get_property(self.handle, name.encode(), self.MPV_FORMAT_INT64,
                                     ctypes.byref(value)) < 0:
            return None
        return int(value.value)

    # ------------------------------------------------------------ 生命周期
    def start(self, position_seconds: float = 0.0) -> bool:
        self.stop()
        handle = self.lib.mpv_create()
        if not handle:
            self.error = "mpv_create 失败"
            return False
        self.handle = handle
        for name, value in (("vo", "null"), ("vid", "no"), ("audio-display", "no"),
                            ("config", "no"), ("terminal", "no"),
                            ("msg-level", "all=no"), ("idle", "yes"),
                            ("keep-open", "yes"), ("osc", "no"),
                            ("input-default-bindings", "no"),
                            ("audio-client-name", APP_TITLE)):
            self.lib.mpv_set_option_string(handle, name.encode(), value.encode())
        if self.lib.mpv_initialize(handle) < 0:
            self.error = "mpv_initialize 失败"
            self.stop()
            return False
        position = max(0.0, float(position_seconds or 0.0))
        if position > 0.001:                # 起始位置用 start 选项（loadfile 第 3 个参数是 index）
            self.lib.mpv_set_option_string(handle, b"start",
                                           f"{position:.3f}".encode())
        if self.audio_ordinal > 0:          # 跟随界面所选音轨（mpv 的 aid 从 1 起编号）
            self.lib.mpv_set_option_string(handle, b"aid",
                                           str(self.audio_ordinal + 1).encode())
        if self._command("loadfile", self.media_path, "replace") < 0:
            self.error = "loadfile 失败"
            self.stop()
            return False
        self.started_at = time.monotonic()
        return True

    def stop(self):
        handle, self.handle = self.handle, None
        self.started_at = None
        if handle is not None:
            try:
                self.lib.mpv_terminate_destroy(handle)
            except Exception:
                pass

    # ------------------------------------------------------------ 时钟 / 控制
    def position_ms(self) -> float | None:
        """音频实际播放位置（毫秒）；音频尚未真正开始返回 None。"""
        if self.handle is None:
            return None
        pts = self._double("audio-pts")
        if pts is None or pts <= 0:
            return None
        return pts * 1000.0

    @property
    def finished(self) -> bool:
        if self.handle is None:
            return False
        return bool(self._flag("idle-active")) or bool(self._flag("eof-reached"))

    def seek(self, position_seconds: float) -> bool:
        if self.handle is None:
            return False
        ok = self._command("seek", f"{max(0.0, float(position_seconds)):.3f}",
                           "absolute+exact") >= 0
        if ok:
            self.started_at = time.monotonic()
        return ok

    def set_paused(self, paused: bool) -> bool:
        if self.handle is None:
            return False
        return self._command("set", "pause", "yes" if paused else "no") >= 0


class WaveOutAudioClock:
    """纯标准库方案：ffmpeg 解码 PCM → waveOut 播放，用缓冲区播完事件当音频时钟。"""

    name = "waveOut"
    supports_seek = False
    supports_pause = False
    WAVE_FORMAT_PCM = 1
    WHDR_DONE = 0x00000001
    MMSYSERR_NOERROR = 0
    BUFFER_SECONDS = 0.06
    BUFFER_COUNT = 5

    class _WAVEFORMATEX(ctypes.Structure):
        _fields_ = [("wFormatTag", ctypes.c_ushort), ("nChannels", ctypes.c_ushort),
                    ("nSamplesPerSec", ctypes.c_uint),
                    ("nAvgBytesPerSec", ctypes.c_uint),
                    ("nBlockAlign", ctypes.c_ushort),
                    ("wBitsPerSample", ctypes.c_ushort), ("cbSize", ctypes.c_ushort)]

    class _WAVEHDR(ctypes.Structure):
        _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", ctypes.c_uint),
                    ("dwBytesRecorded", ctypes.c_uint), ("dwUser", ctypes.c_void_p),
                    ("dwFlags", ctypes.c_uint), ("dwLoops", ctypes.c_uint),
                    ("lpNext", ctypes.c_void_p), ("reserved", ctypes.c_void_p)]

    def __init__(self, ffmpeg, media_path, rate=48000, channels=2, audio_ordinal: int = 0):
        self.ffmpeg = ffmpeg
        self.media_path = str(media_path)
        self.audio_ordinal = max(0, int(audio_ordinal or 0))
        self.rate = int(rate)
        self.channels = int(channels)
        self.block = 2 * self.channels
        self.chunk = max(int(self.rate * self.BUFFER_SECONDS) * self.block,
                         self.rate * self.block // 10)
        self.error = ""
        self.handle = None
        self.process = None
        self.thread = None
        self.started_at: float | None = None
        self._stop = threading.Event()
        self._eof = False
        self._slots: list[dict] = []
        self._lock = threading.Lock()
        self._anchor_wall = 0.0
        self._anchor_ms = 0.0
        self._start_ms = 0.0
        self._written = 0
        self._played = 0
        self._winmm = ctypes.WinDLL("winmm") if os.name == "nt" else None
        if self._winmm is not None:
            self._winmm.waveOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p),
                                                ctypes.c_uint,
                                                ctypes.POINTER(self._WAVEFORMATEX),
                                                ctypes.c_void_p, ctypes.c_void_p,
                                                ctypes.c_uint]
            self._winmm.waveOutPrepareHeader.argtypes = [ctypes.c_void_p,
                                                         ctypes.POINTER(self._WAVEHDR),
                                                         ctypes.c_uint]
            self._winmm.waveOutWrite.argtypes = [ctypes.c_void_p,
                                                 ctypes.POINTER(self._WAVEHDR),
                                                 ctypes.c_uint]
            self._winmm.waveOutReset.argtypes = [ctypes.c_void_p]
            self._winmm.waveOutClose.argtypes = [ctypes.c_void_p]
            self._winmm.waveOutUnprepareHeader.argtypes = [ctypes.c_void_p,
                                                           ctypes.POINTER(self._WAVEHDR),
                                                           ctypes.c_uint]

    @classmethod
    def create(cls, ffmpeg, media_path, audio_ordinal: int = 0) -> "WaveOutAudioClock | None":
        if os.name != "nt" or not ffmpeg:
            return None
        return cls(ffmpeg, media_path, audio_ordinal=audio_ordinal)

    # ------------------------------------------------------------ 内部
    def _ms_of(self, byte_count: int) -> float:
        return byte_count / (self.rate * self.block) * 1000.0

    def _upgrade_clock(self):
        """把「已播完」的缓冲区字节累加为音频位置，并重新锚定时钟。"""
        progressed = False
        for slot in self._slots:
            if slot["counted"] or not slot["queued"]:
                continue
            if slot["header"].dwFlags & self.WHDR_DONE:
                slot["queued"] = False
                slot["counted"] = True
                self._played += slot["bytes"]
                progressed = True
        if progressed:
            self._anchor_ms = self._start_ms + self._ms_of(self._played)
            self._anchor_wall = time.monotonic()

    def _feed(self):
        pipe = self.process.stdout if self.process else None
        winmm = self._winmm
        if pipe is None or winmm is None:
            return
        while not self._stop.is_set():
            free = None
            for slot in self._slots:
                if not slot["queued"] and slot["counted"]:
                    free = slot
                    break
            self._upgrade_clock()
            if free is None:
                time.sleep(0.004)
                continue
            if self._eof:
                time.sleep(0.01)
                continue
            try:
                data = pipe.read(self.chunk)
            except (OSError, ValueError):
                data = b""
            if not data:
                self._eof = True
                continue
            usable = len(data) - (len(data) % self.block)
            if usable <= 0:
                continue
            buffer = free["buf"]
            ctypes.memmove(buffer, data[:usable], usable)
            free["data"] = data[:usable]
            free["bytes"] = usable
            header = free["header"]
            header.dwBufferLength = usable
            header.dwFlags &= ~self.WHDR_DONE      # 只清 DONE，保留 PREPARED
            if winmm.waveOutWrite(self.handle, ctypes.byref(header),
                                  ctypes.sizeof(header)) == self.MMSYSERR_NOERROR:
                free["queued"] = True
                free["counted"] = False
                self._written += usable
            else:
                free["bytes"] = 0
                self._eof = True

    # ------------------------------------------------------------ 生命周期
    def start(self, position_seconds: float = 0.0) -> bool:
        self.stop()
        winmm = self._winmm
        if winmm is None or not self.ffmpeg:
            self.error = "缺少 waveOut/ffmpeg"
            return False
        fmt = self._WAVEFORMATEX(self.WAVE_FORMAT_PCM, self.channels, self.rate,
                                 self.rate * self.block, self.block, 16, 0)
        handle = ctypes.c_void_p()
        code = winmm.waveOutOpen(ctypes.byref(handle),
                                 ctypes.c_uint(0xFFFFFFFF), ctypes.byref(fmt),
                                 0, 0, 0)
        if code != self.MMSYSERR_NOERROR:
            self.error = f"waveOutOpen 失败: {code}"
            return False
        self.handle = handle
        position = max(0.0, float(position_seconds or 0.0))
        self._start_ms = position * 1000.0
        self._anchor_ms = self._start_ms
        self._written = self._played = 0
        self._eof = False
        self._stop.clear()
        self._slots = []
        for _ in range(self.BUFFER_COUNT):
            buffer = ctypes.create_string_buffer(self.chunk)
            header = self._WAVEHDR()
            header.lpData = ctypes.cast(buffer, ctypes.c_void_p)
            header.dwBufferLength = self.chunk
            if winmm.waveOutPrepareHeader(self.handle, ctypes.byref(header),
                                          ctypes.sizeof(header)) != self.MMSYSERR_NOERROR:
                self.error = "waveOutPrepareHeader 失败"
                self.stop()
                return False
            self._slots.append({"header": header, "buf": buffer, "data": b"",
                                "bytes": 0, "queued": False, "counted": True})
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-ss", f"{position:.3f}", "-i", self.media_path,
                   "-map", f"0:a:{self.audio_ordinal}", "-vn",
                   "-f", "s16le", "-acodec", "pcm_s16le", "-ac", str(self.channels),
                   "-ar", str(self.rate), "-"]
        try:
            self.process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            self.error = f"无法启动 ffmpeg: {exc}"
            self.stop()
            return False
        self.thread = threading.Thread(target=self._feed, daemon=True)
        self.thread.start()
        self.started_at = time.monotonic()
        return True

    def stop(self):
        self._stop.set()
        process, self.process = self.process, None
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass
        if self.handle is not None and self._winmm is not None:
            try:
                self._winmm.waveOutReset(self.handle)
            except Exception:
                pass
        if self.thread is not None:
            self.thread.join(timeout=1.5)
            self.thread = None
        if self.handle is not None and self._winmm is not None:
            for slot in self._slots:
                try:
                    self._winmm.waveOutUnprepareHeader(
                        self.handle, ctypes.byref(slot["header"]),
                        ctypes.sizeof(slot["header"]))
                except Exception:
                    pass
            try:
                self._winmm.waveOutClose(self.handle)
            except Exception:
                pass
            self.handle = None
        self._slots = []
        self.started_at = None
        if process is not None:
            try:
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    # ------------------------------------------------------------ 时钟 / 控制
    def position_ms(self) -> float | None:
        if self.handle is None or self._played <= 0:
            return None
        return self._anchor_ms + (time.monotonic() - self._anchor_wall) * 1000.0

    @property
    def finished(self) -> bool:
        if not self._eof:
            return False
        return not any(slot["queued"] for slot in self._slots)

    def seek(self, position_seconds: float) -> bool:
        return False                       # 需要重建解码进程，由调用方重启

    def set_paused(self, paused: bool) -> bool:
        return False                       # 由调用方 stop/start 模拟


def create_audio_clock(media_path, ffmpeg: str | None, audio_ordinal: int = 0):
    """按 mpv → waveOut 的优先级创建音频主时钟；都不可用返回 None。

    audio_ordinal 为音频流序号（0 起），用于让播放跟随界面所选的音轨。
    """
    ordinal = max(0, int(audio_ordinal or 0))
    try:
        clock = MpvAudioClock.create(media_path, ordinal)
    except Exception:
        clock = None
    if clock is not None:
        return clock
    if ffmpeg:
        try:
            clock = WaveOutAudioClock.create(ffmpeg, media_path, ordinal)
        except Exception:
            clock = None
        if clock is not None:
            return clock
    return None


class SubtitleStudio:
    BASE_WIDTH = 1210
    BASE_HEIGHT = 812
    BASE_MIN_WIDTH = 940
    BASE_MIN_HEIGHT = 620
    MAX_CONCURRENT = 100

    def __init__(self, initial_path: str | None = None):
        enable_dpi_awareness()
        self.root = (TkinterDnD.Tk() if TkinterDnD else tk.Tk())
        self.root.title(APP_TITLE)
        set_console_echo(True)          # GUI 下也在命令行回显 Whisper / AI 的返回
        console_echo("GUI", "控制台回显已开启：Whisper 识别结果与 AI 接口返回都会打印在这里"
                            f"（关闭：set {CONSOLE_ECHO_ENV}=0）")
        self.root.configure(background=PALETTE["bg"])
        self.root.update_idletasks()
        self.dpi = window_dpi(self.root)
        self.scale = max(1.0, self.dpi / 96.0)
        self.root.tk.call("tk", "scaling", self.dpi / 72.0)
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        self.fonts: dict[str, tkfont.Font] = {}

        self.path_var = tk.StringVar()
        self.position_var = tk.DoubleVar(value=0.0)
        self.source_var = tk.StringVar(value="自动检测")
        self.target_var = tk.StringVar(value="中文（简体）")
        self.asr_language_var = tk.StringVar(value="自动检测")
        self.whisper_model_var = tk.StringVar(value=default_whisper_model())
        self.translation_model_var = tk.StringVar(value=default_translation_model())
        self.translation_concurrency_var = tk.StringVar(
            value=str(default_translation_concurrency()))
        self.subtitle_format_var = tk.StringVar(value="SRT")
        self.subtitle_language_var = tk.StringVar(value="原文")
        self.translate_source_var = tk.StringVar(value=TRANSLATE_SOURCE_ASR)
        self.mux_check_var = tk.BooleanVar(value=True)
        self.mux_threshold_var = tk.StringVar(value=str(DUPLICATE_THRESHOLD_DEFAULT))
        self.mux_track_kind_var = tk.StringVar(value=MUX_TRACK_ORIGINAL)
        self.group_translation_var = tk.BooleanVar(value=False)
        self.batch_size_var = tk.StringVar(value=str(subtitles.DEFAULT_BATCH_SIZE))
        self.context_lines_var = tk.StringVar(value=str(DEFAULT_CONTEXT_LINES))
        self.status_var = tk.StringVar(value="拖入视频 / 音频 / 字幕，或点击右上角「选择媒体…」")
        self.caption_var = tk.StringVar(
            value="播放时字幕按文件自身格式叠加渲染（不会烧录）；画面跟随音频时钟，"
                  "如有残留偏差可用右侧「同步」微调（正数 = 画面延后）。")
        self.sync_offset_var = tk.StringVar(value="0.0")
        self.sync_offset_var.trace_add("write", self._on_sync_change)
        self.time_label_var = tk.StringVar(value="00:00 / 00:00")
        self.media_stats_var = tk.StringVar(value="拖入媒体文件后显示轨道信息。")
        self.entry_stats_var = tk.StringVar(value="0 条")
        self.asr_status_var = tk.StringVar(value="")
        self.translate_progress_var = tk.StringVar(value="载入或识别字幕后即可开始翻译。")
        self.translate_source_hint_var = tk.StringVar(value="")
        self.export_hint_var = tk.StringVar(value="载入媒体后显示预计输出文件名。")
        self.export_file_hint_var = tk.StringVar(value="载入媒体后显示预计输出文件名。")
        self.model_detail_var = tk.StringVar(value="")
        self.plan_status_var = tk.StringVar(
            value="在「识别 / 翻译 / 导出与封装」里把设置加入计划，再添加要处理的文件。")
        self.plan_progress_var = tk.StringVar(value="总进度：未开始。")
        self.plan_token_var = tk.StringVar(value="Token：本文件 — · 总计 —")
        self.plan_continue_var = tk.BooleanVar(value=True)

        self.media_path: Path | None = None
        self.media_info: dict = {}
        self.audio_tracks: list[dict] = []
        self.embedded_subtitles: list[dict] = []
        self.external_subtitles: list[Path] = []
        self.entries: list[dict] = []
        self.original_entries: list[dict] = []
        self.translated: list[dict] = []
        self.subtitle_source: dict | None = None
        self.preview_photo = None
        self.video_capture = None
        self.video_fps = 25.0
        self.video_duration = 0.0
        self.video_playing = False
        self.video_after = None
        self.current_frame = None
        self.updating_position = False
        self.preview_audio_process = None
        self.audio_clock = None
        self._audio_clock_kind = ""
        self._play_anchor_wall = 0.0
        self._play_anchor_media = 0.0
        self._caption_cache: dict = {}
        self._photo_image = None
        self._photo_size: tuple[int, int] | None = None
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.translate_running = False
        self.translate_cancel_event: threading.Event | None = None
        self._audio_index = 0
        self._subtitle_index = 0
        self._subtitle_options: list[str] = ["不使用字幕", SUBTITLE_IMPORT_ENTRY]
        self._last_translation_model: str | None = None
        self._preview_message: str | None = None
        self._pending_subtitle: Path | None = None
        self._mux_tracks: list[dict] = []              # 要输出 / 压制的字幕轨（可多条）
        self._mux_sub_keep: dict[int, bool] = {}        # 内嵌字幕序号 → 是否保留
        self._mux_sub_vars: dict[int, tk.BooleanVar] = {}
        self._mux_sub_checks: list[ttk.Checkbutton] = []
        self._plan_steps: list[dict] = []
        self._plan_files: list[Path] = []
        self._plan_status: dict[str, str] = {}
        self._plan_cancel: threading.Event | None = None
        self.plan_running = False
        self._plan_ok = 0
        self._plan_failed = 0
        self._plan_skipped = 0
        self._skipped_notes: list[str] = []
        self._pending_mux: list[dict] = []   # 没找到对应字幕的外部字幕轨（结束后弹窗补选）
        self._plan_file_steps: dict[str, list[dict]] = {}   # 文件 → 本次执行的各步骤明细
        self._plan_total_steps = 0
        self._plan_steps_done = 0
        self._plan_tokens_total = 0
        self._plan_current_step_text = ""

        self._apply_theme()
        self._place_window()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self._closing = False
        self._poll_after = self.root.after(80, self._poll_events)
        self._dpi_after = self.root.after(1500, self._watch_dpi)
        if initial_path:
            self.root.after(250, lambda: self.load_media(initial_path))

    # ------------------------------------------------------- 高 DPI 适配与主题
    def px(self, value: float) -> int:
        return max(1, int(round(value * self.scale)))

    def _pick_family(self, stack: tuple[str, ...]) -> str:
        try:
            installed = {name.casefold() for name in tkfont.families(self.root)}
        except tk.TclError:
            installed = set()
        for name in stack:
            if name.casefold() in installed:
                return name
        try:
            return tkfont.nametofont("TkDefaultFont").actual("family")
        except tk.TclError:
            return "TkDefaultFont"

    def _apply_theme(self):
        ui_family = self._pick_family(UI_FONT_STACK)
        log_family = self._pick_family(LOG_FONT_STACK)
        self.fonts = {
            "base": tkfont.Font(root=self.root, family=ui_family, size=10),
            "small": tkfont.Font(root=self.root, family=ui_family, size=9),
            "section": tkfont.Font(root=self.root, family=ui_family, size=10, weight="bold"),
            "title": tkfont.Font(root=self.root, family=ui_family, size=17, weight="bold"),
            "button": tkfont.Font(root=self.root, family=ui_family, size=10),
            "mono": tkfont.Font(root=self.root, family=log_family, size=9),
        }
        p = self.px
        style = self.style
        style.configure("TFrame", background=PALETTE["bg"])
        style.configure("Header.TFrame", background=PALETTE["bg"])
        style.configure("Panel.TFrame", background=PALETTE["surface"])
        style.configure("TLabel", background=PALETTE["bg"], foreground=PALETTE["ink"],
                        font=self.fonts["base"])
        style.configure("Surface.TLabel", background=PALETTE["surface"],
                        foreground=PALETTE["ink"], font=self.fonts["base"])
        style.configure("Muted.TLabel", background=PALETTE["bg"],
                        foreground=PALETTE["muted"], font=self.fonts["small"])
        style.configure("SurfaceMuted.TLabel", background=PALETTE["surface"],
                        foreground=PALETTE["muted"], font=self.fonts["small"])
        style.configure("Title.TLabel", background=PALETTE["bg"], foreground=PALETTE["ink"],
                        font=self.fonts["title"])
        style.configure("Subtitle.TLabel", background=PALETTE["bg"],
                        foreground=PALETTE["muted"], font=self.fonts["small"])
        style.configure("Section.TLabel", background=PALETTE["surface"],
                        foreground=PALETTE["ink"], font=self.fonts["section"])
        style.configure("TButton", font=self.fonts["button"], padding=(p(12), p(6)))
        style.configure("Accent.TButton", font=self.fonts["button"], padding=(p(14), p(7)),
                        background=PALETTE["accent"], foreground="#ffffff",
                        borderwidth=0, focuscolor=PALETTE["accent"])
        style.map("Accent.TButton",
                  background=[("disabled", "#9dbfb1"), ("pressed", PALETTE["accent_hover"]),
                              ("active", PALETTE["accent_hover"])],
                  foreground=[("disabled", "#f2f7f4")])
        style.configure("Ghost.TButton", font=self.fonts["small"], padding=(p(8), p(3)))
        style.configure("TCombobox", padding=p(4))
        style.configure("TSpinbox", padding=p(3), arrowsize=p(12), font=self.fonts["base"])
        style.configure("TCheckbutton", background=PALETTE["surface"],
                        font=self.fonts["base"])
        style.map("TCheckbutton", background=[("active", PALETTE["surface"])])
        style.configure("TNotebook", background=PALETTE["bg"], borderwidth=0,
                        tabmargins=(p(2), p(4), 0, 0))
        style.configure("TNotebook.Tab", font=self.fonts["base"], padding=(p(14), p(7)))
        style.map("TNotebook.Tab",
                  background=[("selected", PALETTE["surface"])],
                  foreground=[("disabled", PALETTE["muted"]),
                              ("selected", PALETTE["accent"])])
        style.configure("Treeview", font=self.fonts["base"], rowheight=p(27),
                        background=PALETTE["surface"], fieldbackground=PALETTE["surface"],
                        foreground=PALETTE["ink"], borderwidth=0)
        style.map("Treeview", background=[("selected", PALETTE["accent_soft"])],
                  foreground=[("selected", PALETTE["ink"])])
        style.configure("Treeview.Heading", font=self.fonts["section"], padding=p(4))
        style.configure("TProgressbar", thickness=p(10), background=PALETTE["accent"],
                        troughcolor=PALETTE["accent_soft"], borderwidth=0)
        try:
            self.root.option_add("*TCombobox*Listbox.font", self.fonts["base"].name)
        except tk.TclError:
            pass

    def _place_window(self):
        width, height = self.px(self.BASE_WIDTH), self.px(self.BASE_HEIGHT)
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        width = max(self.px(720), min(width, screen_w - self.px(32)))
        height = max(self.px(520), min(height, screen_h - self.px(64)))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self._update_minsize(screen_w, screen_h)

    def _update_minsize(self, screen_w: int | None = None, screen_h: int | None = None):
        width_screen = int(screen_w) if screen_w is not None else self.root.winfo_screenwidth()
        height_screen = int(screen_h) if screen_h is not None else self.root.winfo_screenheight()
        self.root.minsize(
            min(self.px(self.BASE_MIN_WIDTH), int(width_screen * 0.9)),
            min(self.px(self.BASE_MIN_HEIGHT), int(height_screen * 0.85)),
        )

    def _watch_dpi(self):
        if self._closing:
            return
        try:
            dpi = window_dpi(self.root)
        except tk.TclError:
            return
        if dpi != self.dpi:
            self._apply_dpi(dpi)
        try:
            self._dpi_after = self.root.after(1500, self._watch_dpi)
        except tk.TclError:
            pass

    def _apply_dpi(self, dpi: int):
        self.dpi = int(dpi)
        self.scale = max(1.0, self.dpi / 96.0)
        self.root.tk.call("tk", "scaling", self.dpi / 72.0)
        self._rebuild_ui()

    def _rebuild_ui(self):
        """DPI 变化时按新缩放重建整套界面，同时保留播放位置与日志。"""
        position = self.position_var.get() if self.video_capture is not None else None
        log_content = ""
        if getattr(self, "log_text", None) is not None:
            try:
                log_content = self.log_text.get("1.0", "end-1c")
            except tk.TclError:
                log_content = ""
        self._close_video()
        for child in self.root.winfo_children():
            if isinstance(child, tk.Toplevel):
                continue
            child.destroy()
        self._apply_theme()
        self._build()
        self._update_minsize()
        if log_content:
            self.log_text.configure(state="normal")
            self.log_text.insert("1.0", log_content)
            self.log_text.configure(state="disabled")
            self.log_text.see("end")
        if self.media_path is not None and position is not None:
            has_video = any(stream.get("codec_type") == "video"
                            for stream in (self.media_info.get("streams") or []))
            self._open_video(self.media_path, has_video)
            if self.video_capture is not None:
                self._seek_video(str(position))

    def _restore_action_states(self):
        self._set_busy(self.busy)
        self.cancel_translate_button.configure(
            state="normal" if self.translate_running else "disabled")
        if not self.translate_running:
            self._update_translate_hint()

    def _register_drop_targets(self):
        if DND_FILES is None:
            return
        register = getattr(self.root, "drop_target_register", None)
        bind = getattr(self.root, "dnd_bind", None)
        if not (callable(register) and callable(bind)):
            return
        try:
            register(DND_FILES)
            bind("<<Drop>>", self._drop_media)
            bind("<<DropEnter>>", lambda _event: self._set_drop_hover(True))
            bind("<<DropLeave>>", lambda _event: self._set_drop_hover(False))
        except tk.TclError:
            pass

    def _set_drop_hover(self, active: bool):
        label = getattr(self, "drop_label", None)
        if label is None:
            return
        try:
            label.configure(bg=PALETTE["drop_hover"] if active else PALETTE["drop_idle"])
        except tk.TclError:
            pass

    def _build(self):
        root = self.root
        root.configure(background=PALETTE["bg"])

        header = ttk.Frame(root, style="Header.TFrame",
                           padding=(self.px(18), self.px(14), self.px(18), self.px(6)))
        header.pack(fill="x")
        title_block = ttk.Frame(header, style="Header.TFrame")
        title_block.pack(side="left")
        ttk.Label(title_block, text="字幕工作台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_block, text="本地 Whisper 识别 · AI 并发翻译 · 字幕轨无损封装",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(self.px(2), 0))
        actions = ttk.Frame(header, style="Header.TFrame")
        actions.pack(side="right")
        self.load_subtitle_button = ttk.Button(actions, text="载入字幕…",
                                               command=self._choose_subtitle_file)
        self.load_subtitle_button.pack(side="right")
        self.choose_button = ttk.Button(actions, text="选择媒体…", style="Accent.TButton",
                                        command=self._choose_media)
        self.choose_button.pack(side="right", padx=(0, self.px(10)))

        self.drop_label = tk.Label(
            root,
            text="拖入视频 / 音频 / 字幕文件 —— 支持一次拖入「媒体 + 同名字幕」，字幕也可单独拖入替换",
            anchor="center", bg=PALETTE["drop_idle"], fg="#2f5a49",
            font=self.fonts["base"], padx=self.px(14), pady=self.px(8),
            highlightthickness=0)
        self.drop_label.pack(fill="x", padx=self.px(18), pady=(0, self.px(8)))
        self._register_drop_targets()
        root.bind("<space>", self._on_space)

        self.path_label = ttk.Label(root, textvariable=self.path_var, style="Subtitle.TLabel",
                                    anchor="w",
                                    padding=(self.px(20), 0, self.px(20), self.px(4)))
        self.path_label.pack(fill="x")

        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=self.px(18), pady=(0, self.px(10)))
        left = ttk.Frame(body, style="Panel.TFrame")
        right = ttk.Frame(body, style="Panel.TFrame")
        body.add(left, weight=3)
        body.add(right, weight=2)

        self.preview_canvas = tk.Canvas(left, bg=PALETTE["preview"], highlightthickness=0,
                                        height=self.px(400))
        self.preview_canvas.pack(fill="both", expand=True,
                                 padx=self.px(10), pady=(self.px(10), 0))
        self.preview_canvas.bind("<Configure>", self._resize_video_canvas)
        self._draw_preview_placeholder("拖入媒体后在此预览画面\n播放时字幕会实时叠加（不会烧录）")

        transport = ttk.Frame(left, style="Panel.TFrame",
                              padding=(self.px(10), self.px(8), self.px(10), self.px(2)))
        transport.pack(fill="x")
        self.play_button = ttk.Button(transport, text="▶ 播放", style="Accent.TButton",
                                      command=self._toggle_playback, state="disabled")
        self.play_button.pack(side="left")
        self.prev_button = ttk.Button(transport, text="⏮", width=3,
                                      command=lambda: self._jump_entry(-1), state="disabled")
        self.prev_button.pack(side="left", padx=(self.px(6), 0))
        self.next_button = ttk.Button(transport, text="⏭", width=3,
                                      command=lambda: self._jump_entry(1), state="disabled")
        self.next_button.pack(side="left", padx=(self.px(3), 0))
        self.seek_scale = ttk.Scale(transport, from_=0, to=1, variable=self.position_var,
                                    command=self._seek_video, state="disabled")
        self.seek_scale.pack(side="left", fill="x", expand=True, padx=self.px(8))
        ttk.Label(transport, textvariable=self.time_label_var, style="SurfaceMuted.TLabel",
                  width=13, anchor="e").pack(side="right")
        self.sync_spinbox = ttk.Spinbox(transport, from_=-1.0, to=1.0, increment=0.05,
                                        width=6, textvariable=self.sync_offset_var)
        self.sync_spinbox.pack(side="right", padx=(self.px(6), 0))
        ttk.Label(transport, text="同步", style="SurfaceMuted.TLabel").pack(
            side="right", padx=(self.px(6), 0))
        ttk.Label(left, textvariable=self.caption_var, style="SurfaceMuted.TLabel",
                  justify="left", wraplength=self.px(680)).pack(
            fill="x", padx=self.px(12), pady=(self.px(4), self.px(10)))

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        media_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=self.px(12))
        asr_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=self.px(12))
        self.notebook.add(media_tab, text="媒体与字幕")
        self.notebook.add(asr_tab, text="识别")

        # ---- 媒体与字幕 ----
        ttk.Label(media_tab, textvariable=self.media_stats_var, style="SurfaceMuted.TLabel",
                  justify="left", wraplength=self.px(360)).pack(anchor="w")
        ttk.Label(media_tab, text="音轨", style="Section.TLabel").pack(
            anchor="w", pady=(self.px(10), 0))
        self.audio_box = ttk.Combobox(media_tab, state="readonly", values=["未检测到音轨"])
        self.audio_box.pack(fill="x", pady=(self.px(4), 0))
        self.audio_box.bind("<<ComboboxSelected>>", self._remember_audio_selection)
        ttk.Label(media_tab, text="字幕来源", style="Section.TLabel").pack(
            anchor="w", pady=(self.px(10), 0))
        self.subtitle_box = ttk.Combobox(media_tab, state="readonly", values=["不使用字幕"])
        self.subtitle_box.pack(fill="x", pady=(self.px(4), 0))
        self.subtitle_box.bind("<<ComboboxSelected>>", self._select_subtitle)
        list_head = ttk.Frame(media_tab, style="Panel.TFrame")
        list_head.pack(fill="x", pady=(self.px(12), self.px(4)))
        ttk.Label(list_head, text="字幕条目", style="Section.TLabel").pack(side="left")
        ttk.Label(list_head, textvariable=self.entry_stats_var,
                  style="SurfaceMuted.TLabel").pack(side="right")
        tree_wrap = ttk.Frame(media_tab, style="Panel.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_wrap, columns=("index", "time", "text"),
                                 show="headings", selectmode="browse")
        self.tree.heading("index", text="#")
        self.tree.heading("time", text="开始")
        self.tree.heading("text", text="字幕文本")
        self.tree.column("index", width=self.px(42), stretch=False, anchor="center")
        self.tree.column("time", width=self.px(88), stretch=False, anchor="center")
        self.tree.column("text", width=self.px(230))
        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.tag_configure("odd", background=PALETTE["surface_alt"])
        self.tree.tag_configure("even", background=PALETTE["surface"])
        self.tree.bind("<<TreeviewSelect>>", self._select_entry)

        # ---- 识别 ----
        ttk.Label(asr_tab, text="Whisper 模型", style="Section.TLabel").pack(anchor="w")
        asr_model_row = ttk.Frame(asr_tab, style="Panel.TFrame")
        asr_model_row.pack(fill="x", pady=(self.px(4), 0))
        ttk.Combobox(asr_model_row, textvariable=self.whisper_model_var, state="readonly",
                     values=WHISPER_MODELS, width=14).pack(side="left")
        linked = "、".join(cached_whisper_models()) or "无"
        ttk.Label(asr_model_row, text=f"已缓存：{linked}", style="SurfaceMuted.TLabel").pack(
            side="left", padx=(self.px(10), 0))
        ttk.Label(asr_tab, text="音频语言（Whisper 提示，可自动检测）",
                  style="Section.TLabel").pack(anchor="w", pady=(self.px(12), 0))
        ttk.Combobox(asr_tab, textvariable=self.asr_language_var, state="readonly",
                     values=list(LANGUAGES)).pack(fill="x", pady=(self.px(4), 0))
        ttk.Label(asr_tab, text="未缓存的模型首次使用需要联网下载权重；识别推理在本机完成。",
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(360)).pack(anchor="w", pady=(self.px(12), 0))
        asr_actions = ttk.Frame(asr_tab, style="Panel.TFrame")
        asr_actions.pack(fill="x", side="bottom")
        self.asr_status_label = ttk.Label(asr_actions, textvariable=self.asr_status_var,
                                          style="SurfaceMuted.TLabel", justify="left",
                                          wraplength=self.px(170))
        self.asr_status_label.pack(side="left", fill="x", expand=True)
        self.asr_button = ttk.Button(asr_actions, text="识别所选音轨", style="Accent.TButton",
                                     command=self._start_transcription)
        self.asr_button.pack(side="right")
        self.plan_asr_button = ttk.Button(asr_actions, text="加入计划",
                                          command=self._plan_add_asr)
        self.plan_asr_button.pack(side="right", padx=(0, self.px(6)))

        # ---- 翻译 ----
        translate_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=self.px(12))
        self.notebook.add(translate_tab, text="翻译")

        ttk.Label(translate_tab, text="翻译模型", style="Section.TLabel").pack(anchor="w")
        self.translation_model_box = ttk.Combobox(
            translate_tab, textvariable=self.translation_model_var, state="readonly",
            values=[item["name"] for item in translation_models()])
        self.translation_model_box.pack(fill="x", pady=(self.px(4), 0))
        self.translation_model_box.bind("<<ComboboxSelected>>",
                                       self._on_translation_model_change)
        ttk.Label(translate_tab, textvariable=self.model_detail_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(360)).pack(anchor="w", pady=(self.px(4), 0))

        concurrency_row = ttk.Frame(translate_tab, style="Panel.TFrame")
        concurrency_row.pack(fill="x", pady=(self.px(10), 0))
        ttk.Label(concurrency_row, text="并发请求数", style="Section.TLabel").pack(side="left")
        self.concurrency_spinbox = ttk.Spinbox(
            concurrency_row, from_=1, to=self.MAX_CONCURRENT, width=6,
            textvariable=self.translation_concurrency_var)
        self.concurrency_spinbox.pack(side="left", padx=self.px(8))
        ttk.Label(concurrency_row, text="1–100 · 受 API 限额约束",
                  style="SurfaceMuted.TLabel").pack(side="left")

        group_row = ttk.Frame(translate_tab, style="Panel.TFrame")
        group_row.pack(fill="x", pady=(self.px(10), 0))
        self.group_check = ttk.Checkbutton(
            group_row, text="分组翻译", variable=self.group_translation_var,
            command=self._toggle_group_translation)
        self.group_check.pack(side="left")
        ttk.Label(group_row, text="每组行数", style="SurfaceMuted.TLabel").pack(
            side="left", padx=(self.px(12), self.px(4)))
        self.batch_size_spinbox = ttk.Spinbox(
            group_row, from_=subtitles.BATCH_SIZE_MIN, to=subtitles.BATCH_SIZE_MAX,
            textvariable=self.batch_size_var, width=5, state="disabled")
        self.batch_size_spinbox.pack(side="left")
        ttk.Label(group_row, text=f"（{subtitles.BATCH_SIZE_MIN}–{subtitles.BATCH_SIZE_MAX} 行）",
                  style="SurfaceMuted.TLabel").pack(side="left", padx=(self.px(4), 0))
        ttk.Label(translate_tab,
                  text="逐条对齐更严格；分组把多行合并成一次请求，请求数更少。",
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(520)).pack(anchor="w", pady=(self.px(2), 0))

        lang_grid = ttk.Frame(translate_tab, style="Panel.TFrame")
        lang_grid.pack(fill="x", pady=(self.px(12), 0))
        lang_grid.columnconfigure(1, weight=1)
        ttk.Label(lang_grid, text="源语言", style="Surface.TLabel").grid(
            row=0, column=0, sticky="w", pady=self.px(2))
        ttk.Combobox(lang_grid, textvariable=self.source_var, state="readonly",
                     values=list(LANGUAGES)).grid(row=0, column=1, sticky="ew",
                                                  padx=self.px(8), pady=self.px(2))
        ttk.Label(lang_grid, text="目标语言", style="Surface.TLabel").grid(
            row=1, column=0, sticky="w", pady=self.px(2))
        ttk.Combobox(lang_grid, textvariable=self.target_var, state="readonly",
                     values=[lang for lang in LANGUAGES if lang != "自动检测"]).grid(
            row=1, column=1, sticky="ew", padx=self.px(8), pady=self.px(2))
        ttk.Label(lang_grid, text="翻译来源", style="Surface.TLabel").grid(
            row=2, column=0, sticky="w", pady=self.px(2))
        translate_source_box = ttk.Combobox(lang_grid, textvariable=self.translate_source_var,
                                            state="readonly", values=list(TRANSLATE_SOURCES))
        translate_source_box.grid(row=2, column=1, sticky="ew", padx=self.px(8),
                                  pady=self.px(2))
        translate_source_box.bind("<<ComboboxSelected>>",
                                  lambda _event: self._on_translate_source_change())
        ttk.Label(translate_tab, textvariable=self.translate_source_hint_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(520)).pack(anchor="w", pady=(self.px(4), 0))

        context_row = ttk.Frame(translate_tab, style="Panel.TFrame")
        context_row.pack(fill="x", pady=(self.px(8), 0))
        ttk.Label(context_row, text="上下文句数", style="Section.TLabel").pack(side="left")
        self.context_spinbox = ttk.Spinbox(
            context_row, from_=0, to=CONTEXT_LINES_MAX, width=5,
            textvariable=self.context_lines_var)
        self.context_spinbox.pack(side="left", padx=self.px(8))
        ttk.Label(context_row, text=f"前后各 N 条非空字幕只作参考（0–{CONTEXT_LINES_MAX}，0 = 关闭）",
                  style="SurfaceMuted.TLabel").pack(side="left")

        plan_row = ttk.Frame(translate_tab, style="Panel.TFrame")
        plan_row.pack(fill="x", pady=(self.px(8), 0))
        ttk.Label(plan_row, text="把当前翻译设置记入计划：",
                  style="SurfaceMuted.TLabel").pack(side="left")
        self.plan_translate_button = ttk.Button(plan_row, text="加入计划",
                                                command=self._plan_add_translate)
        self.plan_translate_button.pack(side="right")

        self.translate_progress = ttk.Progressbar(translate_tab, mode="determinate",
                                                  maximum=1, value=0)
        self.translate_progress.pack(fill="x", pady=(self.px(12), 0))
        progress_row = ttk.Frame(translate_tab, style="Panel.TFrame")
        progress_row.pack(fill="x", pady=(self.px(6), 0))
        ttk.Label(progress_row, textvariable=self.translate_progress_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(200)).pack(side="left", fill="x", expand=True)
        self.cancel_translate_button = ttk.Button(progress_row, text="取消翻译",
                                                  command=self._cancel_translation,
                                                  state="disabled")
        self.cancel_translate_button.pack(side="right")
        self.translate_button = ttk.Button(progress_row, text="开始翻译", style="Accent.TButton",
                                           command=self._start_translation)
        self.translate_button.pack(side="right", padx=(0, self.px(8)))

        log_head = ttk.Frame(translate_tab, style="Panel.TFrame")
        log_head.pack(fill="x", pady=(self.px(12), self.px(4)))
        ttk.Label(log_head, text="运行日志（批次进度 / 降级 / 错误）",
                  style="Section.TLabel").pack(side="left")
        ttk.Button(log_head, text="清空", style="Ghost.TButton",
                   command=self._clear_log).pack(side="right")
        log_wrap = ttk.Frame(translate_tab, style="Panel.TFrame")
        log_wrap.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_wrap, height=5, wrap="word", font=self.fonts["mono"],
                                bg=PALETTE["surface_alt"], fg=PALETTE["ink"], bd=0,
                                highlightthickness=1,
                                highlightbackground=PALETTE["border"],
                                state="disabled", padx=self.px(6), pady=self.px(4))
        log_scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        # ---- 导出与封装（两大块：① 只导出单个字幕文件；② 只管压制字幕，互不影响）----
        export_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=self.px(12))
        self.notebook.add(export_tab, text="导出与封装")

        ttk.Label(export_tab, text="① 导出字幕文件（单个文件）",
                  style="Section.TLabel").pack(anchor="w")
        file_grid = ttk.Frame(export_tab, style="Panel.TFrame")
        file_grid.pack(fill="x", pady=(self.px(4), 0))
        file_grid.columnconfigure(1, weight=1)
        ttk.Label(file_grid, text="字幕格式", style="Surface.TLabel").grid(
            row=0, column=0, sticky="w", pady=self.px(3))
        self.export_format_box = ttk.Combobox(file_grid,
                                              textvariable=self.subtitle_format_var,
                                              state="readonly", values=("SRT", "ASS", "VTT"))
        self.export_format_box.grid(row=0, column=1, sticky="ew", padx=self.px(8),
                                    pady=self.px(3))
        self.export_format_box.bind("<<ComboboxSelected>>",
                                    lambda _event: self._update_export_file_hint())
        ttk.Label(file_grid, text="字幕语言", style="Surface.TLabel").grid(
            row=1, column=0, sticky="w", pady=self.px(3))
        self.subtitle_language_box = ttk.Combobox(file_grid,
                                                  textvariable=self.subtitle_language_var,
                                                  state="readonly",
                                                  values=("原文", "译文", "双语"))
        self.subtitle_language_box.grid(row=1, column=1, sticky="ew", padx=self.px(8),
                                        pady=self.px(3))
        self.subtitle_language_box.bind("<<ComboboxSelected>>",
                                        self._on_subtitle_language_change)
        ttk.Label(export_tab, textvariable=self.export_file_hint_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(520)).pack(anchor="w", pady=(self.px(4), 0))
        file_actions = ttk.Frame(export_tab, style="Panel.TFrame")
        file_actions.pack(fill="x", pady=(self.px(4), 0))
        self.export_button = ttk.Button(file_actions, text="导出字幕文件",
                                        command=self._start_export)
        self.export_button.pack(side="left")
        self.plan_export_button = ttk.Button(file_actions, text="加入计划",
                                             command=self._plan_add_export)
        self.plan_export_button.pack(side="left", padx=(self.px(6), 0))

        ttk.Label(export_tab, text="② 压制字幕（不烧录画面）",
                  style="Section.TLabel").pack(anchor="w", pady=(self.px(6), 0))
        # 压制按钮先占住底部，避免内容变高时被挤出可视区
        mux_actions = ttk.Frame(export_tab, style="Panel.TFrame")
        mux_actions.pack(fill="x", side="bottom", pady=(self.px(6), 0))
        self.mux_button = ttk.Button(mux_actions, text="压制字幕", style="Accent.TButton",
                                     command=self._start_mux)
        self.mux_button.pack(side="left")
        self.plan_mux_button = ttk.Button(mux_actions, text="加入计划",
                                          command=self._plan_add_mux)
        self.plan_mux_button.pack(side="left", padx=(self.px(6), 0))
        track_row = ttk.Frame(export_tab, style="Panel.TFrame")
        track_row.pack(fill="x", pady=(self.px(4), 0))
        track_row.columnconfigure(0, weight=1)
        self.mux_track_kind_box = ttk.Combobox(track_row,
                                              textvariable=self.mux_track_kind_var,
                                              state="readonly", values=MUX_TRACK_KINDS)
        self.mux_track_kind_box.grid(row=0, column=0, sticky="ew")
        self.mux_track_kind_box.bind("<<ComboboxSelected>>", self._on_mux_track_kind)
        self.mux_track_add_button = ttk.Button(track_row, text="添加", style="Ghost.TButton",
                                               command=self._add_mux_track)
        self.mux_track_add_button.grid(row=0, column=1, padx=(self.px(6), 0))
        mux_tracks_wrap = ttk.Frame(export_tab, style="Panel.TFrame")
        mux_tracks_wrap.pack(fill="x", pady=(self.px(6), 0))
        self.mux_tracks_tree = ttk.Treeview(mux_tracks_wrap,
                                            columns=("order", "label", "language"),
                                            show="headings", selectmode="browse", height=5)
        self.mux_tracks_tree.heading("order", text="#")
        self.mux_tracks_tree.heading("label", text="要压制的字幕轨")
        self.mux_tracks_tree.heading("language", text="语言")
        self.mux_tracks_tree.column("order", width=self.px(36), stretch=False,
                                    anchor="center")
        self.mux_tracks_tree.column("label", width=self.px(228))
        self.mux_tracks_tree.column("language", width=self.px(70), stretch=False)
        self.mux_tracks_tree.tag_configure("first", foreground=PALETTE["accent"])
        mux_tracks_scroll = ttk.Scrollbar(mux_tracks_wrap, orient="vertical",
                                          command=self.mux_tracks_tree.yview)
        self.mux_tracks_tree.configure(yscrollcommand=mux_tracks_scroll.set)
        self.mux_tracks_tree.pack(side="left", fill="both", expand=True)
        mux_tracks_scroll.pack(side="right", fill="y")
        mux_track_actions = ttk.Frame(export_tab, style="Panel.TFrame")
        mux_track_actions.pack(fill="x", pady=(self.px(2), 0))
        for text, command in (("移除", self._remove_mux_track),
                              ("设为默认", self._set_default_mux_track),
                              ("清空", self._clear_mux_tracks)):
            ttk.Button(mux_track_actions, text=text, style="Ghost.TButton",
                       command=command).pack(side="left", padx=(0, self.px(6)))
        ttk.Label(export_tab, textvariable=self.export_hint_var, style="SurfaceMuted.TLabel",
                  justify="left", wraplength=self.px(520)).pack(
            anchor="w", pady=(self.px(4), 0))
        mux_check_row = ttk.Frame(export_tab, style="Panel.TFrame")
        mux_check_row.pack(fill="x", pady=(self.px(4), 0))
        self.mux_check = ttk.Checkbutton(
            mux_check_row, text="压制前检查重复字幕（同语言且内容雷同才算重复）",
            variable=self.mux_check_var, command=self._update_mux_hint)
        self.mux_check.pack(side="left")
        ttk.Label(mux_check_row, text="本地阈值", style="SurfaceMuted.TLabel").pack(
            side="left", padx=(self.px(10), self.px(4)))
        self.mux_threshold_spinbox = ttk.Spinbox(
            mux_check_row, from_=DUPLICATE_AI_LOW, to=100, width=5,
            textvariable=self.mux_threshold_var, command=self._update_mux_hint)
        self.mux_threshold_spinbox.pack(side="left")
        ttk.Label(mux_check_row, text=f"%（{DUPLICATE_AI_LOW}–阈值交 AI 判语义）",
                  style="SurfaceMuted.TLabel").pack(side="left", padx=(self.px(4), 0))
        mux_subs_head = ttk.Frame(export_tab, style="Panel.TFrame")
        mux_subs_head.pack(fill="x", pady=(self.px(8), self.px(2)))
        ttk.Button(mux_subs_head, text="全部删除", style="Ghost.TButton",
                   command=lambda: self._set_all_mux_subs(False)).pack(side="right")
        ttk.Button(mux_subs_head, text="全部保留", style="Ghost.TButton",
                   command=lambda: self._set_all_mux_subs(True)).pack(
            side="right", padx=(0, self.px(6)))
        ttk.Label(mux_subs_head, text="原有内嵌字幕（取消勾选 = 压制时删除该字幕轨）",
                  style="Section.TLabel").pack(side="left")
        # 字幕轨很多时限高滚动，避免把导出页撑高（三个按钮 / 下拉框仍始终可见）
        mux_subs_wrap = ttk.Frame(export_tab, style="Panel.TFrame")
        mux_subs_wrap.pack(fill="x")
        self.mux_subs_canvas = tk.Canvas(mux_subs_wrap, bg=PALETTE["surface"],
                                        highlightthickness=0, bd=0,
                                        height=self.px(48))
        mux_subs_scroll = ttk.Scrollbar(mux_subs_wrap, orient="vertical",
                                        command=self.mux_subs_canvas.yview)
        self.mux_subs_canvas.configure(yscrollcommand=mux_subs_scroll.set)
        self.mux_subs_canvas.pack(side="left", fill="x", expand=True)
        mux_subs_scroll.pack(side="right", fill="y")
        self.mux_subs_frame = ttk.Frame(self.mux_subs_canvas, style="Panel.TFrame")
        self._mux_subs_window = self.mux_subs_canvas.create_window(
            (0, 0), window=self.mux_subs_frame, anchor="nw")
        self.mux_subs_frame.bind(
            "<Configure>",
            lambda _event: self.mux_subs_canvas.configure(
                scrollregion=self.mux_subs_canvas.bbox("all")))
        self.mux_subs_canvas.bind(
            "<Configure>",
            lambda event: self.mux_subs_canvas.itemconfigure(self._mux_subs_window,
                                                            width=event.width))
        for widget in (self.mux_subs_canvas, self.mux_subs_frame):
            widget.bind("<MouseWheel>", self._on_mux_subs_wheel)

        # ---- 计划任务 ----
        plan_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=self.px(12))
        self.notebook.add(plan_tab, text="计划任务")
        # 按钮先占住底部（否则内容变高时会被挤到可视区外）
        plan_actions = ttk.Frame(plan_tab, style="Panel.TFrame")
        plan_actions.pack(fill="x", side="bottom")
        self.plan_stop_button = ttk.Button(plan_actions, text="停止",
                                          command=self._stop_plan, state="disabled")
        self.plan_stop_button.pack(side="right", padx=(0, self.px(6)))
        self.plan_button = ttk.Button(plan_actions, text="开始执行计划",
                                      style="Accent.TButton", command=self._start_plan)
        self.plan_button.pack(side="right")
        ttk.Label(plan_tab, text="已加入的计划步骤（按顺序执行）",
                  style="Section.TLabel").pack(anchor="w")
        steps_head = ttk.Frame(plan_tab, style="Panel.TFrame")
        steps_head.pack(fill="x", pady=(self.px(4), self.px(4)))
        self.plan_step_buttons = []
        for text, command in (("清空", self._plan_clear_steps),
                              ("删除", self._plan_remove_step),
                              ("下移", lambda: self._plan_move_step(1)),
                              ("上移", lambda: self._plan_move_step(-1))):
            button = ttk.Button(steps_head, text=text, style="Ghost.TButton",
                                command=command)
            button.pack(side="right", padx=(self.px(4), 0))
            self.plan_step_buttons.append(button)
        steps_wrap = ttk.Frame(plan_tab, style="Panel.TFrame")
        steps_wrap.pack(fill="both", expand=True)
        self.plan_tree = ttk.Treeview(steps_wrap, columns=("order", "page", "detail"),
                                     show="headings", selectmode="browse", height=3)
        self.plan_tree.heading("order", text="#")
        self.plan_tree.heading("page", text="页面")
        self.plan_tree.heading("detail", text="设置")
        self.plan_tree.column("order", width=self.px(34), stretch=False, anchor="center")
        self.plan_tree.column("page", width=self.px(78), stretch=False, anchor="center")
        self.plan_tree.column("detail", width=self.px(240))
        steps_scroll = ttk.Scrollbar(steps_wrap, orient="vertical",
                                     command=self.plan_tree.yview)
        self.plan_tree.configure(yscrollcommand=steps_scroll.set)
        self.plan_tree.pack(side="left", fill="both", expand=True)
        steps_scroll.pack(side="right", fill="y")
        self.plan_tree.tag_configure("odd", background=PALETTE["surface_alt"])
        self.plan_tree.tag_configure("even", background=PALETTE["surface"])

        ttk.Label(plan_tab, text="要处理的文件（可多选，逐个执行整套计划）",
                  style="Section.TLabel").pack(anchor="w", pady=(self.px(8), 0))
        files_head = ttk.Frame(plan_tab, style="Panel.TFrame")
        files_head.pack(fill="x", pady=(self.px(4), self.px(4)))
        self.plan_file_buttons = []
        for text, command in (("清空", self._plan_clear_files),
                              ("移除", self._plan_remove_file),
                              ("添加当前媒体", self._plan_add_current),
                              ("添加文件…", self._plan_choose_files)):
            button = ttk.Button(files_head, text=text, style="Ghost.TButton",
                                command=command)
            button.pack(side="right", padx=(self.px(4), 0))
            self.plan_file_buttons.append(button)
        files_wrap = ttk.Frame(plan_tab, style="Panel.TFrame")
        files_wrap.pack(fill="both", expand=True)
        self.plan_files_tree = ttk.Treeview(files_wrap,
                                            columns=("order", "name", "status", "tokens"),
                                            show="headings", selectmode="browse", height=5)
        self.plan_files_tree.heading("order", text="#")
        self.plan_files_tree.heading("name", text="文件 / 步骤")
        self.plan_files_tree.heading("status", text="状态")
        self.plan_files_tree.heading("tokens", text="Token")
        self.plan_files_tree.column("order", width=self.px(46), stretch=False,
                                    anchor="center")
        self.plan_files_tree.column("name", width=self.px(170))
        self.plan_files_tree.column("status", width=self.px(120), stretch=False)
        self.plan_files_tree.column("tokens", width=self.px(72), stretch=False,
                                    anchor="e")
        files_scroll = ttk.Scrollbar(files_wrap, orient="vertical",
                                     command=self.plan_files_tree.yview)
        self.plan_files_tree.configure(yscrollcommand=files_scroll.set)
        self.plan_files_tree.pack(side="left", fill="both", expand=True)
        files_scroll.pack(side="right", fill="y")
        self.plan_files_tree.tag_configure("running", background=PALETTE["accent_soft"])
        self.plan_files_tree.tag_configure("done", background="#e4f3ea")
        self.plan_files_tree.tag_configure("failed", background="#f8e5e1")
        self.plan_files_tree.tag_configure("skipped", background="#fdf3d8")
        self.plan_files_tree.tag_configure("step", foreground=PALETTE["muted"])

        plan_options = ttk.Frame(plan_tab, style="Panel.TFrame")
        plan_options.pack(fill="x", pady=(self.px(8), 0))
        self.plan_continue_check = ttk.Checkbutton(
            plan_options, text="某个文件失败后继续处理下一个",
            variable=self.plan_continue_var)
        self.plan_continue_check.pack(side="left")

        self.plan_progress = ttk.Progressbar(plan_tab, mode="determinate",
                                            maximum=1, value=0)
        self.plan_progress.pack(fill="x", pady=(self.px(8), 0))
        ttk.Label(plan_tab, textvariable=self.plan_progress_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(340)).pack(anchor="w", pady=(self.px(2), 0))
        self.plan_step_progress = ttk.Progressbar(plan_tab, mode="determinate",
                                                  maximum=1, value=0)
        self.plan_step_progress.pack(fill="x", pady=(self.px(6), 0))
        ttk.Label(plan_tab, textvariable=self.plan_status_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(340)).pack(anchor="w", pady=(self.px(2), 0))
        ttk.Label(plan_tab, textvariable=self.plan_token_var,
                  style="SurfaceMuted.TLabel", justify="left",
                  wraplength=self.px(340)).pack(anchor="w", pady=(self.px(2), 0))

        # ---- 底栏 ----
        footer = ttk.Frame(root, style="Header.TFrame",
                           padding=(self.px(18), 0, self.px(18), self.px(10)))
        footer.pack(fill="x")
        self.footer_progress = ttk.Progressbar(footer, mode="indeterminate",
                                               length=self.px(150))
        self.footer_progress.pack(side="right")
        ttk.Label(footer, textvariable=self.status_var, style="Subtitle.TLabel").pack(side="left")
        if DND_FILES is None:
            self.status_var.set("拖拽需安装 tkinterdnd2；仍可使用右上角按钮载入文件")

        self._sync_from_state()
        self._restore_action_states()

    # ------------------------------------------------------------- 界面状态同步
    def _selected_audio_ordinal(self) -> int:
        """当前「音轨」下拉框对应的音频流序号（0 起）；未选或无音轨时返回 0。"""
        if not self.audio_tracks:
            return 0
        try:
            index = int(self.audio_box.current())
        except (tk.TclError, ValueError):
            index = 0
        return max(0, min(index, len(self.audio_tracks) - 1))

    def _remember_audio_selection(self, _event=None):
        """记住音轨选择；正在播放时立即换到新音轨（重新起播音频时钟）。"""
        self._audio_index = self._selected_audio_ordinal()
        if not self.video_playing:
            return
        self._reset_play_clock(self.position_var.get())
        self._start_audio(self.position_var.get())
        self._append_log(f"已切换播放音轨：音轨 {self._audio_index + 1}")

    def _subtitle_option_count(self) -> int:
        """可选字幕来源数量（不含列表末端的「导入外部字幕文件…」占位项）。"""
        return max(1, len(self._subtitle_options) - 1)

    def _sync_from_state(self):
        self.path_var.set(str(self.media_path) if self.media_path else "")
        if self.audio_tracks:
            self.audio_box["values"] = [item["label"] for item in self.audio_tracks]
            self.audio_box.current(max(0, min(self._audio_index, len(self.audio_tracks) - 1)))
        else:
            self.audio_box["values"] = ["未检测到音轨"]
            self.audio_box.set("未检测到音轨")
        self.subtitle_box["values"] = list(self._subtitle_options)
        self.subtitle_box.current(
            max(0, min(self._subtitle_index, self._subtitle_option_count() - 1)))
        self._refresh_plan_tree()
        self._refresh_plan_files_tree()
        self._populate_tree()
        self._update_media_stats()
        self._refresh_mux_embedded_subs()
        self._refresh_mux_tracks_tree()
        self._update_translate_source_hint()
        self._refresh_translation_models()
        self._update_export_hint()
        self._update_entry_stats()

    def _rebuild_subtitle_options(self, select: int = 0):
        options = ["不使用字幕"]
        options.extend(item["label"] for item in self.embedded_subtitles)
        options.extend(f"外置字幕 · {path.name}" for path in self.external_subtitles)
        options.append(SUBTITLE_IMPORT_ENTRY)        # 末尾固定为「导入外部字幕文件…」
        self._subtitle_options = options
        self.subtitle_box["values"] = options
        index = max(0, min(select, self._subtitle_option_count() - 1))
        self._subtitle_index = index
        self.subtitle_box.current(index)

    def _adopt_external_subtitle(self, path: Path):
        if self.media_path is None:
            messagebox.showinfo("需要媒体", "请先载入媒体文件，再载入字幕。")
            return
        path = path.expanduser()
        if not path.is_file() or path.suffix.lower() not in SUBTITLE_EXTENSIONS:
            messagebox.showerror("无法打开", f"不是有效的字幕文件：{path}")
            return
        if path not in self.external_subtitles:
            self.external_subtitles.append(path)
        index = 1 + len(self.embedded_subtitles) + self.external_subtitles.index(path)
        self._rebuild_subtitle_options(select=index)
        self._update_media_stats()
        self._select_subtitle()
        self.status_var.set(f"已载入外置字幕：{path.name}")

    def _default_subtitle_dir(self) -> Path | None:
        """导入字幕对话框的默认目录：优先媒体所在目录，其次已载入字幕的目录。"""
        if self.media_path is not None:
            parent = self.media_path.parent
            if parent.is_dir():
                return parent
        for candidate in self.external_subtitles:
            if candidate.parent.is_dir():
                return candidate.parent
        return None

    def _choose_subtitle_file(self, restore_on_cancel: bool = False):
        """选择字幕文件（默认目录 = 媒体所在目录）；从「字幕来源」进入时，取消则回到原选项。"""
        options = {
            "title": "选择字幕文件",
            "filetypes": [("字幕文件", "*.srt *.ass *.ssa *.vtt *.sub *.smi"),
                          ("所有文件", "*.*")],
        }
        folder = self._default_subtitle_dir()
        if folder is not None:
            options["initialdir"] = str(folder)
        path = filedialog.askopenfilename(**options)
        if not path:
            if restore_on_cancel:
                self._restore_subtitle_selection()
            return
        self._adopt_external_subtitle(Path(path))

    def _restore_subtitle_selection(self):
        index = max(0, min(self._subtitle_index, self._subtitle_option_count() - 1))
        self._subtitle_index = index
        self.subtitle_box.current(index)

    def _append_log(self, text: str | None):
        widget = getattr(self, "log_text", None)
        if widget is None or not text:
            return
        widget.configure(state="normal")
        widget.insert("end", str(text).rstrip() + "\n")
        try:
            lines = int(widget.index("end-1c").split(".")[0])
            if lines > 400:
                widget.delete("1.0", f"{lines - 320}.0")
        except (tk.TclError, ValueError):
            pass
        widget.see("end")
        widget.configure(state="disabled")

    def _clear_log(self):
        widget = getattr(self, "log_text", None)
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    def _on_space(self, _event=None):
        """空格键播放/暂停；输入类控件获得焦点时不拦截。"""
        try:
            widget = self.root.focus_get()
        except (tk.TclError, KeyError):
            widget = None
        if isinstance(widget, (tk.Entry, tk.Text, ttk.Entry)):
            return None
        if self.video_capture is None:
            return None
        self._toggle_playback()
        return "break"

    def _draw_preview_placeholder(self, message: str | None):
        self._preview_message = message
        canvas = getattr(self, "preview_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        if not message:
            return
        width = max(canvas.winfo_width(), self.px(240))
        height = max(canvas.winfo_height(), self.px(160))
        canvas.create_text(width // 2, height // 2, text=message,
                           fill=PALETTE["preview_text"], font=self.fonts["base"],
                           justify="center", width=width - self.px(40))

    def _set_transport_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for widget in (self.play_button, self.prev_button, self.next_button):
            widget.configure(state=state)
        self.seek_scale.configure(state=state)

    def _update_media_stats(self):
        if self.media_path is None:
            self.media_stats_var.set("拖入媒体文件后显示轨道信息。")
            return
        details = []
        try:
            details.append(f"{self.media_path.stat().st_size / 1_048_576:,.1f} MB")
        except OSError:
            pass
        videos = [stream for stream in (self.media_info.get("streams") or [])
                  if stream.get("codec_type") == "video"]
        if videos:
            width = videos[0].get("width") or "?"
            height = videos[0].get("height") or "?"
            rate = str(videos[0].get("avg_frame_rate") or "")
            fps = None
            if "/" in rate:
                numerator, _, denominator = rate.partition("/")
                try:
                    denominator_value = float(denominator)
                    fps = float(numerator) / denominator_value if denominator_value else None
                except ValueError:
                    fps = None
            details.append(f"{width}×{height}" + (f" · {fps:.2f} fps" if fps else ""))
        try:
            duration = float((self.media_info.get("format") or {}).get("duration") or 0)
            if duration > 0:
                details.append(self._format_duration(duration))
        except (TypeError, ValueError):
            pass
        summary = " · ".join(details)
        self.media_stats_var.set(
            f"文件：{self.media_path.name}\n{summary}\n"
            f"{len(self.audio_tracks)} 音轨 · {len(self.embedded_subtitles)} 内嵌字幕 · "
            f"{len(self.external_subtitles)} 外置字幕")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"

    @staticmethod
    def _format_timestamp(milliseconds: float) -> str:
        total = max(0, int(milliseconds)) // 1000
        return f"{total // 3600:02d}:{(total // 60) % 60:02d}:{total % 60:02d}"

    def _update_entry_stats(self):
        count = len(self.entries)
        if count:
            filled = sum(1 for entry in self.entries if entry["text"].strip())
            translated = sum(1 for entry in self.translated
                             if entry.get("text", "").strip())
            text = f"{count} 条 · 可翻译 {filled} 条"
            if translated:
                text += f" · 已翻译 {translated} 条"
            self.entry_stats_var.set(text)
        else:
            self.entry_stats_var.set("0 条")
        self._update_translate_hint()

    def _update_translate_hint(self):
        if self.busy or self.translate_running:
            return
        if not self.entries:
            self.translate_progress_var.set("载入或识别字幕后即可开始翻译。")
            return
        filled = sum(1 for entry in (self.original_entries or self.entries)
                     if entry["text"].strip())
        mode = (f"分组 {self.batch_size_var.get()} 行/批"
                if self.group_translation_var.get() else "逐条")
        self.translate_progress_var.set(
            f"待翻译 {filled} 条 · {mode} · 上下文 ±{self.context_lines_var.get()} 条 · "
            f"并发 {self.translation_concurrency_var.get()}")

    def _update_export_hint(self):
        """同时刷新两块提示（单文件导出 / 压制）。"""
        self._update_export_file_hint()
        self._update_mux_hint()

    def _update_export_file_hint(self):
        """① 导出字幕文件：只写一个文件，与压制设置无关。"""
        if self.media_path is None:
            self.export_file_hint_var.set("载入媒体后显示预计输出文件名。")
            return
        mode = self.subtitle_language_var.get()
        suffix = SUBTITLE_OUTPUT_SUFFIX.get(mode, "original")
        name = f"{self.media_path.stem}_{suffix}.{self.subtitle_format_var.get().lower()}"
        self.export_file_hint_var.set(f"将输出到媒体同目录：{name}")

    def _update_mux_hint(self):
        """② 压制字幕：写明要压几条轨 / 删除几条内嵌字幕 / 是否做重复检查。"""
        self._refresh_mux_tracks_tree()
        threshold = self._mux_threshold()
        check_state = (f"压制前检查重复字幕：开（本地 ≥{threshold}%，不同语言不算重复）"
                       if self.mux_check_var.get() else "压制前检查重复字幕：关")
        if self.media_path is None:
            self.export_hint_var.set(f"载入媒体后显示预计输出文件名。{check_state}")
            return
        has_video = any(stream.get("codec_type") == "video"
                        for stream in (self.media_info.get("streams") or []))
        container = ".mkv" if has_video else ".mka"
        tracks = self._mux_tracks
        if tracks:
            labels = [self._mux_track_label(track) for track in tracks]
            shown = "、".join(labels[:3]) + ("…" if len(labels) > 3 else "")
            source = f"{len(labels)} 条字幕轨（{shown}）"
        else:
            source = f"生成的字幕（{self.subtitle_language_var.get()}）"
        drop = len(self._selected_drop_subtitles())
        extra = f"，删除 {drop} 条内嵌字幕" if drop else ""
        bound = sum(1 for track in tracks
                    if track.get("kind") == "external"
                    and subtitle_binding(self.media_path, track.get("path") or ""))
        bind_note = (f"{bound} 条外部字幕按文件名关系匹配（加入计划后自动换成各文件自己的字幕）；"
                     if bound else "")
        self.export_hint_var.set(
            f"将压制 {source} → {self.media_path.stem}_subtitled{container}{extra}"
            f"\n列表为空 = 按「字幕语言」压 1 条；第一条为默认轨。{bind_note}{check_state}")

    def _mux_threshold(self) -> int:
        """本地相似度阈值（百分比）；非法值回落到默认 70。"""
        try:
            value = int(float(self.mux_threshold_var.get()))
        except (TypeError, ValueError):
            return DUPLICATE_THRESHOLD_DEFAULT
        return max(DUPLICATE_AI_LOW, min(100, value))

    def _on_translate_source_change(self, _event=None):
        self._update_translate_source_hint()

    def _update_translate_source_hint(self):
        mode = self.translate_source_var.get()
        if mode == TRANSLATE_SOURCE_ASR:
            text = ("一律先识别「音轨」里选的那条音轨再用识别结果翻译"
                    "（计划里没加识别步骤也会自动补一次）。")
        elif mode == TRANSLATE_SOURCE_PROBE:
            text = (f"计划里没加识别步骤、或选不到那条音轨时，先取开头 "
                    f"{PROBE_SAMPLE_SECONDS // 60} 分钟用 {PROBE_WHISPER_MODEL} 探针校验已有内嵌字幕："
                    "对得上就直接用它翻译，对不上再完整识别。")
        elif mode == TRANSLATE_SOURCE_EMBEDDED:
            text = "直接用文件里的第一条内嵌字幕，不识别（会先让 AI 判语言）。"
        else:
            text = "直接用媒体同目录的同名字幕文件，不识别（会先让 AI 判语言）。"
        self.translate_source_hint_var.set(text)

    # ------------------------------------------- 要输出的字幕轨与内嵌字幕取舍
    def _selected_drop_subtitles(self) -> list[int]:
        """压制时要删除的内嵌字幕序号（0 起，按字幕流顺序）；未勾选的才算删除。"""
        return [item["ordinal"] for item in self.embedded_subtitles
                if not self._mux_sub_keep.get(item["ordinal"], True)]

    def _on_mux_track_kind(self, _event=None):
        """选中列表项时立即加入（选「外部字幕文件…」则弹文件框，可多选）。"""
        self._add_mux_track()

    def _mux_track_label(self, track: dict) -> str:
        if track.get("kind") == "external":
            return f"外部字幕 · {Path(track['path']).name}"
        return f"生成的字幕 · {track.get('mode') or '原文'}"

    def _mux_track_language(self, track: dict) -> str:
        """这条字幕轨写给播放器的语言标记（在导出时才取当前语言设置）。"""
        if track.get("language"):
            return str(track["language"])
        if track.get("kind") == "external":
            return guess_subtitle_language(track["path"])
        if (track.get("mode") or "原文") == "原文":
            return subtitle_language_code(self.source_var.get())
        return subtitle_language_code(self.target_var.get())

    def _refresh_mux_tracks_tree(self, select: int | None = None):
        tree = getattr(self, "mux_tracks_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for index, track in enumerate(self._mux_tracks):
            tree.insert("", "end", iid=str(index),
                        values=(index + 1, self._mux_track_label(track),
                                self._mux_track_language(track)),
                        tags=("first",) if index == 0 else ())
        if select is not None and 0 <= select < len(self._mux_tracks):
            tree.selection_set(str(select))
            tree.see(str(select))

    def _add_mux_track(self):
        """把当前选择的条目加入列表（外部字幕文件可一次多选）。"""
        kind = self.mux_track_kind_var.get()
        if kind == MUX_TRACK_EXTERNAL:
            paths = self._choose_mux_subtitle_files()
            if not paths:
                return
            for path in paths:
                self._mux_tracks.append({"kind": "external", "path": path,
                                         "language": None})
        else:
            mode = MUX_TRACK_MODES.get(kind, "原文")
            if any(track.get("kind") != "external" and track.get("mode") == mode
                   for track in self._mux_tracks):
                self.status_var.set(f"「{mode}」已经在列表里了。")
                return
            self._mux_tracks.append({"kind": "generated", "mode": mode,
                                     "language": None})
        self._refresh_mux_tracks_tree(select=len(self._mux_tracks) - 1)
        self._update_export_hint()
        self.status_var.set(f"已加入 {len(self._mux_tracks)} 条字幕轨")

    def _choose_mux_subtitle_files(self) -> list[Path]:
        """选择要压制的字幕文件（可多选；默认目录 = 媒体所在目录）。"""
        options = {
            "title": "选择要压制的字幕文件（可多选）",
            "filetypes": [("字幕文件", "*.srt *.ass *.ssa *.vtt *.sub *.smi *.lrc"),
                          ("所有文件", "*.*")],
        }
        folder = self._default_subtitle_dir()
        if folder is not None:
            options["initialdir"] = str(folder)
        chosen = filedialog.askopenfilenames(**options)
        paths: list[Path] = []
        seen = {str(track.get("path")) for track in self._mux_tracks}
        for item in chosen or ():
            path = Path(item)
            if str(path) in seen:
                continue
            seen.add(str(path))
            paths.append(path)
        return paths

    def _remove_mux_track(self):
        tree = getattr(self, "mux_tracks_tree", None)
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            self.status_var.set("先在列表里选中要移除的字幕轨。")
            return
        index = int(selection[0])
        if 0 <= index < len(self._mux_tracks):
            removed = self._mux_tracks.pop(index)
            self._append_log(f"已移出字幕轨：{self._mux_track_label(removed)}")
        self._refresh_mux_tracks_tree()
        self._update_export_hint()

    def _clear_mux_tracks(self):
        if not self._mux_tracks:
            return
        self._mux_tracks = []
        self._refresh_mux_tracks_tree()
        self._update_export_hint()
        self.status_var.set("已清空字幕轨列表（改为按「字幕语言」输出 1 条）")

    def _set_default_mux_track(self):
        """把选中的字幕轨移到最前（第一条 = 播放器默认显示的那条）。"""
        tree = getattr(self, "mux_tracks_tree", None)
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            self.status_var.set("先在列表里选中要设为默认的字幕轨。")
            return
        index = int(selection[0])
        if index <= 0 or index >= len(self._mux_tracks):
            return
        self._mux_tracks.insert(0, self._mux_tracks.pop(index))
        self._refresh_mux_tracks_tree(select=0)
        self._update_export_hint()
        self.status_var.set("已设为默认字幕轨（列表第一条）")

    def _mux_track_specs(self) -> list[dict] | None:
        """导出 / 计划统一用的字幕轨设置；列表为空返回 None（= 按「字幕语言」输出 1 条）。

        外部字幕会附带 `bind`（字幕相对当前媒体的命名关系）；加入计划后按同样的关系
        去每个文件旁边找对应字幕，避免把同一个字幕压进所有文件。
        """
        specs: list[dict] = []
        for track in self._mux_tracks:
            language = self._mux_track_language(track)
            if track.get("kind") == "external":
                path = Path(track["path"])
                specs.append({"kind": "external", "path": str(path),
                              "language": language, "title": path.stem,
                              "bind": subtitle_binding(self.media_path, path)})
            else:
                mode = track.get("mode") or "原文"
                specs.append({"kind": "generated", "mode": mode,
                              "language": language, "title": mode})
        return specs or None

    def _on_mux_subs_wheel(self, event):
        """内嵌字幕列表只占几行高，滚轮可以翻看剩下的行。"""
        self.mux_subs_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _refresh_mux_embedded_subs(self):
        """按当前媒体的内嵌字幕重建「保留 / 删除」勾选框（勾选 = 保留）。"""
        frame = getattr(self, "mux_subs_frame", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        self._mux_sub_vars = {}
        self._mux_sub_checks = []
        count = len(self.embedded_subtitles)
        if not count:
            ttk.Label(frame, text="当前媒体没有内嵌字幕。",
                      style="SurfaceMuted.TLabel").grid(row=0, column=0, sticky="w",
                                                        pady=(self.px(2), 0))
            return
        columns = 1 if count <= 6 else 2      # 字幕轨多时分两列，减少需要滚动的行数
        per_column = (count + columns - 1) // columns
        for position, item in enumerate(self.embedded_subtitles):
            ordinal = item["ordinal"]
            var = tk.BooleanVar(value=self._mux_sub_keep.get(ordinal, True))
            self._mux_sub_vars[ordinal] = var
            check = ttk.Checkbutton(
                frame, text=f"{item['label']} · {item['codec']}", variable=var,
                command=lambda o=ordinal, v=var: self._on_mux_sub_toggle(o, v))
            check.grid(row=position % per_column, column=position // per_column,
                       sticky="w", padx=(0, self.px(10)))
            self._mux_sub_checks.append(check)
        canvas = getattr(self, "mux_subs_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(0.0)

    def _on_mux_sub_toggle(self, ordinal: int, var: tk.BooleanVar):
        """勾选 / 取消内嵌字幕：记下取舍并刷新提示。"""
        self._mux_sub_keep[ordinal] = bool(var.get())
        self._update_export_hint()

    def _set_all_mux_subs(self, keep: bool):
        for ordinal, var in getattr(self, "_mux_sub_vars", {}).items():
            var.set(keep)
            self._mux_sub_keep[ordinal] = keep
        self._update_export_hint()

    def _on_subtitle_language_change(self, _event=None):
        self.refresh_preview()
        self._update_export_hint()

    def _choose_media(self):
        path = filedialog.askopenfilename(
            title="选择视频或音频",
            filetypes=[("媒体文件", "*." + " *.".join(sorted(ext[1:] for ext in MEDIA_EXTENSIONS))),
                       ("所有文件", "*.*")],
        )
        if path:
            self.load_media(path)

    def _drop_media(self, event):
        self._set_drop_hover(False)
        try:
            paths = [Path(item) for item in self.root.tk.splitlist(event.data)]
        except tk.TclError:
            return
        media = next((path for path in paths if path.suffix.lower() in MEDIA_EXTENSIONS), None)
        subtitle = next((path for path in paths if path.suffix.lower() in SUBTITLE_EXTENSIONS), None)
        if media is not None:
            if subtitle is not None:
                self._pending_subtitle = subtitle
            self.load_media(media)
        elif subtitle is not None:
            self._adopt_external_subtitle(subtitle)
        elif paths:
            self.status_var.set("拖入的文件既不是媒体也不是字幕，已忽略。")

    def load_media(self, path: str | Path):
        media_path = Path(path).expanduser()
        if media_path.suffix.lower() in SUBTITLE_EXTENSIONS:
            self._adopt_external_subtitle(media_path)
            return
        if not media_path.is_file() or media_path.suffix.lower() not in MEDIA_EXTENSIONS:
            messagebox.showerror("无法打开", "请选择有效的视频或音频文件。")
            return
        self._run_worker("正在读取媒体轨道…", self._load_media_worker, media_path)

    def _load_media_worker(self, media_path: Path):
        info = probe_media(media_path)
        audio, embedded, videos = probe_tracks(info)
        external = subtitle_candidates(media_path)
        return media_path, info, audio, embedded, videos, external

    def _choose_audio(self, loaded):
        media_path, info, audio, embedded, videos, external = loaded
        self._close_video()
        self.media_path, self.media_info = media_path, info
        self.audio_tracks, self.embedded_subtitles = audio, embedded
        self.external_subtitles = external
        self.entries, self.original_entries, self.translated = [], [], []
        self.subtitle_source = None
        self._audio_index = 0
        self._mux_sub_keep = {}          # 换文件后内嵌字幕序号重新映射
        self.path_var.set(str(media_path))
        if audio:
            self.audio_box["values"] = [item["label"] for item in audio]
            self.audio_box.current(0)
        else:
            self.audio_box["values"] = ["未检测到音轨"]
            self.audio_box.set("未检测到音轨")
        self._rebuild_subtitle_options(select=1 if (embedded or external) else 0)
        if self._subtitle_index > 0:
            self._select_subtitle()
        else:
            self._populate_tree()
            self.refresh_preview()
        self.asr_status_var.set("")
        self.translate_progress.configure(maximum=1, value=0)
        self._set_translate_running(False)
        self._update_media_stats()
        self._refresh_mux_embedded_subs()
        self._update_export_hint()
        self.status_var.set(
            f"已载入：{len(audio)} 条音轨 · {len(embedded)} 条内嵌字幕 · "
            f"{len(external)} 个同目录字幕"
        )
        self._append_log(f"已载入媒体：{media_path.name}（{len(audio)} 音轨 / "
                         f"{len(embedded)} 内嵌字幕 / {len(external)} 外置字幕）")
        self._open_video(media_path, bool(videos))
        pending = self._pending_subtitle
        if pending is not None:
            self._pending_subtitle = None
            self.root.after(80, lambda: self._adopt_external_subtitle(pending))

    def _select_subtitle(self, _event=None):
        if self.media_path is None:
            self._restore_subtitle_selection()
            return
        selected = self.subtitle_box.current()
        if selected < 0:
            selected = 0
        if selected >= self._subtitle_option_count():     # 选中了「导入外部字幕文件…」
            self._choose_subtitle_file(restore_on_cancel=True)
            return
        self._subtitle_index = selected
        if selected <= 0:
            self.entries, self.original_entries, self.translated = [], [], []
            self.subtitle_source = None
            self._populate_tree()
            self.refresh_preview()
            self.status_var.set("已关闭字幕显示。")
            return
        if selected <= len(self.embedded_subtitles):
            source = self.embedded_subtitles[selected - 1]
            self._run_worker("正在读取内嵌字幕…", self._load_subtitle_worker,
                             "embedded", source)
        else:
            index = selected - len(self.embedded_subtitles) - 1
            if index < len(self.external_subtitles):
                path = self.external_subtitles[index]
                self._run_worker("正在解析外置字幕…", self._load_subtitle_worker,
                                 "external", path)

    def _load_subtitle_worker(self, kind: str, source):
        media_path = self.media_path
        if media_path is None:
            raise StudioError("请先载入媒体文件。")
        if kind == "embedded":
            entries = extract_embedded_subtitle(media_path, source["stream_index"])
        else:
            entries = load_subtitle_document(source)
        return entries, {"kind": kind, "source": source}

    def _subtitle_loaded(self, result):
        self.entries, self.subtitle_source = result
        self.original_entries = copy.deepcopy(result[0])
        self.translated = []
        self._populate_tree()
        self.refresh_preview()
        self.status_var.set(f"字幕已载入：{len(self.entries)} 条")
        self._append_log(f"字幕已载入：{len(self.entries)} 条")

    def _populate_tree(self):
        if getattr(self, "tree", None) is None:
            return
        self.tree.delete(*self.tree.get_children())
        for index, entry in enumerate(self.entries):
            timestamp = self._format_timestamp(entry["start_ms"])
            text = entry["text"].replace("\n", " / ")
            self.tree.insert("", "end", iid=str(index),
                             values=(index + 1, timestamp, text),
                             tags=("odd" if index % 2 else "even",))
        self._update_entry_stats()

    def _selected_entry(self):
        try:
            index = int(self.tree.selection()[0])
            return self.entries[index]
        except (ValueError, IndexError):
            return None

    def _select_entry(self, _event=None):
        entry = self._selected_entry()
        if entry is not None:
            self._seek_video(entry["start_ms"] / 1000.0)

    def _jump_entry(self, delta: int):
        if not self.entries or self.video_capture is None:
            return
        current = self.position_var.get() * 1000
        starts = [entry["start_ms"] for entry in self.entries]
        if delta > 0:
            target = next((index for index, start in enumerate(starts)
                           if start > current + 1), len(starts) - 1)
        else:
            target = max((index for index, start in enumerate(starts)
                          if start < current - 1), default=0)
        target = max(0, min(target, len(self.entries) - 1))
        entry = self.entries[target]
        self._seek_video(entry["start_ms"] / 1000.0)
        if self.tree is not None:
            self.tree.selection_set(str(target))
            self.tree.see(str(target))

    def refresh_preview(self):
        if self.current_frame is None:
            return
        self._render_video_frame()

    def _open_video(self, media_path: Path, has_video: bool):
        self._set_transport_enabled(False)
        self._caption_cache = {}
        self._photo_image = None
        self._photo_size = None
        if not has_video:
            self._draw_preview_placeholder(
                "音频文件：没有视频画面\n播放时可叠加字幕预览（不会烧录）")
            self.time_label_var.set("音频")
            return
        if cv2 is None:
            message = opencv_missing_message()
            self._draw_preview_placeholder(message)
            self.status_var.set("缺少 OpenCV：无法预览视频画面（识别 / 翻译 / 导出仍可用）")
            self._append_log(message.replace("\n", " · "))
            return
        capture = cv2.VideoCapture(str(media_path))
        if not capture.isOpened():
            capture.release()
            self._draw_preview_placeholder("无法打开视频流进行预览")
            self.status_var.set("无法打开视频流进行预览")
            return
        self.video_capture = capture
        self.video_fps = max(1.0, float(capture.get(cv2.CAP_PROP_FPS) or 25.0))
        frame_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.video_duration = frame_count / self.video_fps if frame_count else 0.0
        self.seek_scale.configure(to=max(0.1, self.video_duration))
        self.position_var.set(0.0)
        self._set_transport_enabled(True)
        self._read_video_frame()
        self.time_label_var.set(f"00:00 / {self._format_clock(self.video_duration)}")

    # --------------------------------------------------- 播放时钟（按墙钟 + 音画同步）
    def _video_delay(self) -> float:
        """画面相对音频的额外延迟（秒）；音频主时钟已精确，仅用于微调残留偏差。"""
        try:
            value = float(self.sync_offset_var.get())
        except (TypeError, ValueError):
            return 0.0
        return max(-2.0, min(2.0, value))

    def _on_sync_change(self, *_args):
        if getattr(self, "video_playing", False):
            self._reset_play_clock(self.position_var.get())

    def _reset_play_clock(self, seconds: float):
        self._play_anchor_media = max(0.0, float(seconds or 0.0))
        self._play_anchor_wall = time.monotonic() + self._video_delay()

    def _capture_time_ms(self) -> float | None:
        """解码器当前时间（毫秒）：优先用帧号推算，退回 POS_MSEC。"""
        if self.video_capture is None:
            return None
        try:
            frame_index = float(self.video_capture.get(CAP_PROP_POS_FRAMES))
        except Exception:
            frame_index = 0.0
        if frame_index > 0:
            return max(0.0, (frame_index - 1.0) / self.video_fps * 1000.0)
        try:
            msec = float(self.video_capture.get(CAP_PROP_POS_MSEC))
        except Exception:
            return None
        return msec if msec > 0 else None

    def _start_playback(self):
        if self.video_capture is None:
            return
        self.video_playing = True
        self.play_button.configure(text="❚❚ 暂停")
        set_precise_timers(True)
        self._reset_play_clock(self.position_var.get())
        self._start_audio(self.position_var.get())
        self._schedule_video_tick(0)

    def _pause_playback(self):
        self.video_playing = False
        set_precise_timers(False)
        if hasattr(self, "play_button"):
            self.play_button.configure(text="▶ 播放")
        self._stop_audio()
        if self.video_after is not None:
            try:
                self.root.after_cancel(self.video_after)
            except tk.TclError:
                pass
            self.video_after = None

    def _schedule_video_tick(self, delay_ms: float | None = None):
        if not self.video_playing:
            return
        if delay_ms is None:
            delay_ms = 1000.0 / max(1.0, self.video_fps)
        self.video_after = self.root.after(max(1, int(round(delay_ms))),
                                           self._play_video_tick)

    def _toggle_playback(self):
        if self.video_capture is None:
            return
        if self.video_playing:
            self._pause_playback()
        else:
            self._start_playback()

    def _play_video_tick(self):
        self.video_after = None
        if not self.video_playing or self.video_capture is None:
            return
        interval_ms = 1000.0 / max(1.0, self.video_fps)
        target_ms, waiting = self._playback_target_ms()
        if waiting:                         # 音频尚未真正开始 → 保持当前帧继续等
            self._schedule_video_tick(15.0)
            return
        if self.video_duration > 0 and target_ms >= self.video_duration * 1000.0:
            self._pause_playback()
            self.updating_position = True
            self.position_var.set(self.video_duration)
            self.updating_position = False
            self.time_label_var.set(
                f"{self._format_clock(self.video_duration)} / "
                f"{self._format_clock(self.video_duration)}")
            return
        current_ms = self._capture_time_ms()
        if current_ms is None:
            current_ms = target_ms - interval_ms
        wait_ms = current_ms + interval_ms - target_ms
        if wait_ms > 1.0:                   # 还没到下一帧的显示时刻，按到期时刻再唤醒
            self._schedule_video_tick(wait_ms)
            return
        # 只有明显落后（超过约 1.8 帧）才丢帧，否则逐帧播放以免帧率减半
        skipped = 0
        while skipped < 24 and target_ms - current_ms >= interval_ms * 1.8:
            if not self.video_capture.grab():
                break
            skipped += 1
            probed = self._capture_time_ms()
            current_ms = probed if probed is not None else current_ms + interval_ms
        success, frame = self.video_capture.read()
        if not success:
            self._pause_playback()
            return
        self.current_frame = frame
        self._preview_message = None
        self._render_video_frame()
        shown_ms = self._capture_time_ms()
        if shown_ms is None:
            shown_ms = current_ms + interval_ms
        seconds_now = shown_ms / 1000.0
        if self.video_duration > 0:
            seconds_now = min(seconds_now, self.video_duration)
        self.updating_position = True
        self.position_var.set(seconds_now)
        self.updating_position = False
        self.time_label_var.set(
            f"{self._format_clock(seconds_now)} / "
            f"{self._format_clock(self.video_duration)}")
        # 睡到下一帧的到期时刻（音频时钟与墙钟共用同一公式；每帧只跳一次定时器）
        next_target, next_waiting = self._playback_target_ms()
        if next_waiting:
            delay_ms = interval_ms
        else:
            delay_ms = (shown_ms + interval_ms) - next_target
        self._schedule_video_tick(max(1.0, min(delay_ms, interval_ms * 3.0)))

    def _playback_target_ms(self) -> tuple[float, bool]:
        """画面目标时间（毫秒）与「是否需等音频开始」。

        音频主时钟可用时：目标 = 音频位置 - 「同步」偏移（正数 = 画面延后）。
        否则退回墙钟锚点（旧行为）；音频超时未开始也会自动退回。
        """
        clock = self.audio_clock
        if clock is not None:
            position = clock.position_ms()
            if position is not None and not clock.finished:
                return position - self._video_delay() * 1000.0, False
            started = getattr(clock, "started_at", None)
            if not clock.finished and started is not None \
                    and time.monotonic() - started < 2.0:
                return self._play_anchor_media * 1000.0, True
            if started is not None and not clock.finished \
                    and time.monotonic() - started >= 2.0:
                self._append_log("音频时钟 2 秒内未能开始，已改用墙钟播放（画面不再跟随音频）")
            self._stop_audio()
        elapsed = time.monotonic() - self._play_anchor_wall
        if elapsed < 0:
            return self._play_anchor_media * 1000.0, True
        return self._play_anchor_media * 1000.0 + elapsed * 1000.0, False

    def _seek_video(self, value):
        if self.updating_position or self.video_capture is None:
            return
        try:
            seconds = max(0.0, min(float(value), self.video_duration or float(value)))
        except (TypeError, ValueError):
            return
        self.video_capture.set(CAP_PROP_POS_MSEC, seconds * 1000.0)
        self._read_video_frame()
        if self.video_playing:              # 跳转后音频对齐：能在线 seek 就不重建进程
            self._reset_play_clock(seconds)
            clock = self.audio_clock
            if not (clock is not None and getattr(clock, "supports_seek", False)
                    and clock.seek(seconds)):
                self._start_audio(seconds)
            self._schedule_video_tick(0)

    def _read_video_frame(self):
        if self.video_capture is None:
            return
        success, frame = self.video_capture.read()
        if not success:
            return
        self.current_frame = frame
        self._preview_message = None
        current_ms = self._capture_time_ms()
        if current_ms is not None:
            seconds = current_ms / 1000.0
            if self.video_duration > 0:
                seconds = min(seconds, self.video_duration)
            self.updating_position = True
            self.position_var.set(seconds)
            self.updating_position = False
            self.time_label_var.set(
                f"{self._format_clock(seconds)} / {self._format_clock(self.video_duration)}")
        self._render_video_frame()

    @staticmethod
    def _format_clock(seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 60:02d}:{total % 60:02d}"

    # -------------------------------------------------- 字幕叠加（按文件格式渲染）
    @staticmethod
    def _entry_block(entry: dict) -> dict | None:
        block = entry.get("_preview")
        if block is None:
            block = default_preview_block(str(entry.get("text") or ""))
        if not any(block.get("lines") or []):
            return None
        return block

    @staticmethod
    def _plain_block(text: str) -> dict | None:
        if not (text or "").strip():
            return None
        return default_preview_block(text)

    def _caption_blocks_for(self, seconds: float) -> list[dict]:
        """当前时间点的字幕块，顺序为从下往上：译文在下、原文在上。"""
        mode = self.subtitle_language_var.get()
        original = self.original_entries or self.entries
        current = None
        for index, entry in enumerate(original):
            if entry["start_ms"] <= seconds * 1000 < entry["end_ms"]:
                current = index
                break
        if current is None:
            return []
        translated_text = ""
        if current < len(self.translated):
            translated_text = str(self.translated[current].get("text") or "")
        blocks: list[dict] = []
        if mode == "译文":
            block = (self._plain_block(translated_text)
                     or self._entry_block(original[current]))
            if block is not None:
                blocks.append(block)
        elif mode == "双语":
            translated_block = self._plain_block(translated_text)
            if translated_block is not None:
                blocks.append(translated_block)
            source_block = self._entry_block(original[current])
            if source_block is not None:
                blocks.append(source_block)
        else:
            source_block = self._entry_block(original[current])
            if source_block is not None:
                blocks.append(source_block)
        return blocks

    @staticmethod
    def _wrap_caption_lines(draw, block: dict, font_px: int, family: str,
                            available: float) -> list[list[dict]]:
        """按可用宽度在字符级换行，保留原有 \\N 换行与内联样式。"""
        lines: list[list[dict]] = []
        for source_line in block.get("lines") or []:
            current: list[dict] = []
            current_width = 0.0
            for run in source_line:
                text = str(run.get("text") or "")
                if not text:
                    continue
                bold = bool(run.get("bold") or block.get("bold"))
                italic = bool(run.get("italic") or block.get("italic"))
                font = preview_font(font_px, bold, family, needs_cjk(text))
                if font is None:
                    continue
                for char in text:
                    char_width = draw.textlength(char, font=font)
                    if current and current_width + char_width > available:
                        lines.append(current)
                        current = []
                        current_width = 0.0
                    if (current and current[-1]["bold"] == bold
                            and current[-1]["italic"] == italic
                            and current[-1].get("underline") == run.get("underline")
                            and current[-1].get("colour") == run.get("colour")):
                        current[-1]["text"] += char
                    else:
                        current.append({"text": char, "bold": bold, "italic": italic,
                                        "underline": run.get("underline"),
                                        "colour": run.get("colour")})
                    current_width += char_width
            lines.append(current)
        return lines

    def _draw_caption_blocks(self, image, draw, width: int, height: int,
                             blocks: list[dict]) -> float:
        """从下往上依次绘制字幕块，返回最上方块的可用底边（供后续块继续堆叠）。"""
        bottom = float(height) - self.px(8)
        if Image is None or ImageDraw is None:
            return bottom
        default_size = max(self.px(15), int(height * 0.042))
        for block in blocks:
            bottom = self._draw_caption_block(image, draw, width, height, block,
                                              default_size, bottom)
        return bottom

    def _draw_caption_block(self, image, draw, width: int, height: int, block: dict,
                            default_size: int, bottom_limit: float) -> float:
        pil_image, pil_draw = Image, ImageDraw
        if pil_image is None or pil_draw is None:   # 防御性检查（调用方已拦截）+ 类型收窄
            return bottom_limit
        res_x = int(block.get("res_x") or 0)
        res_y = int(block.get("res_y") or 0)
        scale_y = (height / res_y) if res_y else 1.0
        scale_x = (width / res_x) if res_x else scale_y
        size = float(block.get("size") or 0.0)
        font_px = max(10, min(int(round(size * scale_y)) if size else default_size,
                              int(height * 0.4)))
        border = max(0.0, float(block.get("border") or 0.0)) * (scale_y if res_y else 1.0)
        stroke = int(round(border)) if border >= 0.5 else 0
        family = str(block.get("family") or "")
        outline = tuple(block.get("outline") or (17, 25, 20))
        primary = tuple(block.get("primary") or (255, 255, 255))
        if res_x:
            margin_l = float(block.get("margin_l") or 0.0) * scale_x
            margin_r = float(block.get("margin_r") or 0.0) * scale_x
            margin_v = float(block.get("margin_v") or 0.0) * scale_y
        else:
            margin_l = margin_r = 0.0
            margin_v = self.px(18)
        alignment = int(block.get("alignment") or 2)
        if not 1 <= alignment <= 9:
            alignment = 2
        available = max(self.px(40), width - margin_l - margin_r - self.px(12))
        lines = self._wrap_caption_lines(draw, block, font_px, family, available)
        spacing = max(2, int(font_px * 0.18))
        prepared = []
        for line in lines:
            runs = []
            line_width = 0.0
            line_height = float(font_px)
            for run in line:
                font = preview_font(font_px, run["bold"], family, needs_cjk(run["text"]))
                if font is None:
                    continue
                bounds = draw.textbbox((0, 0), run["text"], font=font, stroke_width=stroke)
                run_width = float(bounds[2] - bounds[0])
                line_height = max(line_height, float(bounds[3] - bounds[1]))
                runs.append((run, font, run_width))
                line_width += run_width
            prepared.append((runs, line_width, line_height) if runs else None)
        if not any(prepared):
            return bottom_limit
        block_width = max(item[1] for item in prepared if item)
        block_height = (sum(item[2] for item in prepared if item)
                        + spacing * max(0, len(prepared) - 1))
        column = (alignment - 1) % 3                 # 0=左 1=中 2=右
        row = (alignment - 1) // 3                   # 0=下 1=中 2=上
        if column == 0:
            x = margin_l + self.px(6)
        elif column == 2:
            x = width - margin_r - block_width - self.px(6)
        else:
            x = (width - block_width) / 2.0
        if row == 0:
            y = bottom_limit - margin_v - block_height
        elif row == 1:
            y = (height - block_height) / 2.0
        else:
            y = margin_v
        x = max(self.px(4), min(x, max(self.px(4), width - block_width - self.px(4))))
        y = max(self.px(4), min(y, max(self.px(4), height - block_height - self.px(4))))
        if block.get("background", True) and block_width > 0:
            pad_x, pad_y = self.px(8), self.px(5)
            draw.rounded_rectangle(
                (x - pad_x, y - pad_y, x + block_width + pad_x, y + block_height + pad_y),
                radius=self.px(5), fill=(0, 0, 0, 128))
        line_y = y
        affine = getattr(pil_image, "AFFINE", 0)
        for item in prepared:
            if item is None:
                line_y += spacing
                continue
            runs, line_width, line_height = item
            run_x = x + (block_width - line_width) / 2.0
            for run, font, run_width in runs:
                fill = tuple(run.get("colour") or primary) + (255,)
                if run.get("italic"):
                    pad = self.px(8)
                    layer = pil_image.new("RGBA",
                                          (int(run_width) + pad * 2,
                                           int(line_height) + pad * 2), (0, 0, 0, 0))
                    pil_draw.Draw(layer).text((pad, pad), run["text"], font=font,
                                              fill=fill, stroke_width=stroke,
                                              stroke_fill=outline + (255,))
                    shear = 0.22
                    shifted = int(layer.height * shear)
                    layer = layer.transform((layer.width + shifted, layer.height),
                                            affine, (1, shear, -shifted, 0, 1, 0),
                                            resample=pil_image.BILINEAR)
                    image.alpha_composite(layer, (int(run_x) - pad, int(line_y) - pad))
                else:
                    draw.text((run_x, line_y), run["text"], font=font, fill=fill,
                              stroke_width=stroke, stroke_fill=outline + (255,))
                if run.get("underline"):
                    underline_y = line_y + line_height
                    draw.line((run_x, underline_y, run_x + run_width, underline_y),
                              fill=fill, width=max(1, int(font_px * 0.06)))
                run_x += run_width
            line_y += line_height + spacing
        return y - spacing

    def _render_video_frame(self):
        if self.current_frame is None or cv2 is None:
            return
        if Image is None or ImageTk is None or ImageDraw is None:
            return
        canvas_width = max(2, self.preview_canvas.winfo_width())
        canvas_height = max(2, self.preview_canvas.winfo_height())
        frame_height, frame_width = self.current_frame.shape[:2]
        ratio = min(canvas_width / frame_width, canvas_height / frame_height)
        width = max(1, round(frame_width * ratio))
        height = max(1, round(frame_height * ratio))
        interpolation = cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR
        frame = cv2.resize(self.current_frame, (width, height), interpolation=interpolation)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        blocks = self._caption_blocks_for(self.position_var.get())
        if blocks:
            signature = (width, height, self.subtitle_language_var.get(),
                         tuple(run["text"] for block in blocks
                               for line in block["lines"] for run in line))
            cache = self._caption_cache
            if cache.get("key") != signature:
                overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                self._draw_caption_blocks(overlay, ImageDraw.Draw(overlay, "RGBA"),
                                          width, height, blocks)
                cache = self._caption_cache = {"key": signature, "image": overlay}
            raster = Image.fromarray(frame_rgb).convert("RGBA")
            raster.alpha_composite(cache["image"])
            raster = raster.convert("RGB")
        else:
            raster = Image.fromarray(frame_rgb)
        if self._photo_image is None or self._photo_size != (width, height):
            self._photo_image = ImageTk.PhotoImage(raster)
            self._photo_size = (width, height)
        else:
            self._photo_image.paste(raster)
        self.preview_photo = self._photo_image
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_width // 2, canvas_height // 2,
                                         image=self._photo_image, anchor="center")

    def _stop_rendered_audio_preview(self):
        process = self.preview_audio_process
        if process is None:
            return
        self.preview_audio_process = None
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _start_audio(self, seconds: float):
        """启动音频：优先可查询的音频主时钟（mpv → waveOut），否则退回 ffplay + 墙钟。"""
        self._stop_audio()
        position = max(0.0, float(seconds or 0.0))
        if not self.audio_tracks:
            self._audio_clock_kind = ""
            return
        ordinal = self._selected_audio_ordinal()
        clock = create_audio_clock(self.media_path, find_binary("ffmpeg"), ordinal)
        if clock is not None and clock.start(position):
            self.audio_clock = clock
            self._audio_clock_kind = clock.name
            self._append_log(f"播放时钟：{clock.name}（音频主时钟，音轨 "
                             f"{ordinal + 1}，画面跟随音频）")
            return
        self.audio_clock = None
        self._audio_clock_kind = "ffplay"
        self._start_rendered_audio_preview()
        detail = getattr(clock, "error", "") if clock is not None else ""
        self._append_log("播放时钟：ffplay + 墙钟（未找到可查询的音频时钟"
                         + (f"：{detail}" if detail else "") + "）"
                         + "；音画不同步时请用「同步」微调")

    def _stop_audio(self):
        clock, self.audio_clock = self.audio_clock, None
        self._audio_clock_kind = ""
        if clock is not None:
            try:
                clock.stop()
            except Exception:
                pass
        self._stop_rendered_audio_preview()

    def _start_rendered_audio_preview(self):
        """用 ffplay 只播放音频（-vn 不解码视频），画面由画布按墙钟驱动。"""
        self._stop_rendered_audio_preview()
        ffplay = find_binary("ffplay")
        if not ffplay or self.media_path is None:
            return
        position = max(0.0, self.position_var.get())
        command = [ffplay, "-hide_banner", "-loglevel", "error", "-nostats",
                   "-autoexit", "-nodisp", "-vn",
                   "-ast", f"a:{self._selected_audio_ordinal()}",
                   "-ss", f"{position:.3f}", "-i", str(self.media_path)]
        try:
            self.preview_audio_process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            self.preview_audio_process = None

    def _resize_video_canvas(self, _event=None):
        if self.current_frame is not None:
            self._render_video_frame()
        elif self._preview_message:
            self._draw_preview_placeholder(self._preview_message)

    def _close_video(self):
        self.video_playing = False
        set_precise_timers(False)
        self._stop_audio()
        if self.video_after is not None:
            try:
                self.root.after_cancel(self.video_after)
            except tk.TclError:
                pass
            self.video_after = None
        if self.video_capture is not None:
            self.video_capture.release()
            self.video_capture = None
        self.current_frame = None
        self._caption_cache = {}
        self._photo_image = None
        self._photo_size = None
        if hasattr(self, "play_button"):
            self.play_button.configure(text="▶ 播放")

    def _close_window(self):
        self._closing = True
        if self._plan_cancel is not None:
            self._plan_cancel.set()
        for handle in (getattr(self, "_poll_after", None), getattr(self, "_dpi_after", None)):
            if handle is not None:
                try:
                    self.root.after_cancel(handle)
                except tk.TclError:
                    pass
        self._close_video()
        self.root.destroy()

    def _start_transcription(self):
        if self.busy:
            return
        if self.media_path is None or not self.audio_tracks:
            messagebox.showinfo("需要媒体", "请先载入包含音轨的媒体文件。")
            return
        ordinal = self._selected_audio_ordinal()
        model = self.whisper_model_var.get()
        choice = self.asr_language_var.get()
        whisper_lang = "" if choice == "自动检测" else WHISPER_LANGUAGE_CODES.get(choice, "")
        self.asr_status_var.set("正在准备识别…")
        self._append_log(f"开始识别：Whisper {model} · 音轨 {ordinal + 1} · 语言 {choice}")
        self._run_worker("准备本地 Whisper…", self._transcribe_worker,
                         ordinal, model, whisper_lang)

    def _transcribe_worker(self, ordinal: int, model: str, language: str):
        media_path = self.media_path
        if media_path is None:
            raise StudioError("请先载入媒体文件。")
        with tempfile.TemporaryDirectory(prefix="media_asr_") as temp_dir:
            audio = Path(temp_dir) / "audio.wav"
            self.events.put(("status", "正在抽取所选音轨为 16 kHz 单声道…"))
            audio_to_wav(media_path, ordinal, audio)
            entries = transcribe_audio(audio, model, language,
                                       progress=lambda text: self.events.put(("status", text)),
                                       label="识别")
        return {"entries": entries, "model": model, "ordinal": ordinal}

    def _context_line_count(self, report: bool = False) -> int | None:
        """读取「上下文句数」；非法时返回 None（report=True 时弹提示）。"""
        try:
            value = int(float(self.context_lines_var.get()))
        except (TypeError, ValueError):
            if report:
                messagebox.showerror("参数无效", "上下文句数必须是整数。")
            return None
        if not 0 <= value <= CONTEXT_LINES_MAX:
            if report:
                messagebox.showerror(
                    "参数无效",
                    f"上下文句数必须在 0~{CONTEXT_LINES_MAX} 之间（0 = 关闭）。")
            return None
        return value

    def _start_translation(self):
        if self.busy:
            return
        if not self.entries:
            messagebox.showinfo("没有字幕", "请先载入字幕，或先识别一个音轨。")
            return
        if not translation_models():
            messagebox.showerror("缺少配置",
                                 f"未找到可用的 AI 模型配置：{subtitles.get_config_path()}")
            return
        try:
            max_concurrent = int(float(self.translation_concurrency_var.get()))
            batch_size = (int(float(self.batch_size_var.get()))
                          if self.group_translation_var.get() else 0)
        except (TypeError, ValueError):
            messagebox.showerror("参数无效", "并发数和每组行数必须是整数。")
            return
        if not 1 <= max_concurrent <= self.MAX_CONCURRENT:
            messagebox.showerror("参数无效",
                                 f"并发数必须在 1~{self.MAX_CONCURRENT} 之间。")
            return
        if self.group_translation_var.get() and not (
                subtitles.BATCH_SIZE_MIN <= batch_size <= subtitles.BATCH_SIZE_MAX):
            messagebox.showerror(
                "参数无效",
                f"每组行数必须在 {subtitles.BATCH_SIZE_MIN}~{subtitles.BATCH_SIZE_MAX} 之间。",
            )
            return
        context_lines = self._context_line_count(report=True)
        if context_lines is None:
            return
        model_name = self.translation_model_var.get()
        source, target = self.source_var.get(), self.target_var.get()
        mode_text = f"分组 {batch_size} 行/批" if batch_size else "逐条"
        self.translate_cancel_event = threading.Event()
        self._set_translate_running(True)
        self._append_log(
            f"开始翻译：{model_name} · 并发 {max_concurrent} · {mode_text} · "
            f"上下文 ±{context_lines} 条 · {source} → {target}")
        self._run_worker("正在调用 AI 翻译…", self._translate_worker,
                         model_name, source, target, max_concurrent, batch_size,
                         context_lines)

    def _cancel_translation(self):
        if self.translate_cancel_event is not None:
            self.translate_cancel_event.set()
        self.cancel_translate_button.configure(state="disabled")
        self.status_var.set("正在取消翻译：等待在途请求返回…")
        self._append_log("已请求取消；等待在途请求结束后停止（完成的部分不会写入字幕）。")

    def _translate_worker(self, model_name: str, source: str, target: str,
                          max_concurrent: int, batch_size: int, context_lines: int):
        entries = copy.deepcopy(self.original_entries or self.entries)
        translated, cancelled = translated_entries(
            entries, source, target, model_name,
            progress=lambda done, total: self.events.put(("progress", done, total)),
            log=lambda text: self.events.put(("log", text)),
            max_concurrent=max_concurrent, batch_size=batch_size,
            context_lines=context_lines,
            cancel_event=self.translate_cancel_event,
        )
        try:
            tokens = subtitles.get_token_stats()[2]
        except Exception:
            tokens = 0
        return {"translated": translated, "cancelled": cancelled,
                "tokens": tokens, "total": len(translated)}

    def _set_translate_running(self, running: bool):
        self.translate_running = running
        if running:
            self.translate_progress.configure(maximum=1, value=0)
            self.cancel_translate_button.configure(state="normal")
            self.translate_progress_var.set("正在准备翻译任务…")
        else:
            self.cancel_translate_button.configure(state="disabled")

    def _on_translate_progress(self, done: int, total: int):
        total = max(1, int(total))
        done = max(0, min(int(done), total))
        self.translate_progress.configure(maximum=total, value=done)
        self.translate_progress_var.set(f"已翻译 {done}/{total} 条（{done * 100 // total}%）")

    def _toggle_group_translation(self):
        state = "normal" if self.group_translation_var.get() else "disabled"
        self.batch_size_spinbox.configure(state=state)
        self._update_translate_hint()

    def _refresh_translation_models(self):
        if getattr(self, "translation_model_box", None) is None:
            return
        models = translation_models()
        names = [item["name"] for item in models]
        self.translation_model_box["values"] = names
        current = self.translation_model_var.get()
        if current not in names:
            current = default_translation_model()
            self.translation_model_var.set(current)
        detail = translation_model_by_name(current)
        changed = current != self._last_translation_model
        self._last_translation_model = current
        if detail:
            per_model = model_concurrency(detail)
            self.model_detail_var.set(
                f"{detail.get('model', '未知模型')} · 模型配置默认并发 {per_model}")
            if changed:
                self.translation_concurrency_var.set(str(per_model))
        else:
            self.model_detail_var.set("未找到 api_settings.json 中的模型配置。")
        self._update_translate_hint()

    def _on_translation_model_change(self, _event=None):
        self._refresh_translation_models()
        self._append_log(f"翻译模型已切换为：{self.translation_model_var.get()}")

    def _start_export(self):
        """① 只导出单个字幕文件（外挂），与压制设置完全无关。"""
        if self.busy:
            return
        media_path = self.media_path
        if media_path is None:
            messagebox.showinfo("需要媒体", "请先载入媒体文件。")
            return
        language_mode = self.subtitle_language_var.get()
        original = copy.deepcopy(self.original_entries or self.entries)
        translated = copy.deepcopy(self.translated)
        if not original:
            messagebox.showinfo("没有字幕", "请先载入或识别字幕。")
            return
        if language_mode in {"译文", "双语"} and not translated:
            messagebox.showinfo("没有译文", "请先翻译字幕，或选择原文输出。")
            return
        self._append_log(f"导出字幕文件：{self.subtitle_format_var.get()} · {language_mode}")
        self._run_worker(
            "正在导出字幕文件…", self._export_worker, str(media_path),
            self.subtitle_format_var.get().lower(), language_mode, original, translated)

    def _mux_options(self) -> dict:
        """压制时的重复检查设置（快照，后台线程用）。"""
        return {"check_duplicates": bool(self.mux_check_var.get()),
                "duplicate_threshold": self._mux_threshold(),
                "check_ai": True,
                "ai_model": self.translation_model_var.get()}

    def _start_mux(self):
        """② 压制字幕（只处理压制，与单文件导出互不影响）。"""
        if self.busy:
            return
        media_path = self.media_path
        if media_path is None:
            messagebox.showinfo("需要媒体", "请先载入媒体文件。")
            return
        original = copy.deepcopy(self.original_entries or self.entries)
        translated = copy.deepcopy(self.translated)
        mux_tracks = self._mux_track_specs()
        try:
            normalize_export_tracks(mux_tracks)
        except StudioError as exc:
            messagebox.showerror("字幕轨无效", str(exc))
            return
        if mux_tracks:
            needs_original = any(item["kind"] == "generated" for item in mux_tracks)
            needs_translated = any(item["kind"] == "generated" and item["mode"] != "原文"
                                   for item in mux_tracks)
        else:
            mode = self.subtitle_language_var.get()
            needs_original, needs_translated = True, mode in {"译文", "双语"}
        if needs_original and not original:
            messagebox.showinfo("没有字幕", "请先载入或识别字幕。")
            return
        if needs_translated and not translated:
            messagebox.showinfo("没有译文", "请先翻译字幕，或改为压制原文。")
            return
        drop_subtitles = self._selected_drop_subtitles()
        threshold = self._mux_threshold()
        self._append_log(
            f"开始压制：{len(mux_tracks) if mux_tracks else 1} 条字幕轨"
            + (f" · 删除 {len(drop_subtitles)} 条内嵌字幕" if drop_subtitles else "")
            + (f" · 重复检查开（≥{threshold}%）" if self.mux_check_var.get()
               else " · 重复检查关"))
        self._run_worker(
            "正在压制字幕…", self._mux_worker, str(media_path),
            self.subtitle_format_var.get().lower(),
            self.subtitle_language_var.get(), original, translated,
            drop_subtitles, mux_tracks, self._mux_options())

    def _export_worker(self, media_path: str, format_name: str,
                       language_mode: str, original: list[dict],
                       translated: list[dict]) -> list[Path]:
        return export_subtitles(media_path, format_name, "外挂字幕", language_mode,
                                original, translated)

    def _mux_worker(self, media_path: str, format_name: str, language_mode: str,
                    original: list[dict], translated: list[dict],
                    drop_subtitles=None, mux_tracks=None, options=None) -> dict:
        """压制（带重复检查）：返回 {"outputs": [...], "dropped": [...], "tokens": int}。"""
        options = dict(options or {})
        token_before = int(subtitles.get_token_stats()[2])
        candidates: list[dict] = []
        tracks = mux_tracks or [{"kind": "generated", "mode": language_mode,
                                 "language": None, "title": language_mode}]
        tracks, missing_tracks = resolve_export_tracks(
            media_path, tracks, log=lambda text: self.events.put(("log", text)))
        if not tracks:
            raise StudioError(
                "没有可压制的字幕轨：\n"
                + "\n".join(f"· {item['label']}：{item['reason']}" for item in missing_tracks))
        for position, track in enumerate(tracks, 1):
            if str(track.get("kind") or "") == "external":
                item_label = f"外部字幕 {Path(str(track.get('path'))).name}"
            else:
                item_label = f"生成的字幕·{track.get('mode') or '原文'}"
            candidates.append({"key": position, "label": item_label, "spec": track,
                               "entries": _plan_track_contents(track, original, translated)})
        dropped: list[dict] = []
        if candidates and options.get("check_duplicates", True):
            outcome = check_mux_tracks(
                Path(media_path), candidates,
                threshold=options.get("duplicate_threshold", DUPLICATE_THRESHOLD_DEFAULT),
                use_ai=bool(options.get("check_ai", True)),
                model_name=options.get("ai_model"),
                log=lambda text: self.events.put(("log", text)))
            candidates, dropped = outcome["keep"], outcome["dropped"]
            if not candidates:
                raise StudioError(
                    "待压字幕与视频里已有字幕同语言且内容雷同，已全部去掉：\n"
                    + "\n".join(f"· {item['label']} ≈ {item['target']}"
                                f"（{item['ratio']:.0%}）" for item in dropped))
        outputs = export_subtitles(
            media_path, format_name, "内嵌字幕", language_mode, original, translated,
            drop_subtitles=drop_subtitles,
            mux_tracks=[item["spec"] for item in candidates] or None)
        tokens = int(subtitles.get_token_stats()[2]) - token_before
        return {"outputs": outputs, "dropped": dropped, "tokens": max(0, tokens)}

    # ------------------------------------------------------------- 计划任务
    def _plan_add_step(self, kind: str, page: str, detail: str, settings: dict):
        """把当前页面的设置记为一个计划步骤（按加入顺序依次执行）。"""
        if self.plan_running:
            self.status_var.set("计划正在执行，暂时不能修改计划。")
            return
        step = {"kind": kind, "page": page, "detail": detail,
                "label": f"{page} · {detail}", "settings": settings}
        self._plan_steps.append(step)
        self._refresh_plan_tree(select=len(self._plan_steps) - 1)
        self._append_log(f"已加入计划：{step['label']}")
        self.status_var.set(f"已加入计划（共 {len(self._plan_steps)} 步）：{detail}")

    def _plan_add_asr(self):
        model = self.whisper_model_var.get()
        choice = self.asr_language_var.get()
        ordinal = self._selected_audio_ordinal()
        settings = {
            "model": model,
            "language": choice,
            "whisper_language": ("" if choice == "自动检测"
                                 else WHISPER_LANGUAGE_CODES.get(choice, "")),
            "audio_ordinal": ordinal,
        }
        detail = f"Whisper {model} · 音轨 {ordinal + 1} · 语言 {choice}"
        self._plan_add_step("asr", "识别", detail, settings)

    def _plan_add_translate(self):
        if not translation_models():
            messagebox.showerror("缺少配置",
                                 f"未找到可用的 AI 模型配置：{subtitles.get_config_path()}")
            return
        try:
            max_concurrent = int(float(self.translation_concurrency_var.get()))
            batch_size = (int(float(self.batch_size_var.get()))
                          if self.group_translation_var.get() else 0)
        except (TypeError, ValueError):
            messagebox.showerror("参数无效", "并发数和每组行数必须是整数。")
            return
        if not 1 <= max_concurrent <= self.MAX_CONCURRENT:
            messagebox.showerror("参数无效",
                                 f"并发数必须在 1~{self.MAX_CONCURRENT} 之间。")
            return
        if self.group_translation_var.get() and not (
                subtitles.BATCH_SIZE_MIN <= batch_size <= subtitles.BATCH_SIZE_MAX):
            messagebox.showerror(
                "参数无效",
                f"每组行数必须在 {subtitles.BATCH_SIZE_MIN}~"
                f"{subtitles.BATCH_SIZE_MAX} 之间。")
            return
        context_lines = self._context_line_count(report=True)
        if context_lines is None:
            return
        settings = {
            "model_name": self.translation_model_var.get(),
            "source": self.source_var.get(),
            "target": self.target_var.get(),
            "concurrency": max_concurrent,
            "batch_size": batch_size,
            "context_lines": context_lines,
        }
        mode = f"分组 {batch_size} 行/批" if batch_size else "逐条"
        detail = (f"{settings['model_name']} · 并发 {max_concurrent} · {mode} · "
                  f"上下文 ±{context_lines} · "
                  f"{settings['source']} → {settings['target']}")
        self._plan_add_step("translate", "翻译", detail, settings)

    def _plan_add_export(self):
        """加入计划：只导出单个字幕文件。"""
        settings = {
            "format": self.subtitle_format_var.get().lower(),
            "language": self.subtitle_language_var.get(),
            "mode": "file",
        }
        detail = f"{settings['format'].upper()} · 字幕文件 · {settings['language']}"
        self._plan_add_step("export", "导出", detail, settings)

    def _plan_add_mux(self):
        """加入计划：压制字幕轨（含重复检查设置）。"""
        mux_tracks = self._mux_track_specs()
        try:
            normalize_export_tracks(mux_tracks)
        except StudioError as exc:
            messagebox.showerror("字幕轨无效", str(exc))
            return
        drop_subtitles = self._selected_drop_subtitles()
        threshold = self._mux_threshold()
        check_on = bool(self.mux_check_var.get())
        settings = {
            "format": self.subtitle_format_var.get().lower(),
            "drop_subtitles": drop_subtitles,
            "mux_tracks": mux_tracks,
            "check_duplicates": check_on,
            "duplicate_threshold": threshold,
        }
        detail = f"{settings['format'].upper()} · 压制"
        if mux_tracks:
            labels = [self._mux_track_label(track) for track in self._mux_tracks]
            shown = "、".join(labels[:2]) + ("…" if len(labels) > 2 else "")
            detail += f" · {len(labels)} 条字幕轨（{shown}）"
            bound = sum(1 for item in mux_tracks if item.get("bind"))
            if bound:
                detail += f" · {bound} 条按文件名关系自动匹配"
        if drop_subtitles:
            detail += f" · 删除 {len(drop_subtitles)} 条内嵌字幕"
        detail += f" · 重复检查{'开 ≥' + str(threshold) + '%' if check_on else '关'}"
        self._plan_add_step("mux", "压制", detail, settings)

    def _refresh_plan_tree(self, select: int | None = None):
        tree = getattr(self, "plan_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for index, step in enumerate(self._plan_steps):
            tree.insert("", "end", iid=str(index),
                        values=(index + 1, step.get("page"), step.get("detail")),
                        tags=("odd" if index % 2 else "even",))
        if select is not None and 0 <= select < len(self._plan_steps):
            tree.selection_set(str(select))
            tree.see(str(select))

    def _refresh_plan_files_tree(self, select: int | None = None):
        """重建文件列表：每个文件下面挂本次执行中它的各步骤（状态 + token）。"""
        tree = getattr(self, "plan_files_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        for index, path in enumerate(self._plan_files):
            status = self._plan_status.get(str(path), "待处理")
            if status.startswith("处理中"):
                tag = "running"
            elif status.startswith("完成"):
                tag = "done"
            elif status.startswith("失败"):
                tag = "failed"
            elif status.startswith("跳过"):
                tag = "skipped"
            else:
                tag = "odd" if index % 2 else "even"
            steps = self._plan_file_steps.get(str(path)) or []
            total = sum(int(item.get("tokens") or 0) for item in steps)
            tree.insert("", "end", iid=str(index), open=bool(steps),
                        values=(index + 1, path.name, status,
                                f"{total:,}" if total else "—"), tags=(tag,))
            for item in steps:
                tokens = int(item.get("tokens") or 0)
                tree.insert(str(index), "end", iid=f"{index}.{item['order']}",
                            values=(f"{index + 1}.{item['order']}",
                                    f"　{item.get('label') or ''}",
                                    item.get("status") or "",
                                    f"{tokens:,}" if tokens else "—"),
                            tags=("step",))
        if select is not None and 0 <= select < len(self._plan_files):
            tree.selection_set(str(select))
            tree.see(str(select))

    def _plan_selection(self, tree_name: str) -> int | None:
        tree = getattr(self, tree_name, None)
        if tree is None:
            return None
        try:
            return int(tree.selection()[0])
        except (IndexError, ValueError):
            return None

    def _plan_set_status(self, path: Path, status: str):
        self._plan_status[str(path)] = status
        self._refresh_plan_files_tree()

    def _plan_move_step(self, delta: int):
        if self.plan_running:
            return
        index = self._plan_selection("plan_tree")
        if index is None:
            self.status_var.set("请先在计划列表里选择一个步骤。")
            return
        target = index + delta
        if not 0 <= target < len(self._plan_steps):
            return
        steps = self._plan_steps
        steps[index], steps[target] = steps[target], steps[index]
        self._refresh_plan_tree(select=target)

    def _plan_remove_step(self):
        if self.plan_running:
            return
        index = self._plan_selection("plan_tree")
        if index is None:
            self.status_var.set("请先在计划列表里选择一个步骤。")
            return
        removed = self._plan_steps.pop(index)
        self._refresh_plan_tree(select=min(index, len(self._plan_steps) - 1))
        self._append_log(f"已从计划移除：{removed.get('label')}")

    def _plan_clear_steps(self):
        if self.plan_running or not self._plan_steps:
            return
        self._plan_steps = []
        self._refresh_plan_tree()
        self._append_log("计划步骤已清空。")

    def _plan_add_files(self, paths) -> int:
        added = 0
        if self.plan_running:
            return 0
        for item in paths:
            path = Path(item)
            try:
                if path.suffix.lower() not in MEDIA_EXTENSIONS or not path.is_file():
                    continue
            except OSError:
                continue
            if path in self._plan_files:
                continue
            self._plan_files.append(path)
            added += 1
        if added:
            self._refresh_plan_files_tree()
            self.status_var.set(f"已加入 {added} 个文件（共 {len(self._plan_files)} 个）")
        return added

    def _plan_choose_files(self):
        paths = filedialog.askopenfilenames(
            title="选择要处理的媒体文件（可多选）",
            filetypes=[("媒体文件",
                        "*." + " *.".join(sorted(ext[1:] for ext in MEDIA_EXTENSIONS))),
                       ("所有文件", "*.*")],
        )
        if not paths:
            return
        if not self._plan_add_files(paths):
            self.status_var.set("没有加入新文件（已存在或不是媒体文件）")

    def _plan_add_current(self):
        if self.media_path is None:
            self.status_var.set("还没有载入媒体文件。")
            return
        if not self._plan_add_files([self.media_path]):
            self.status_var.set(f"{self.media_path.name} 已在计划文件列表中。")

    def _plan_remove_file(self):
        if self.plan_running:
            return
        index = self._plan_selection("plan_files_tree")
        if index is None:
            self.status_var.set("请先在文件列表里选择一个文件。")
            return
        removed = self._plan_files.pop(index)
        self._plan_status.pop(str(removed), None)
        self._refresh_plan_files_tree(select=min(index, len(self._plan_files) - 1))
        self.status_var.set(f"已从计划移除文件：{removed.name}")

    def _plan_clear_files(self):
        if self.plan_running or not self._plan_files:
            return
        self._plan_files = []
        self._plan_status = {}
        self._refresh_plan_files_tree()
        self.status_var.set("计划文件列表已清空。")

    def _start_plan(self):
        if self.busy or self.plan_running:
            return
        if not self._plan_steps:
            messagebox.showerror("计划为空",
                                 "请先在「识别 / 翻译 / 导出与封装」页面把设置加入计划。")
            return
        if not self._plan_files:
            messagebox.showerror("没有文件", "请先添加要处理的媒体文件，可一次选择多个。")
            return
        missing = [path for path in self._plan_files if not path.is_file()]
        if missing:
            messagebox.showerror("文件不存在",
                                 "\n".join(str(path) for path in missing[:5]))
            return
        if not any(step.get("kind") in ("export", "mux") for step in self._plan_steps):
            self._append_log("提示：计划里没有导出 / 压制步骤，执行完不会生成字幕文件。")
        self._plan_cancel = threading.Event()
        self._plan_ok = self._plan_failed = 0
        self._plan_skipped = 0
        self._skipped_notes = []
        self._pending_mux = []
        self._plan_status = {}
        self._plan_file_steps = {}
        self._plan_steps_done = 0
        self._plan_tokens_total = 0
        self._plan_current_step_text = ""
        steps = copy.deepcopy(self._plan_steps)
        files = list(self._plan_files)
        # ⚠️ Tk 变量只能在主线程读取：先取成普通值再交给后台线程
        continue_on_error = bool(self.plan_continue_var.get())
        asr_language = self.asr_language_var.get()
        options = {
            "translate_source": self.translate_source_var.get(),
            "audio_ordinal": self._selected_audio_ordinal(),
            "asr_model": self.whisper_model_var.get(),
            "asr_language": ("" if asr_language == "自动检测"
                             else WHISPER_LANGUAGE_CODES.get(asr_language, "")),
            "target": self.target_var.get(),
            "check_duplicates": bool(self.mux_check_var.get()),
            "duplicate_threshold": self._mux_threshold(),
            "check_ai": True,
            "ai_model": self.translation_model_var.get(),
            "probe_model": PROBE_WHISPER_MODEL,
            "probe_seconds": PROBE_SAMPLE_SECONDS,
        }
        self._plan_total_steps = max(1, len(files) * len(steps))
        self._refresh_plan_files_tree()
        self._set_plan_running(True)
        self.plan_progress.configure(maximum=self._plan_total_steps, value=0)
        self.plan_step_progress.configure(maximum=1, value=0)
        self.plan_progress_var.set(
            f"总进度 0/{self._plan_total_steps} 步（0/{len(files)} 个文件）")
        self.plan_token_var.set("Token：本文件 — · 总计 —")
        self.plan_status_var.set(f"准备处理 {len(files)} 个文件…")
        self._append_log(f"开始执行计划：{len(files)} 个文件 × {len(steps)} 个步骤")
        threading.Thread(target=self._plan_worker,
                         args=(steps, files, continue_on_error, options),
                         daemon=True).start()

    def _stop_plan(self):
        if not self.plan_running:
            return
        if self._plan_cancel is not None:
            self._plan_cancel.set()
        self.plan_stop_button.configure(state="disabled")
        self.plan_status_var.set("正在停止：当前步骤结束后停止（识别推理无法立即中断）")
        self._append_log("已请求停止计划。")

    def _set_plan_running(self, running: bool):
        self.plan_running = running
        if getattr(self, "plan_button", None) is not None:
            self.plan_button.configure(state="disabled" if running else "normal")
        if getattr(self, "plan_stop_button", None) is not None:
            self.plan_stop_button.configure(state="normal" if running else "disabled")
        for button in (list(getattr(self, "plan_step_buttons", []))
                       + list(getattr(self, "plan_file_buttons", []))):
            button.configure(state="disabled" if running else "normal")
        self._set_busy(running)

    def _plan_worker(self, steps: list[dict], files: list[Path],
                     continue_on_error: bool, options: dict):
        """后台线程：识别线程连续刷文件，主线程拿到结果就翻译 / 压制（流水线）。

        不在这里碰任何 Tk 控件 / 变量：options 是主线程取好的快照。
        """
        cancel = self._plan_cancel

        def log(text, name=None):
            self.events.put(("log", f"[{name}] {text}" if name else str(text)))

        def progress(done, total):
            self.events.put(("plan_progress", done, total))

        def file_callback(index, total, path_text):
            self.events.put(("plan_file", index, total, path_text))

        def step_callback(event, index, path):
            self.events.put(("plan_step", index, str(path), event))

        try:
            summary = run_plan_for_files(
                files, steps, log=log, progress=progress, cancel_event=cancel,
                step_callback=step_callback, file_callback=file_callback,
                options=options, continue_on_error=continue_on_error,
                pending_mux=self._pending_mux)
        except Exception as exc:
            self.events.put(("log", f"计划异常终止：{exc}"))
            self.events.put(("plan_done", bool(cancel is not None and cancel.is_set())))
            return
        for item in summary.get("skipped") or []:
            self.events.put(("plan_skip", item["path"], item["reason"], item.get("detail", "")))
        for item in summary.get("errors") or []:
            self.events.put(("plan_error", 0, item["path"], item["message"]))
        for result in summary.get("results") or []:
            index = next((position for position, path in enumerate(files, 1)
                          if str(path) == result.get("media")), 0)
            self.events.put(("plan_result", index, result))
        self.events.put(("plan_summary", summary))
        self.events.put(("plan_done", bool(cancel is not None and cancel.is_set())))

    def _on_plan_file(self, index: int, total: int, path_text: str):
        path = Path(path_text)
        self._plan_file_steps.setdefault(str(path), [])   # 识别线程可能已经写过明细
        self._plan_current_step_text = path.name
        self._plan_set_status(path, "处理中…")
        self.plan_step_progress.configure(maximum=1, value=0)
        self.plan_progress_var.set(
            f"总进度 {self._plan_steps_done}/{self._plan_total_steps} 步"
            f"（{index - 1}/{total} 个文件）")
        self.plan_status_var.set(f"正在处理 {index}/{total}：{path.name}")
        self.status_var.set(f"计划执行中 {index}/{total}：{path.name}")
        self._update_plan_token_var(path)

    def _on_plan_step(self, index: int, path_text: str, event: dict):
        """单个步骤开始 / 结束：更新当前步骤进度条、总进度条与文件树里的明细行。"""
        path = Path(path_text)
        steps = self._plan_file_steps.setdefault(str(path), [])
        order = int(event.get("order") or 0)
        entry = next((item for item in steps if item["order"] == order), None)
        if entry is None:
            entry = {"order": order, "label": str(event.get("label") or ""),
                     "status": "", "tokens": 0}
            steps.append(entry)
        label = entry["label"] or str(event.get("kind") or f"步骤 {order}")
        if event.get("phase") == "begin":
            entry["status"] = "进行中…"
            self._plan_current_step_text = (f"{path.name} · 步骤 {order}/"
                                            f"{event.get('total')}：{label}")
            self.plan_step_progress.configure(maximum=1, value=0)
            self.plan_status_var.set(self._plan_current_step_text)
        else:
            entry["status"] = "完成"
            entry["tokens"] = int(event.get("tokens") or 0)
            self._plan_steps_done += 1
            self._plan_tokens_total += entry["tokens"]
            self.plan_progress.configure(
                value=min(self._plan_steps_done, self._plan_total_steps))
            self.plan_progress_var.set(
                f"总进度 {self._plan_steps_done}/{self._plan_total_steps} 步"
                f"（{self._plan_ok + self._plan_failed}/{len(self._plan_files)} 个文件）")
            self.plan_step_progress.configure(maximum=1, value=1)
            self.plan_status_var.set(
                f"{self._plan_current_step_text}　已完成"
                + (f" · 本步 token {entry['tokens']:,}" if entry["tokens"] else ""))
            self._update_plan_token_var(path)
        self._refresh_plan_files_tree()

    def _on_plan_progress(self, done: int, total: int):
        total = max(1, int(total))
        done = max(0, min(int(done), total))
        self.plan_step_progress.configure(maximum=total, value=done)
        self.plan_status_var.set(
            f"{self._plan_current_step_text}　{done}/{total} 条"
            f"（{done * 100 // total}%）")

    def _update_plan_token_var(self, path: Path | None = None):
        file_tokens = sum(int(item.get("tokens") or 0)
                          for item in self._plan_file_steps.get(str(path), []))
        self.plan_token_var.set(f"Token：本文件 {file_tokens:,} · "
                                f"总计 {self._plan_tokens_total:,}")

    def _on_plan_result(self, index: int, result: dict):
        path = Path(result.get("media") or "")
        outputs = result.get("outputs") or []
        tokens = int(result.get("tokens") or 0)
        self._plan_ok += 1
        self._plan_set_status(path, f"完成（{len(outputs)} 个输出）")
        for output in outputs:
            self._append_log(f"已输出：{output}")
        if tokens:
            self._append_log(f"[{path.name}] 本文件 token：{tokens:,}")
        self._update_plan_token_var(path)

    def _on_plan_error(self, index: int, path_text: str, message: str):
        path = Path(path_text)
        for item in self._plan_file_steps.get(str(path), []):
            if item.get("status") == "进行中…":
                item["status"] = "失败"
        self._plan_failed += 1
        self._plan_set_status(path, f"失败：{str(message)[:36]}")
        self._append_log(f"[{path.name}] 失败：{message}")
        self._update_plan_token_var(path)

    def _on_plan_skip(self, path_text: str, reason: str, detail: str = ""):
        """该文件被自动跳过（重复字幕 / 语言判定 / 没有可用来源）。"""
        path = Path(path_text)
        for item in self._plan_file_steps.get(str(path), []):
            if item.get("status") == "进行中…":
                item["status"] = "已跳过"
        self._plan_skipped += 1
        self._plan_set_status(path, f"跳过 · {reason[:26]}")
        self._skipped_notes.append(f"{path.name}：{reason}"
                                   + (f"（{detail}）" if detail else ""))
        self._update_plan_token_var(path)

    def _on_plan_summary(self, summary: dict):
        """任务列表跑完后，把跳过 / 跳轨的原因统一写进运行日志。"""
        notes = self._skipped_notes
        if notes:
            self._append_log(f"—— 本次有 {len(notes)} 个文件被自动跳过 ——")
            for line in notes:
                self._append_log(f"  跳过：{line}")
            self._append_log("跳过的原因多为字幕重复 / 已经是目标语言 / 判定失败；"
                             "可关掉「压制前检查重复字幕」或改用「翻译来源」重跑。")
        errors = summary.get("errors") or []
        if errors:
            self._append_log(f"—— {len(errors)} 个文件失败 ——")
            for item in errors:
                self._append_log(f"  {Path(item['path']).name}：{item['message']}")

    def _on_plan_done(self, cancelled: bool):
        self._set_plan_running(False)
        self._plan_cancel = None
        if cancelled:
            for steps in self._plan_file_steps.values():
                for item in steps:
                    if item.get("status") == "进行中…":
                        item["status"] = "已停止"
            self._refresh_plan_files_tree()
        summary = (f"计划结束：成功 {self._plan_ok} · 失败 {self._plan_failed} · "
                   f"跳过 {self._plan_skipped} · "
                   f"共 {len(self._plan_files)} 个文件 · 完成 {self._plan_steps_done}/"
                   f"{self._plan_total_steps} 步 · token {self._plan_tokens_total:,}")
        if cancelled:
            summary += "（已停止）"
        self.plan_status_var.set(summary)
        skipped = max(0, self._plan_total_steps - self._plan_steps_done)
        self.plan_progress_var.set(
            f"总进度 {self._plan_steps_done}/{self._plan_total_steps} 步"
            f"（{self._plan_ok}/{len(self._plan_files)} 个文件成功"
            + (f"，{skipped} 步未执行" if skipped else "") + "）")
        self.status_var.set(summary)
        self._append_log(summary)
        if self._pending_mux:
            missing_count = sum(len(item.get("missing") or [])
                                for item in self._pending_mux)
            self._append_log(f"—— {missing_count} 处外部字幕没找到对应字幕，"
                             "稍后弹出窗口由你决定放弃还是补选 ——")
            self.root.after(150, self._open_pending_mux_dialog)

    # ------------------------------------------------- 缺字幕：结束后补选 / 放弃
    def _open_pending_mux_dialog(self):
        """整批任务结束后：列出「没找到对应字幕」的文件，让用户放弃或补选字幕再压制。"""
        records = [item for item in self._pending_mux if item.get("missing")]
        self._pending_mux = []
        if not records:
            return
        missing_count = sum(len(item["missing"]) for item in records)
        window = tk.Toplevel(self.root)
        window.title("有文件没找到对应的字幕")
        window.configure(background=PALETTE["bg"])
        window.transient(self.root)
        pad = self.px(12)
        ttk.Label(
            window, justify="left", wraplength=self.px(570),
            text=(f"{len(records)} 个文件共有 {missing_count} 处外部字幕没在旁边找到对应字幕。\n"
                  "· 放弃：这些字幕不再压制（其它字幕轨 / 其它文件不受影响）；\n"
                  "· 补选：选中行后指定要压进该文件的字幕，再点「开始压制」重做这些文件"
                  "（识别 / 翻译结果沿用，不会重新识别）。")
        ).pack(anchor="w", padx=pad, pady=(pad, self.px(6)))

        wrap = ttk.Frame(window)
        wrap.pack(fill="both", expand=True, padx=pad)
        tree = ttk.Treeview(wrap, columns=("file", "missing", "state", "chosen"),
                            show="headings", selectmode="extended",
                            height=min(14, max(4, missing_count)))
        for column, title, width in (("file", "文件", 200), ("missing", "没找到的字幕", 250),
                                     ("state", "当前状态", 90), ("chosen", "补选的字幕", 200)):
            tree.heading(column, text=title)
            tree.column(column, width=self.px(width), anchor="w")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        rows: list[dict] = []
        for record in records:
            media_name = Path(str(record.get("media") or "")).name
            state = "未压制" if record.get("skipped") else "已压其余轨"
            for item in record.get("missing") or []:
                position = len(rows)
                rows.append({"record": record, "index": int(item.get("index", -1)),
                             "label": str(item.get("label") or "外部字幕"),
                             "reason": str(item.get("reason") or ""),
                             "chosen": None})
                tree.insert("", "end", iid=str(position),
                            values=(media_name, rows[position]["label"], state, "—"))

        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=pad, pady=(self.px(6), pad))
        ttk.Button(buttons, text="放弃（不压制这些字幕）",
                   command=window.destroy).pack(side="left")
        ttk.Button(buttons, text="开始压制", style="Accent.TButton",
                   command=lambda: self._confirm_pending_mux(rows, window)
                   ).pack(side="right")
        ttk.Button(buttons, text="为选中项选择字幕…",
                   command=lambda: self._choose_pending_subtitle(tree, rows)
                   ).pack(side="right", padx=(0, self.px(6)))
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.grab_set()
        window.focus_set()
        self._append_log(f"已弹出窗口：{missing_count} 处外部字幕可选「放弃」"
                         "或「补选字幕后重新压制」。")

    def _choose_pending_subtitle(self, tree, rows):
        """给选中的行指定要压进对应文件的字幕文件（多选时共用同一个文件）。"""
        selection = sorted(int(item) for item in tree.selection())
        if not selection:
            messagebox.showinfo("请选择", "先在列表里选中要补选字幕的行（可多选）。",
                                parent=tree.winfo_toplevel())
            return
        options = {"title": "选择要压进这些文件的字幕",
                   "parent": tree.winfo_toplevel(),
                   "filetypes": [("字幕文件", "*.srt *.ass *.ssa *.vtt *.sub *.smi *.lrc"),
                                 ("所有文件", "*.*")]}
        folder = Path(str(rows[selection[0]]["record"].get("media") or "")).parent
        if folder.is_dir():
            options["initialdir"] = str(folder)
        chosen = filedialog.askopenfilename(**options)
        if not chosen:
            return
        path = Path(chosen)
        for position in selection:
            rows[position]["chosen"] = path
            tree.set(str(position), "chosen", path.name)
        tree.see(str(selection[-1]))

    def _confirm_pending_mux(self, rows, window):
        """按用户的选择收尾：没选字幕的行 = 放弃。"""
        jobs = [row for row in rows if row["chosen"] is not None]
        window.destroy()
        if not jobs:
            self._append_log("缺字幕的字幕轨已全部放弃，不压制这些字幕。")
            self.status_var.set("已放弃没有对应字幕的字幕轨")
            return
        self._run_pending_mux(jobs)

    def _run_pending_mux(self, jobs: list[dict]):
        """把补选的字幕压进对应文件：每个文件单独重跑压制步骤（识别 / 翻译结果沿用）。"""
        tasks: list[dict] = []
        for row in jobs:
            record = row["record"]
            tracks = [dict(item) for item in (record.get("tracks") or [])]
            index = int(row["index"])
            if not 0 <= index < len(tracks):
                continue
            spec = dict(tracks[index])
            spec.pop("bind", None)          # 用户手选的字幕 → 直接按这个文件用
            spec["kind"] = "external"
            spec["mode"] = ""
            spec["path"] = str(row["chosen"])
            spec["title"] = spec.get("title") or row["chosen"].stem
            tracks[index] = spec
            tasks.append({
                "record": record,
                "step": {"kind": "mux", "page": "压制", "label": "压制（补选字幕）",
                         "detail": row["chosen"].name,
                         "settings": {"format": record.get("format") or "srt",
                                      "language": record.get("language") or "原文",
                                      "drop_subtitles": record.get("drop_subtitles") or [],
                                      "mux_tracks": tracks}},
            })
        if not tasks:
            self.status_var.set("没有可重新压制的文件")
            return
        self._set_busy(True)
        self.status_var.set(f"正在用补选的字幕压制 {len(tasks)} 个文件…")
        self._append_log(f"开始用补选的字幕压制 {len(tasks)} 个文件…")
        threading.Thread(target=self._pending_mux_worker, args=(tasks,),
                         daemon=True).start()

    def _pending_mux_worker(self, tasks: list[dict]):
        """后台线程：逐个文件用补选的字幕重新压制；不碰任何 Tk 控件。"""
        outputs: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for task in tasks:
            record = task["record"]
            path = Path(str(record.get("media") or ""))
            name = path.name

            def log(text, name=name):
                self.events.put(("log", f"[{name}] {text}"))

            try:
                outcome = run_plan_for_media(
                    path, [task["step"]], log=log,
                    prepared=record.get("prepared"),
                    options=record.get("options") or {})
            except PlanSkipped as exc:
                skipped.append(f"{name}：{exc.reason}")
                continue
            except Exception as exc:
                errors.append(f"{name}：{exc}")
                continue
            for output in outcome.get("outputs") or []:
                outputs.append(str(output))
        lines: list[str] = []
        if outputs:
            lines.append(f"已生成 {len(outputs)} 个文件："
                         + "、".join(Path(item).name for item in outputs[:6])
                         + ("…" if len(outputs) > 6 else ""))
        if skipped:
            lines.append("跳过：" + "；".join(skipped))
        if errors:
            lines.append("失败：" + "；".join(errors))
        self.events.put(("pending_done", "\n".join(lines) or "没有生成任何文件。", outputs))

    def _on_pending_mux_done(self, message: str, outputs: list[str]):
        self._set_busy(False)
        for output in outputs:
            self._append_log(f"补选压制输出：{output}")
        self._append_log("补选字幕压制：" + str(message).replace("\n", " · "))
        self.status_var.set("补选字幕压制完成" if outputs else "补选字幕压制结束（没有输出）")
        messagebox.showinfo("补选字幕压制", message)

    def _run_worker(self, status: str, function, *args):
        if self.busy:
            return
        self._set_busy(True)
        self.status_var.set(status)

        def worker():
            try:
                result = function(*args)
                self.events.put(("result", function.__name__, result))
            except Exception as exc:
                self.events.put(("error", str(exc), traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for button in (getattr(self, "choose_button", None),
                       getattr(self, "load_subtitle_button", None),
                       getattr(self, "asr_button", None),
                       getattr(self, "plan_asr_button", None),
                       getattr(self, "translate_button", None),
                       getattr(self, "plan_translate_button", None),
                       getattr(self, "export_button", None),
                       getattr(self, "mux_button", None),
                       getattr(self, "plan_export_button", None),
                       getattr(self, "plan_mux_button", None)):
            if button is not None:
                button.configure(state=state)
        if busy:
            self.footer_progress.start(12)
        else:
            self.footer_progress.stop()
        self._update_translate_hint()

    def _handle_result(self, name: str, result):
        if name == "_load_media_worker":
            self._choose_audio(result)
        elif name == "_load_subtitle_worker":
            self._subtitle_loaded(result)
        elif name == "_transcribe_worker":
            entries = result["entries"]
            self.entries = entries
            self.original_entries = copy.deepcopy(entries)
            self.translated = []
            self.subtitle_source = {"kind": "generated"}
            self._populate_tree()
            self.refresh_preview()
            self.asr_status_var.set(f"识别完成：{len(entries)} 条 · {result['model']}")
            self._append_log(f"识别完成：{len(entries)} 条 · 模型 {result['model']}")
            self.status_var.set(f"识别完成：{len(entries)} 条，可继续翻译")
        elif name == "_translate_worker":
            if result.get("cancelled"):
                self._set_translate_running(False)
                self._append_log("翻译已取消（未写入半成品）。")
                self.status_var.set("翻译已取消")
                message = "已取消：字幕保持原文，可重新开始"
            else:
                self.translated = result["translated"]
                self.entries = result["translated"]
                self._populate_tree()
                self.refresh_preview()
                self._set_translate_running(False)
                total = max(1, result["total"])
                self.translate_progress.configure(maximum=total, value=total)
                self._append_log(f"翻译完成：{result['total']} 条 · tokens {result['tokens']:,}")
                self.status_var.set(f"翻译完成：{result['total']} 条")
                message = (f"完成：{result['total']} 条 · 本轮消耗 "
                           f"{result['tokens']:,} tokens")
            self._update_entry_stats()
            self.translate_progress_var.set(message)
        elif name == "_export_worker":
            paths = [Path(item) for item in
                     (result if isinstance(result, (list, tuple)) else [result])]
            if paths:
                messagebox.showinfo("导出完成", f"已生成 {len(paths)} 个文件：\n"
                                    + "\n".join(str(path) for path in paths))
                for path in paths:
                    self._append_log(f"导出完成：{path}")
                self.status_var.set(f"已导出 {len(paths)} 个文件" if len(paths) > 1
                                    else f"已导出：{paths[0].name}")
            else:
                self.status_var.set("导出结束：没有生成文件")
        elif name == "_mux_worker":
            paths = [Path(item) for item in (result.get("outputs") or [])]
            dropped = result.get("dropped") or []
            tokens = int(result.get("tokens") or 0)
            for path in paths:
                self._append_log(f"压制完成：{path}")
            for item in dropped:
                self._append_log(f"跳过字幕轨：{item['label']}（与 {item['target']} 同语言且内容雷同 "
                                 f"{item['ratio']:.0%}）")
            if tokens:
                self._append_log(f"重复检查 token：{tokens:,}")
            if paths:
                extra = f"（另有 {len(dropped)} 条重复字幕轨未压入）" if dropped else ""
                messagebox.showinfo("压制完成", f"已生成：\n{paths[0]}{extra}")
                self.status_var.set(f"已压制：{paths[0].name}")
            else:
                self.status_var.set("压制结束：没有生成文件")

    def _poll_events(self):
        if self._closing:
            return
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event[0]
            if kind == "status":
                self.status_var.set(event[1])
                continue
            if kind == "log":
                self._append_log(event[1])
                continue
            if kind == "progress":
                self._on_translate_progress(event[1], event[2])
                continue
            if kind == "plan_file":
                self._on_plan_file(event[1], event[2], event[3])
                continue
            if kind == "plan_step":
                self._on_plan_step(event[1], event[2], event[3])
                continue
            if kind == "plan_progress":
                self._on_plan_progress(event[1], event[2])
                continue
            if kind == "plan_result":
                self._on_plan_result(event[1], event[2])
                continue
            if kind == "plan_error":
                self._on_plan_error(event[1], event[2], event[3])
                continue
            if kind == "plan_skip":
                self._on_plan_skip(event[1], event[2], event[3])
                continue
            if kind == "plan_summary":
                self._on_plan_summary(event[1])
                continue
            if kind == "plan_done":
                self._on_plan_done(event[1])
                continue
            if kind == "pending_done":
                self._on_pending_mux_done(event[1], event[2])
                continue
            self._set_busy(False)
            if kind == "error":
                self._set_translate_running(False)
                self._update_translate_hint()
                message = str(event[1]) or "未知错误"
                self._append_log(f"错误：{message}")
                if len(event) > 2 and event[2]:
                    tail = "\n".join(str(event[2]).strip().splitlines()[-6:])
                    self._append_log(tail)
                self.status_var.set("操作失败")
                messagebox.showerror("处理失败", message)
                continue
            _, name, result = event
            self.status_var.set("就绪")
            self._handle_result(name, result)
        self._poll_after = self.root.after(80, self._poll_events)

    def run(self):
        self.root.mainloop()


def cli_inspect(args) -> int:
    info = probe_media(args.media)
    audio, embedded, videos = probe_tracks(info)
    print(f"文件：{args.media}")
    print(f"视频流：{len(videos)}  音轨：{len(audio)}  内嵌字幕：{len(embedded)}")
    for track in audio:
        print(f"  {track['label']}")
    for track in embedded:
        print(f"  {track['label']} [{track['codec']}]")
    for path in subtitle_candidates(Path(args.media)):
        print(f"  外置字幕：{path.name}")
    return 0


def cli_transcribe(args) -> int:
    media = Path(args.media).resolve()
    info = probe_media(media)
    audio, _embedded, _videos = probe_tracks(info)
    if args.audio_track < 0 or args.audio_track >= len(audio):
        raise StudioError(f"音轨编号超出范围，检测到 {len(audio)} 条音轨。")
    output = Path(args.output) if args.output else media.with_name(media.stem + "_recognized.srt")
    with tempfile.TemporaryDirectory(prefix="media_asr_") as temp_dir:
        wav = Path(temp_dir) / "audio.wav"
        audio_to_wav(media, args.audio_track, wav)
        entries = transcribe_audio(wav, args.model, args.language)
    write_subtitle(entries, output)
    print(f"识别完成：{len(entries)} 条 → {output}")
    return 0


def cli_translate(args) -> int:
    entries = parse_subtitle_file(args.subtitle)
    translated, cancelled = translated_entries(
        entries, args.source, args.target, args.model,
        context_lines=args.context)
    if cancelled:
        raise StudioError("翻译已取消。")
    default_name = (Path(args.subtitle).stem + "_bilingual.ass" if args.format == "ass"
                    else Path(args.subtitle).stem + "_translated.srt")
    output = Path(args.output) if args.output else Path(args.subtitle).with_name(default_name)
    expected_extension = ".ass" if args.format == "ass" else ".srt"
    if not output.suffix:
        output = output.with_suffix(expected_extension)
    elif output.suffix.lower() != expected_extension:
        raise StudioError(f"--format {args.format} 要求输出扩展名为 {expected_extension}。")
    if args.format == "ass":
        write_bilingual_ass(entries, translated, output)
    else:
        write_subtitle(translated, output)
    print(f"翻译完成：{len(translated)} 条 → {output}")
    return 0


def cli_mux(args) -> int:
    languages = list(args.language or [])
    specs = [{"path": path,
              "language": languages[index] if index < len(languages) else None}
             for index, path in enumerate(args.subtitle)]
    output = mux_subtitle(args.media, specs, args.output, args.container,
                          drop_subtitles=args.drop_subtitle)
    print(f"已封装 {len(specs)} 条字幕轨：{output}")
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本地 Whisper 识别、AI 翻译、预览与字幕轨重新封装。无子命令时打开 GUI。"
    )
    subparsers = parser.add_subparsers(dest="command")
    inspect_parser = subparsers.add_parser("inspect", help="列出媒体的音轨、字幕轨和同目录字幕")
    inspect_parser.add_argument("media")
    inspect_parser.set_defaults(handler=cli_inspect)
    asr_parser = subparsers.add_parser("transcribe", help="使用本地 Whisper 识别指定音轨")
    asr_parser.add_argument("media")
    asr_parser.add_argument("--audio-track", type=int, default=0, help="从 0 开始的音轨编号")
    asr_parser.add_argument("--model", choices=WHISPER_MODELS, default=default_whisper_model())
    asr_parser.add_argument("--language", default="", help="Whisper 语言代码；留空自动检测")
    asr_parser.add_argument("-o", "--output")
    asr_parser.set_defaults(handler=cli_transcribe)
    translate_parser = subparsers.add_parser("translate", help="翻译字幕文件")
    translate_parser.add_argument("subtitle")
    translate_parser.add_argument("--source", default="自动检测", choices=list(LANGUAGES))
    translate_parser.add_argument("--target", default="中文（简体）",
                                  choices=[lang for lang in LANGUAGES if lang != "自动检测"])
    translate_parser.add_argument("--model", help="api_settings.json 中的模型名称")
    translate_parser.add_argument("--format", choices=("srt", "ass"), default="srt",
                                  help="srt 输出译文；ass 输出原文+译文双语字幕")
    translate_parser.add_argument(
        "--context", type=int, default=DEFAULT_CONTEXT_LINES,
        help=(f"上下文句数：前后各 N 条非空字幕只作参考不翻译"
              f"（0–{CONTEXT_LINES_MAX}，默认 {DEFAULT_CONTEXT_LINES}，0 = 关闭）"))
    translate_parser.add_argument("-o", "--output")
    translate_parser.set_defaults(handler=cli_translate)
    mux_parser = subparsers.add_parser("mux", help="将字幕重新封装为独立字幕流，不烧录画面")
    mux_parser.add_argument("media")
    mux_parser.add_argument("subtitle", nargs="+",
                            help="要压制的字幕文件（可多个 → 多条字幕轨，第一条为默认轨）")
    mux_parser.add_argument("-o", "--output")
    mux_parser.add_argument("--container", default="auto",
                             help="auto 默认 MKV/MKA，也可指定 mkv/mka/mp4/mov/webm")
    mux_parser.add_argument("--language", action="append", metavar="LANG",
                             help="每条字幕的语言标记（可重复，按顺序对应；缺省从文件名推断）")
    mux_parser.add_argument("--drop-subtitle", type=int, action="append", metavar="N",
                             help="压制时删除的内嵌字幕序号（0 起，按字幕流顺序，可重复指定）")
    mux_parser.set_defaults(handler=cli_mux)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()               # 先保证帮助 / 输出里的中文能安全写管道或文件
    if argv is None:                # 只有真实启动进程时才自动切换解释器（argv 供测试直接调用）
        relaunched = relaunch_in_venv(list(sys.argv[1:]))
        if relaunched is not None:
            return relaunched
    enable_dpi_awareness()          # 必须在创建 Tk 窗口之前调用
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list or (len(args_list) == 1 and Path(args_list[0]).suffix.lower() in MEDIA_EXTENSIONS):
        initial_path = args_list[0] if args_list else None
        SubtitleStudio(initial_path).run()
        return 0
    parser = make_parser()
    args = parser.parse_args(args_list)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    try:
        return args.handler(args)
    except (StudioError, OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())