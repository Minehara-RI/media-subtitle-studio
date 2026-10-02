# Media Subtitle Studio

本地 Whisper 语音识别 + AI 并发字幕翻译 + 字幕轨无损封装（不烧录画面）的单文件
Python 工具（GUI + CLI，深色工作台界面、高 DPI 自适应）。附 Windows 便携包一键配置脚本。

## 功能

- **语音识别**：本地 Whisper（faster-whisper / OpenAI whisper / transformers 任一），
  可选音轨，模型权重自动缓存
- **AI 翻译**：OpenAI 兼容接口并发翻译，逐条 / 分组两种模式，带上下文、自动降级重试；
  源 / 目标语言可选预设，也可**自定义输入**（如粤语、Klingon，本次会话内有效）
- **字幕封装**：`-c copy` 无损压制为独立字幕轨（MKV/MP4/MOV/WebM），支持删除指定内嵌轨、
  语言标记自动推断、第一条轨自动设为 default
- **压制前检查**：语义级重复字幕检测（同语言且内容雷同才算重复，AI 兜底判定）
- **计划任务**：多文件流水线，识别线程连续刷文件、翻译压制并行跟进，token 统计
- **预览**：视频画面 + 按字幕文件自身格式（ASS 样式表 / SRT 内联标签）实时叠加渲染，
  画面按媒体宽高比自适应拟合；界面为**深色工作台风格**（高 DPI 自适应）

## 快速开始（Windows 便携包）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)（勾选 **Add to PATH**）
2. 下载本仓库（或 Release 里的 zip，**约 110 KB 的轻量包，不含权重**），双击 **`Setup.bat`**：
   - 自动创建 `.venv` 并安装依赖（失败自动切换清华 / 阿里镜像）
   - 权重：先找本机已有缓存（`%USERPROFILE%\.cache\whisper`、Buzz 缓存、`weights\`），
     没有就按需下载 `medium.pt`（约 1.46 GB，**支持断点续传 + SHA-256 校验**，
     中断后重跑 `Setup.bat` 会自动续传；可用 `--weight-mirror` 换源）
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

## 更新日志

### v1.1（2026-10-02）

**界面**

- 换成**深色工作台风格**：深炭色背景与面板、浅色文字、绿色操作强调；按钮 / 输入框 /
  下拉框 / 分页 / 表格 / 进度条 / 列表统一配色，选中、悬停、禁用状态有明确反馈；
  计划任务列表的状态色改为跟随主题。
- 重排「导出与封装」页：拆成**「字幕文件导出」/「字幕轨压制」两个内层页签**，
  每个页签的设置、输出提示、执行按钮和「加入计划」按钮成组排列，不再互相穿插。
- 左侧预览新增**自适应拟合**：按媒体宽高比在可用区域内等比放大并居中，
  载入新帧、调整窗口或切换媒体时都会重新计算。

**功能**

- 源 / 目标语言下拉框新增**「自定义语言…」**：可直接输入任意语言名（如粤语、古希腊语、
  Klingon），本次会话内加入语言列表并原样交给翻译模型；切换后记住上次选择，
  再次打开下拉时若取消输入会回到原选项。

**修复**

- 修复 16 处静态类型问题（Pylance 0 报错），运行行为不变。

### v1.0（2026-09-28）

首个公开版本：本地 Whisper 识别 + AI 并发翻译 + 字幕轨无损封装，含 Windows 便携包一键配置。

## License

MIT

---

<!-- 以下为便携包 README（Setup / 打包细节） -->

# Media Subtitle Studio 便携包

把「本地 Whisper 识别 + AI 翻译 + 字幕封装」工具（`media_subtitle_studio.py`）做成
**即拿即用**的绿色包：换一台电脑，装好 Python 后双击两个 bat 即可。

> **发布包不含 Whisper 权重。** Release 里的 zip 是约 **110 KB** 的轻量包，
> 权重（`medium.pt` 约 1.46 GB）由 `Setup.bat` 首次配置时按需下载，
> **支持断点续传 + SHA-256 校验**，中断后重跑 `Setup.bat` 会自动接着下。
> 这样 Release 秒传秒下，也不必把 1.4 GB 的模型塞进压缩包或仓库。

## 文件一览

| 文件 | 作用 |
| --- | --- |
| `media_subtitle_studio.py` | 程序本体（GUI + CLI） |
| `Setup.bat` | **首次配置**：建 `.venv`、装依赖、下载权重、配 API Key、AI 自检 |
| `Start-MediaSubtitleStudio.bat` | 日常启动（无黑窗；也支持把媒体文件拖到它上面） |
| `setup_portable.py` | 配置脚本本体（bat 只是个壳；可直接 `python setup_portable.py --check` 体检） |
| `api_settings.template.json` | API 配置模板（**不含密钥**）；Setup 首次运行据此生成 `api_settings.json` |
| `api_settings.json`（首次配置后生成） | 实际生效的 API 配置，**含 API Key，不要外发** |
| `weights\`（可选，发布包不含） | 放 `.pt` 权重 → 免联网复制 Whisper 模型（离线分发用） |

## 首次使用（新机器）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)（勾选 **Add to PATH**）。
2. 双击 `Setup.bat`。它会自动：
   - 建独立虚拟环境 `.venv`（不污染系统 Python），装齐
     `pillow / tkinterdnd2 / opencv-python / numpy / faster-whisper / requests`；
   - **Whisper 权重**：先找本机已有缓存（`%USERPROFILE%\.cache\whisper`、Buzz 缓存、
     `WHISPER_MODEL_DIR`、便携包内 `weights\`）；都没有就提示下载 `medium.pt`
     （约 1.46 GB，支持断点续传与 SHA-256 校验）；
   - **API Key**：默认从本机既有 `api_settings.json` 自动复制（`--from-ref` 指定模型名，
     `默认` 取第一个）；没有既有配置时交互输入；双击运行无法交互时会提示手动编辑；
   - **AI 自检**：真调一次 chat/completions，并把配置丢给 AI 复核完整性。
3. 双击 `Start-MediaSubtitleStudio.bat` 开始使用。

## 命令行速查

```bat
python setup_portable.py              :: 全流程（缺什么补什么，已配好的自动跳过）
python setup_portable.py --check      :: 只体检：依赖 / 权重 / API 配置 / ffmpeg
python setup_portable.py --download-weights          :: 只下载权重（默认 medium.pt）
python setup_portable.py --download-weights small    :: 只下载指定权重
python setup_portable.py --download-weights medium --weight-mirror <镜像地址>
python setup_portable.py --collect-weights  :: 把本机已缓存的 .pt 权重复制进 weights\（打包用）
python setup_portable.py --from-ref 默认            :: API 配置从本机既有配置复制
python setup_portable.py --api-url <url> --api-key <key> --api-model <id>
python setup_portable.py --no-whisper :: 跳过权重（首次识别时自动下载）
python setup_portable.py --only-env   :: 只装 pip 依赖
```

权重下载说明：

- 直链取自 OpenAI 官方 CDN（`openaipublic.azureedge.net`），URL 里的目录名就是官方 SHA-256，
  下载完成后逐字节校验，校验不过自动换源重下。
- **中断可续**：未下完的文件留在 `%USERPROFILE%\.cache\whisper\*.pt.part`，
  重跑 `Setup.bat` / `--download-weights` 会从断点继续，不会从头再来。
- **可换源**：直连慢时用 `--weight-mirror <地址>`（或环境变量 `MSS_WEIGHT_MIRROR`），
  镜像上放同名 `.pt` 即可；脚本会自动回退，且仍然按官方哈希校验。

## 打包发布（维护者）

- **GitHub Release**：打**不含 `weights\`** 的轻量包（约 110 KB），权重交给首次配置下载。
- **离线分发（网盘等）**：才把 `weights\` 一起打包（约 1.5 GB）；
  用 `python setup_portable.py --collect-weights` 把本机缓存收进 `weights\`。
- `.gitignore` 已忽略 `weights/`、`wheels/`、`.venv/`、`api_settings.json`，别提交进仓库。

## 把包拷到别的电脑

1. 整个 `MediaSubtitleStudio_Portable` 文件夹拷走（含 `weights\` 就免下载权重）。
2. 新机器装好 Python → 双击 `Setup.bat`（权重按需下载或复制；API Key 会自动从本机既有配置复制；
   没有就交互输入，或用 `--from-ref` / `--api-key` 参数）。
3. 双击 `Start-MediaSubtitleStudio.bat` 使用。
4. FFmpeg 新机器需自行安装并加入 `PATH`（体检项会提示）。

## 离线部署（可选）

- 依赖：在有网的机器上 `pip download -d wheels pillow tkinterdnd2 opencv-python numpy faster-whisper requests`，
  把 `wheels\` 一起拷走 → 断网安装走 `--no-index --find-links`。
- 权重：把 `%USERPROFILE%\.cache\whisper\*.pt` 拷进 `weights\`。
- FFmpeg：程序会在 `PATH`、`D:\Program Files\ffmpeg\bin` 等常见位置找 `ffmpeg/ffprobe`，
  新机器需自行安装 FFmpeg 并加入 `PATH`（体检项会提示）。

## 常见问题

- **双击 Setup.bat 闪退** → 命令行里手动跑 `py -3 setup_portable.py` 看报错。
- **国内装依赖慢/失败** → 脚本内置清华 / 阿里镜像自动兜底；也可用 `--offline` 只走本地 wheels。
- **权重下载中断了** → 直接重跑 `Setup.bat`（或 `--download-weights`）会断点续传；
  实在下不动就用 `--weight-mirror` 换源。
- **想跳过 1.46 GB 下载** → `python setup_portable.py --no-whisper`；之后把任意
  `.pt`（`tiny.en / base / small / medium / large-v3`）放进 `%USERPROFILE%\.cache\whisper` 即可。
- **API 自检失败** → 检查 `api_settings.json` 里的 `api_key` / `url` / `model`，改完重跑 `Setup.bat`。
- **启动后想看日志** → 用 `python media_subtitle_studio.py` 而不是 `pythonw`，控制台会回显
  Whisper 识别结果与 AI 返回（环境变量 `MSS_ECHO=0` 关闭）。
