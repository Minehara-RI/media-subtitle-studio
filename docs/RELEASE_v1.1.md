本地 Whisper 语音识别 + AI 并发字幕翻译 + 字幕轨无损封装。GUI + CLI 单文件工具，深色工作台界面，高 DPI 自适应。

## ⚠️ 这个包不含模型（下载前先看）

附件 zip **只有约 110 KB**，里面是程序本体和配置脚本，**不含 Whisper 权重**。上一个版本的大包是 1.31 GB，其中 1.31 GB 全是 `medium.pt`，上传极慢且容易失败 —— 现在改成：

- 权重（`medium.pt` 约 1.46 GB）由 `Setup.bat` **首次配置时按需下载**
- **支持断点续传**：下到一半断网、关窗口都能续，重跑 `Setup.bat` 接着下
- **SHA-256 校验**：按 OpenAI 官方哈希逐字节校验，下坏自动换源重下
- 本机已有缓存（`%USERPROFILE%\.cache\whisper`、Buzz 缓存等）则**自动跳过，不重复下载**

| 版本 | 附件大小 | 模型 |
| --- | --- | --- |
| 本版 v1.1 | **约 110 KB** | 首次配置按需下载 |
| 上一版 v1.0 | 约 1.31 GB | 已内置于 `weights\` |

不想联网下模型？下载任意一个 `.pt`（`tiny.en` / `base` / `small` / `medium` / `large-v3`）放进 `%USERPROFILE%\.cache\whisper\` 即可，程序会自动发现。

## v1.1 更新内容

**界面**

- 换成**深色工作台风格**：深炭色背景与面板、浅色文字、绿色操作强调；按钮 / 输入框 / 下拉框 / 分页 / 表格 / 进度条 / 列表统一配色，选中、悬停、禁用状态有明确反馈；计划任务列表的状态色改为跟随主题。
- 重排「导出与封装」页：拆成**「字幕文件导出」/「字幕轨压制」两个内层页签**，每个页签的设置、输出提示、执行按钮和「加入计划」按钮成组排列，不再互相穿插。
- 左侧预览新增**自适应拟合**：按媒体宽高比在可用区域内等比放大并居中，载入新帧、调整窗口或切换媒体时都会重新计算。

**功能**

- 源 / 目标语言下拉框新增**「自定义语言…」**：可直接输入任意语言名（如粤语、古希腊语、Klingon），本次会话内加入语言列表并原样交给翻译模型；切换后记住上次选择，再次打开下拉时若取消输入会回到原选项。

**修复**

- 修复 16 处静态类型问题（Pylance 0 报错），运行行为不变。
- 顺带修好便携包的权重下载：原先内置的哈希表是错的（`base` / `small` 与官方 SHA-256 不符），真跑必然校验失败；现已改为官方真实哈希并支持断点续传。

## 快速开始（Windows）

1. 装 [Python 3.10+](https://www.python.org/downloads/)，勾选 **Add to PATH**
2. 装 [FFmpeg](https://ffmpeg.org/download.html)，把 `ffmpeg` / `ffprobe` 加入 `PATH`
3. 解压附件，双击 **`Setup.bat`** —— 自动建 `.venv`、装依赖（失败自动切清华 / 阿里镜像）、按需下载权重、配置 AI Key、AI 自检
4. 双击 **`Start-MediaSubtitleStudio.bat`** 打开 GUI（支持把媒体文件拖进去）

AI 翻译需要自备任意 OpenAI 兼容服务的 Key（DeepSeek / GLM / OpenAI 等均可），首次配置时按提示填入即可。

## 附件

| 文件 | 大小 | 说明 |
| --- | --- | --- |
| `MediaSubtitleStudio_Portable_20261002.zip` | 109.4 KB | Windows 便携包（不含权重） |

```
SHA-256  0f4ccfbe36b92517bc7d544120736ce4df8ea03bce5570655ea94750f701f8d2
```

校验（PowerShell）：

```powershell
Get-FileHash .\MediaSubtitleStudio_Portable_20261002.zip -Algorithm SHA256
```

## 命令行速查

```bat
python media_subtitle_studio.py inspect video.mkv          :: 查看轨道信息
python media_subtitle_studio.py transcribe video.mkv       :: 识别 → srt
python media_subtitle_studio.py translate video.srt        :: AI 翻译（--format ass 出双语）
python media_subtitle_studio.py mux video.mkv a.srt b.ass  :: 多条字幕无损封装

python setup_portable.py --check                      :: 体检：依赖 / 权重 / API / ffmpeg
python setup_portable.py --download-weights           :: 只下载权重（默认 medium.pt）
python setup_portable.py --download-weights small     :: 只下载指定权重
python setup_portable.py --weight-mirror <镜像地址>    :: 换源下载
python setup_portable.py --no-whisper                 :: 跳过权重
```

## 系统要求

- Windows 10 / 11（便携包针对 Windows；程序本体为跨平台 Python 脚本）
- Python 3.10+
- FFmpeg（`ffmpeg` / `ffprobe` 在 `PATH` 中）
- 首次配置需联网（装依赖、下载权重、填 AI Key）

---

完整说明见 [README](https://github.com/Minehara-RI/media-subtitle-studio#readme) ｜ 问题反馈请开 [Issue](https://github.com/Minehara-RI/media-subtitle-studio/issues)

---

<!-- ⬇️ 下面这段是给发布者看的备忘，粘贴到 Release 正文时请整段删掉 -->

## 发布备忘（不要粘进 Release）

- **Tag**：建议 `v1.1`
- **Release title**：`v1.1 — 深色工作台界面 + 自定义翻译语言 + 预览自适应`
- **附件**：`MediaSubtitleStudio_Portable_20261002.zip`
  - 路径：`D:\Downlands\MediaSubtitleStudio_Portable_20261002.zip`
  - 大小：112,037 字节（109.4 KB）
  - SHA-256：`0f4ccfbe36b92517bc7d544120736ce4df8ea03bce5570655ea94750f701f8d2`
- 本文从第一行到上面那条 `---` 为止，即 Release 正文。

