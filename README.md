# Media Subtitle Studio

本地 Whisper 语音识别 + AI 并发字幕翻译 + 字幕轨无损封装（不烧录画面）的单文件
Python 工具（GUI + CLI）。附 Windows 便携包一键配置脚本。

## 功能

- **语音识别**：本地 Whisper（faster-whisper / OpenAI whisper / transformers 任一），
  可选音轨，模型权重自动缓存
- **AI 翻译**：OpenAI 兼容接口并发翻译，逐条 / 分组两种模式，带上下文、自动降级重试
- **字幕封装**：`-c copy` 无损压制为独立字幕轨（MKV/MP4/MOV/WebM），支持删除指定内嵌轨、
  语言标记自动推断、第一条轨自动设为 default
- **压制前检查**：语义级重复字幕检测（同语言且内容雷同才算重复，AI 兜底判定）
- **计划任务**：多文件流水线，识别线程连续刷文件、翻译压制并行跟进，token 统计
- **预览**：视频画面 + 按字幕文件自身格式（ASS 样式表 / SRT 内联标签）实时叠加渲染

## 快速开始（Windows 便携包）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)（勾选 **Add to PATH**）
2. 下载本仓库（或 Release 里的 zip），双击 **`Setup.bat`**：
   - 自动创建 `.venv` 并安装依赖（失败自动切换清华 / 阿里镜像）
   - 复制 Whisper 权重（Release 附件 / `weights\` 目录），或首次识别时自动下载
   - 配置 AI：把 `api_settings.template.json` 复制为 `api_settings.json` 并填入你的
     API Key（也可用 `--from-ref` 从本机既有配置复制，或交互输入）
   - AI 自检：真实调用一次 chat/completions 验证配置
3. 双击 **`Start-MediaSubtitleStudio.bat`** 打开 GUI（支持拖入媒体文件）

## CLI 用法

```bat
python media_subtitle_studio.py inspect video.mkv          :: 查看轨道信息
python media_subtitle_studio.py transcribe video.mkv       :: 识别 → srt
python media_subtitle_studio.py translate video.srt        :: AI 翻译（--format ass 出双语）
python media_subtitle_studio.py mux video.mkv a.srt b.ass  :: 多条字幕无损封装
```

## API 配置

复制 `api_settings.template.json` 为 `api_settings.json`，填入任意 OpenAI 兼容服务
（DeepSeek / GLM / OpenAI 等均可）：

```json
{
  "models": [
    {
      "name": "DeepSeek",
      "url": "https://api.deepseek.com/v1/chat/completions",
      "api_key": "sk-...",
      "model": "deepseek-chat",
      "max_concurrent": 10
    }
  ],
  "default_model": "DeepSeek"
}
```

`api_settings.json` 含密钥，已在 `.gitignore` 中排除，请勿提交或外发。

## 依赖

- Python 3.10+；`pillow`、`tkinterdnd2`（拖拽）、`opencv-python`（预览）、
  `faster-whisper` 或 `openai-whisper`（识别）——`Setup.bat` 会自动装
- [FFmpeg](https://ffmpeg.org/download.html)（`ffmpeg` / `ffprobe` 加入 PATH）
- 可选：`libmpv-2.dll`（进程内音频时钟，预览音画同步更稳）

## License

MIT

---

<!-- 以下为原便携包 README（Setup / 打包细节） -->

# Media Subtitle Studio 便携包

把「本地 Whisper 识别 + AI 翻译 + 字幕封装」工具（`media_subtitle_studio.py`）做成
**即拿即用**的绿色包：换一台电脑，装好 Python 后双击两个 bat 即可。

## 文件一览

| 文件 | 作用 |
| --- | --- |
| `media_subtitle_studio.py` | 程序本体（GUI + CLI） |
| `Setup.bat` | **首次配置**：建 `.venv`、装依赖、复制权重、配 API Key、AI 自检 |
| `Start-MediaSubtitleStudio.bat` | 日常启动（无黑窗；也支持把媒体文件拖到它上面） |
| `setup_portable.py` | 配置脚本本体（bat 只是个壳；可直接 `python setup_portable.py --check` 体检） |
| `api_settings.template.json` | API 配置模板（**不含密钥**）；Setup 首次运行据此生成 `api_settings.json` |
| `api_settings.json`（首次配置后生成） | 实际生效的 API 配置，**含 API Key，不要外发** |
| `weights\`（可选） | 放 `.pt` 权重 → 免联网复制 Whisper 模型 |
