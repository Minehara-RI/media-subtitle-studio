# Media Subtitle Studio

`media_subtitle_studio.py` 是一个**单文件自包含**的视频 / 音频字幕 GUI 与 CLI：字幕解析、
生成与并发 AI 翻译内核已内嵌在本文件内（见源码中的「内嵌字幕核心」一节），**不依赖任何同目录脚本**
（原 `S_subtitles.py` 已于 2026-09-27 删除）；配置仍读取程序同目录下的 `api_settings.json`。

界面使用 **PySide6** 实现，GUI 与 CLI 保持在这一个 Python 文件中，不再依赖 Tkinter。
后台处理使用有界 Qt 线程池；字幕列表采用按需读取的表格模型，视频帧先缩放到预览尺寸，
字幕覆盖层使用有界缓存，避免大分辨率视频和长字幕表拖慢界面。

> **与 `Subtitle_Studio_All_in_One.py` 的关系**：两者都是自包含程序，互不依赖、功能不重叠。
> `Subtitle_Studio_All_in_One.py` 是**三个旧程序的合一版**：
> `S_subtitles.py`（转换 / 翻译）+ `subtitle_cli.py`（命令行）+ `subtitle_auto.bat`（一键流程），
> 界面重写为**三标签页**：① 格式转换 ② AI 翻译 + 转换 ③ Whisper 识别 + 翻译 + 转换；
> 它**不包含**本文件的媒体工作台能力（视频预览、字幕样式叠加、字幕轨封装）。
> 那三个旧程序**已于 2026-09-27 全部删除**（功能已全部并入合一版），`S_ASMR_system.bat` 调用的即是合一版。
> 本文件保留为独立的媒体工作台版本（PySide6 界面，含播放同步 / ASS 样式预览）。

## 功能

- 拖入媒体后读取视频、全部音轨、内嵌字幕轨和同目录同名前缀字幕文件；
  一次拖入「媒体 + 同名字幕」或单独拖入字幕文件都能被识别。
- 在 GUI 内连续播放视频，可暂停 / 拖动进度 / 上一句 / 下一句；字幕随播放时间叠加，
  且不会烧录到视频。音画同步由**音频主时钟**驱动（libmpv → waveOut → ffplay 逐级回退）。
- **播放跟随所选音轨**：在「音轨」下拉框里换一条音轨，正在播放的音频会立即切过去
  （mpv 用 `aid`、waveOut 用 `ffmpeg -map 0:a:N`、ffplay 回退用 `-ast a:N`），无需暂停重播。
- 画面按音频位置或墙钟校准；如有残留偏差可用界面上的「同步」微调（见下文）。
- 字幕预览按字幕文件自身的格式渲染：ASS 读取样式表与覆盖标签，SRT/VTT 支持内联标签。
- 自动清理字幕文件中的 `<font>`、`<i>` 等展示标签，避免标签原样显示。
- 为所选音轨运行本地 Whisper；不同音轨可分别识别。支持 `tiny`、`base`、`small`、
  `medium`、`large-v3` 模型，识别语言可单独选择。
- 调用已有 AI 配置翻译字幕：36 种语言、可调并发、逐条或分组翻译、可随时取消、
  实时进度与运行日志。
- 独立选择字幕格式（SRT/ASS/VTT）、位置（外挂/内嵌）和语言（原文/译文/双语）；
  内嵌通过无损重封装，不烧录画面，并在界面上预览预计输出文件名。
- 默认输出到输入媒体所在目录。自动封装容器为有视频时 MKV、纯音频时 MKA。

## 界面布局

1. 顶部：`选择媒体…` / `载入字幕…`，下方是拖放提示条。
2. 左侧（自上而下）：播放预览（画面 + 实时字幕叠加）、播放/暂停、上一句/下一句、
   进度条与时间，以及**运行日志**（预览下方，随窗口拉伸）。
3. 右侧页签：
   - **媒体与字幕**：文件大小与轨道统计、音轨、
     **字幕来源**（末尾固定有「导入外部字幕文件…」，选中即弹出文件对话框，
     默认目录与媒体文件一致，取消则回到原选项）、字幕条目列表。
   - **识别**：Whisper 模型与已缓存模型提示、音频语言、开始识别。
   - **翻译**：翻译模型、并发请求数、分组翻译、源 / 目标语言、翻译来源、进度与取消。
   - **导出与封装**：分为「外挂字幕」与「内嵌字幕」两个子页；内嵌页可组合生成字幕和多份外挂字幕，
     控制是否保留源字幕轨，并在封装前检查同语言重复字幕。
4. **计划任务**：组合识别、翻译、外挂字幕导出和内嵌封装步骤，批量处理文件并支持停止。
5. 底部：状态栏与进度指示。

## 高 DPI 适配

- 启动时启用 Windows **每显示器 DPI 感知**（`SetProcessDpiAwarenessContext` →
  `shcore.SetProcessDpiAwareness` → `SetProcessDPIAware` 逐级回退），
  控件尺寸由 Qt 按系统缩放处理。
- 窗口采用响应式分割布局，字幕表格不会为每行创建独立控件。

## 并发翻译面板

`翻译` 页签把并发相关的控制集中到一处，并与 `api_settings.json` 自动联动：

- **翻译模型**：下拉列出配置中的模型；切换模型会**自动把并发数重置为该模型的默认值**。
- **并发请求数**：1–100；数值非法会在开始前拦截并提示。
- **分组翻译**：关闭 = 逐条请求（时间轴对齐更严格）；开启 = 每 N 行合并成一次请求
  （N 取 2–50，默认 10）。批次失败或缺行时会自动降级为逐条翻译。
- **开始 / 取消**：任务运行时按钮与输入控件互斥；`取消翻译` 置位取消事件，
  由于在途 HTTP 请求无法中断，取消会在**当前批次返回后**停止，并保留原文。
- **进度**：确定式进度条由翻译调度器的进度回调直接驱动。
- **运行日志**：批次进度、失败摘要与 token 用量，放在独立日志页。
- 翻译进度通过 Qt 信号回传主线程；取消事件在当前请求返回后生效。

## 播放与音画同步

音画同步的关键是**画面的时间基准优先来自音频**。程序按下面的优先级尝试取得音频时钟：

1. **libmpv（首选）**：进程内播音频，直接读 `audio-pts` 当作时钟——它就是「正在播出的音频位置」，
   所以音频真正开始前画面会保持等待，不会出现「画面先跑、声音后到」的错位；
   支持播放中在线 seek（拖进度条不重启播放器）与精确暂停。
   需要 `libmpv-2.dll`：放程序目录，或用环境变量 `MSS_LIBMPV` / `LIBMPV_PATH` 指定，
   程序也会自动搜索 `mpv*\libmpv-2.dll`、`D:\Program Files\mpv`、`C:\Program Files\mpv` 等位置。
2. **waveOut（没有 libmpv 时的兜底）**：ffmpeg 解码 PCM → 纯标准库 ctypes 调 waveOut 播放，
   用「缓冲区播完事件」累加已播字节并持续重锚时钟（实测：30s 音频 30.24s 播完，10s 漂移 0ms）。
   注意：播完 100ms 缓冲区才产生一次锚点，因此存在 ≤1 个缓冲的固定滞后。
3. **ffplay + 墙钟（最后兜底）**：没有任何可查询的音频时钟时，音频仍由 `ffplay -vn` 播放，
   画面按墙钟锚点驱动并丢帧保实时；此时「同步」微调用于手工补偿音频进程的启动延迟。

- **画面调度**：以音频位置（或墙钟）为基准校准解码位置，落后超过约 1.8 帧才跳转。
- **跳转**：支持在线 seek 的时钟（libmpv）只发一个 seek 命令，时钟立即跳到新位置并继续；
  其它情况才重启音频进程重新锚定。
- **同步微调**：右侧「同步」= 画面相对音频的额外延迟（秒，**默认 0**）。
  用 mpv / waveOut 时钟时通常保持 0；个别声卡、蓝牙耳机的输出延迟较大时可用 0.05 步长边播边调。
- **音频时钟超过 2 秒仍未开始**会自动回退到墙钟。
- **跟随所选音轨**：三个音频后端都按「音轨」下拉框的序号取流（mpv 设 `aid = 序号 + 1`，
  waveOut 用 `-map 0:a:序号`，ffplay 回退用 `-ast a:序号`）。播放中切换音轨会先重锚墙钟
  再重建音频时钟，日志打印 `已切换播放音轨：音轨 N`。

## 字幕渲染（按文件格式）

预览里的字幕不再是固定白色样式，而是按字幕文件自身的格式绘制：

- **ASS/SSA**：读取 `[Script Info]` 的 `PlayResX/Y` 与 `[V4+ Styles]` 样式表，
  按样式渲染字体名、字号（随画面高度缩放）、主色、描边、粗体、对齐与边距；
  支持常用覆盖标签 `\an`、`\a`、`\b`、`\i`、`\c`/`\1c`、`\N`、`\n`、`\h`、`\r`；
  矢量绘图（`\p1`）条目不会当作文字渲染。
- **SRT/VTT/SMI**：识别 `<b>`、`<i>`、`<u>`、`<font color=...>` 与 `<br>`，
  斜体用倾斜合成、颜色按标签显示。
- 字体按 ASS 样式指定的字体渲染；视频帧先缩小到预览控件大小再转换为 Qt 图像。
- 字幕图层按字幕行、模式和尺寸缓存，最多保留 32 项。
- 另外修正了 ASS 解析中的两个格式问题：`&HBBGGRR` 颜色字节序、以及字幕文本开头多出的字段分隔符
  （导出与预览都已修正）。

## 运行

需要 `PySide6>=6.8`。还需要 FFmpeg / ffprobe 在 `PATH` 中；程序也会检查
常见 Windows 安装目录。

**可选（推荐）**：放一份 `libmpv-2.dll` 到程序目录（或用 `MSS_LIBMPV` 指定路径）即可获得精确的
音频主时钟；没有它时会自动用 waveOut 或退到 ffplay + 墙钟，不影响其它功能。
只想安装播放器本身时：`mpv.exe` 放 `D:\Program Files\mpv\` 并把它加进 `PATH` 即可。

```powershell
python media_subtitle_studio.py
```

将文件拖入窗口，或执行 `python media_subtitle_studio.py "D:\media\film.mkv"` 直接打开该文件。

程序会优先复用系统 Python 的 OpenAI Whisper 与已有权重，其次使用当前环境的 Whisper 后端。
默认模型为 `medium`；会自动检查 `WHISPER_MODEL_DIR`、Buzz 的本地模型缓存和 OpenAI Whisper
默认缓存目录。当前机器在 Buzz 缓存中已有 `tiny.en.pt`、`medium.pt`、`large-v3.pt`，无需重复下载。
如果在其他机器上没有这些权重，且尚未安装识别后端，可在程序使用的 Python 环境运行：

```powershell
python -m pip install faster-whisper
```

未缓存的模型首次使用需要联网下载模型文件；下载后由本机推理，音频不会发送给翻译 API。
AI 翻译会将字幕文本发送到 `api_settings.json` 配置的模型服务。

## CLI

```powershell
# 检查媒体轨道和同目录字幕
python media_subtitle_studio.py inspect "D:\media\film.mkv"

# 识别第 2 条音轨（编号从 0 开始），默认生成 film_recognized.srt
python media_subtitle_studio.py transcribe "D:\media\film.mkv" --audio-track 1 --model small

# 自动识别源语言并翻译为繁体中文
python media_subtitle_studio.py translate "D:\media\film.en.srt" --target "中文（繁體）"

# 指定 api_settings.json 中的模型名称翻译
python media_subtitle_studio.py translate "D:\media\film.en.srt" --target "中文（简体）" --model "DeepSeek-v4.1-flash"

# 翻译并生成原文+译文双语 ASS
python media_subtitle_studio.py translate "D:\media\film.en.srt" --target "中文（简体）" --format ass

# 将多份字幕重新封装为独立轨道，不烧录画面；默认生成 film_subtitled.mkv
python media_subtitle_studio.py mux "D:\media\film.mkv" "D:\media\film.scjp.ass" "D:\media\film.tcjp.ass"
```

也可用 `-o` 指定输出路径。MP4/MOV 适合 SRT 转 `mov_text`，不支持 ASS 字幕流；双语 ASS
请封装到 MKV。PGS/VobSub 等图像字幕无法直接解析成文本，需先另行 OCR。

## 说明

- 源语言选「自动检测」时，翻译请求会要求模型自行判断输入语言（`AUTO_SOURCE_LANG`）。
- 分组翻译是「省请求」模式，逐条是「稳对齐」模式；字幕行很短或需要精确断句时建议逐条。
- 取消翻译只影响本次任务，已载入的字幕与原文不会被改动。
- 关闭窗口会释放播放器与 `ffplay` 预览进程；识别 / 翻译线程为守护线程，退出即结束。
- 字幕解析 / 生成 / 翻译内核已内嵌（原 `S_subtitles.py` 中本程序用到的部分），因此只需
  `media_subtitle_studio.py` + `api_settings.json` 两个文件即可运行，无需其它项目文件。
- 内嵌内核通过 `types.SimpleNamespace` 暴露为 `subtitles`，保留了原先 `subtitles.xxx`
  的写法，方便与旧代码逐行对照；如需直接调用，也可用本文件内的同名模块级函数 / 类
  （`SubtitleParser`、`SubtitleGenerator`、`detect_format`、`translate_entries_concurrent` 等）。

## 变更记录

- **2026-09-27 播放跟随所选音轨 + 字幕来源支持导入文件**：
  - 播放不再固定用第一条音轨：`create_audio_clock()` / `MpvAudioClock` / `WaveOutAudioClock`
    都接受音频流序号，`_selected_audio_ordinal()` 统一把下拉框位置钳到有效范围；
    播放中切换音轨会重锚墙钟并重建音频时钟，日志给出 `已切换播放音轨：音轨 N`。
  - 「字幕来源」列表末尾固定增加 `导入外部字幕文件…`：选中即弹出字幕选择对话框，
    **默认目录与媒体文件所在目录一致**（`_default_subtitle_dir()`，无媒体时退回系统记忆目录），
    确定后立即载入并选中该外置字幕，取消则回退到原选项（全部索引钳制都排除占位项）。
  - 验收：双音轨素材实测（`ffmpeg -map 0:a:0/1` → 440/880Hz，mpv `aid` = 1/2，
    waveOut 命令与 ffplay `-ast` 参数正确）；GUI 29 项断言全通过，
    含内嵌字幕 + 同目录字幕 + 导入项共存时的顺序与索引、取消回退、无音轨媒体兜底。
- **2026-09-27 音画同步重做（音频主时钟）**：
  - 之前画面按墙钟推进、音频由独立的 `ffplay` 进程播放，只能用一个固定偏移去猜音频启动时间。
    实测 `ffplay` 从 seek 到出声的启动延迟在 **0.48 / 5.29 / 3.74 秒**（`-ss 0/5/20`）之间剧烈波动，
    而解码侧只要 46–57ms —— 固定偏移无法对齐，这是「跳转后仍然不同步」的根因。
  - 改为**音频主时钟**：新增 `MpvAudioClock`（进程内 libmpv，读 `audio-pts`）、
    `WaveOutAudioClock`（ffmpeg 解码 PCM → ctypes waveOut，用缓冲区播完事件重锚时钟）与
    `create_audio_clock()` 回退链；`_play_video_tick` 改为按音频位置调度画面，
    音频未开始前保持当前帧等待，超时 2 秒自动回退墙钟。
  - 「同步」微调默认值由 `0.15` 改为 **0**（原来那 0.15s 只是猜出来的补偿，现在会人为制造 150ms 不同步）。
  - 顺手修掉 waveOut 兜底实现的错误：`waveOutPrepareHeader` 之后把 `dwFlags` 清零会抹掉
    `WHDR_PREPARED` 标志，导致 `waveOutWrite` 报错 34；改用 `counted` 标记累计已播字节。
  - 验收：mpv 时钟起播 0.25–0.6s 可用、10 秒漂移 **0ms**；GUI 播放 6 秒画面与音频偏差
    均值 +24ms（极差 41ms，一帧以内）、≈29fps；播放中 seek 到 15s 后偏差仍在 30ms 内；
    连续 10 次拖动跳转时钟不丢；无音轨文件自动走墙钟正常播放；关闭 22ms、无残留进程。

- **2026-09-27 清理旧程序**：三个旧程序（`S_subtitles.py` / `subtitle_cli.py` / `subtitle_auto.bat`）
  及备份包 `_deprecated_subtitle_scripts_20260926.zip`、旧版整合包备份 `_deprecated_allinone_20260927.zip`
  已全部删除；本文件本就自包含，不受影响。
- **2026-09-27 合一程序重建（三标签页，去掉媒体工作台）**：删除了旧的
  `Subtitle_Studio_All_in_One.py`（它把媒体工作台整块也合了进去，界面混杂），
  改为以三个旧程序为源重新拼装：
  - 新文件只有一套界面：**三标签页**（格式转换 / AI 翻译 + 转换 / Whisper 识别 + 翻译 + 转换），
    深色科技风，标签页内设置区可滚动、操作栏固定在底部；
  - 媒体部分只保留第三页用得到的 Whisper + ffmpeg 辅助函数，不再有视频预览 / 音轨列表 / 字幕轨封装；
  - 命令行与旧 `subtitle_cli.py` 完全兼容（`translate` / `convert` / `models` / `config-path`），
    所以 `S_ASMR_system.bat` 无需再改；`--help` 现在能看到全部子命令。
  - 三个旧程序当时仅从备份 zip 还原保底，随后（同日）确认无用并删除。
- **2026-09-26 工作区整合（统一入口）**：`S_ASMR_system.bat` 的字幕自动处理步骤已改为调用
  `Subtitle_Studio_All_in_One.py`，行为与文件命名保持不变（`<名>_zh.srt` → `<名>_zh.lrc`）。
  本文件（`media_subtitle_studio.py`）保持独立、不受影响。
- **2026-09-26 解除对 `S_subtitles.py` 的依赖（自包含单文件）**：
  - 把本程序实际用到的部分内嵌进 `media_subtitle_studio.py`：`api_settings.json` 读取、
    多编码文本读取（utf-8-sig/utf-8/gbk/gb18030/big5/shift-jis/euc-kr/cp949/utf-16…）、
    格式检测（SRT/VTT/ASS/SSA/SUB/SMI/LRC + 内容嗅探）、六种解析器、SRT/VTT/ASS 生成器，
    以及并发翻译内核（单条 / 整段、失败重试、4xx 超限自动减半、token 统计、取消语义）。
  - 移除 `import S_subtitles as subtitles`；调用处通过内嵌的兼容命名空间保持不变。
  - 等价性验证：同一批样例（srt/vtt/ass/ssa/smi/sub/lrc/多编码/无扩展名）与原
    `S_subtitles.py` 逐项对比，格式检测、解析结果、生成文本、翻译提示词、打桩调度
    （逐条 / 整段 / 取消 / token 统计）完全一致；GUI 载入 SRT/ASS 后按样式渲染、
    导出三种格式、DPI 重建均正常。
  - 顺带清理：模块底部残留的顶层 `enable_dpi_awareness()` 调用移入 `main()`，
    导入本模块不再产生副作用（`SubtitleStudio.__init__` 仍会在创建窗口前调用一次）。

- **2026-09-26 播放与字幕渲染修复**（`media_subtitle_studio.py`）：
  - 播放改为**墙钟驱动 + 到期时刻调度**（每帧只跳一次定时器、落后超过约 1.8 帧才丢帧），
    播放期间把系统计时器精度提升到 1ms；实测 30fps 素材稳定 30fps、实时率约 99%，
    长时间播放不再累积漂移，跳转后音画重新对齐。
  - 音频改用 `ffplay -vn`（只解码音频、去掉 subtitles 滤镜，降低 CPU 争用），
    跳转时重启音频并重新锚定播放时钟；新增「同步」微调（默认 0.15s）补偿音频启动延迟。
  - 字幕预览改为**按文件格式渲染**：ASS 读取样式表（字体 / 字号 / 颜色 / 描边 / 对齐 / 边距）
    与 `\an`、`\b`、`\i`、`\c`、`\N` 等覆盖标签，矢量绘图条目不按文字渲染；
    SRT/VTT 支持 `<b>`、`<i>`、`<u>`、`<font color>`；拉丁字体缺中文字形时自动回退微软雅黑；
    字幕图层带缓存，播放时开销极低。
  - 修正 ASS `&HBBGGRR` 颜色字节序，以及 ASS 字幕文本开头多出的字段分隔符
    （预览与导出均已修正）。

- **2026-09-26 单文件版界面重写（深色科技风）**：`Subtitle_Studio_All_in_One.py` 的两套 GUI
  ——「① 字幕工具箱（格式转换 + AI 翻译）」与「② 字幕工作台（识别 / 翻译 / 导出与封装）」
  ——全部改用 **customtkinter** 重写布局，并用 **ttkbootstrap (darkly)** 统一残留 ttk 控件
  （字幕表格、微调框、进度条）。新增卡片式分区、荧光青强调色、窗口拖拽载入与界面自检。
  - 依赖：`python -m pip install customtkinter ttkbootstrap`（缺 customtkinter 时 GUI 会给出
    明确安装提示，`convert` / `models` / `config-path` 等 CLI 子命令仍可正常使用）。
  - 自检：`SUBTITLE_UI_SELFTEST=1 python Subtitle_Studio_All_in_One.py`，会构建两套界面、
    刷新后立即关闭并打印 `OK / FAIL`，用于确认依赖与显示环境正常。
  - 维护提示：新界面代码集中在文件末尾的「深色科技风界面重构区」；文件中部保留的旧版类已
    统一改名为 `*Legacy`（运行时被覆盖，仅作回滚参考），请勿在旧段里修改界面。
  - 维护提示：必须先创建 Tk 根窗口、再调用 `ui_init_theme()`。若顺序颠倒，ttkbootstrap 会
    抢先创建一个隐藏根窗口，导致 tk 变量与 ttk 样式绑定到错误的解释器（表现为下拉框 /
    输入框不刷新、表格变白、进度条失色）。

- **2026-09 界面重写**：高 DPI 感知与运行时 DPI 变化自适应；改为「左侧预览 + 右侧四页签」
  布局；翻译页签集中模型 / 并发 / 分组 / 进度 / 取消 / 日志；支持媒体 + 字幕一起拖入、
  单独拖入字幕替换；新增上一句 / 下一句与空格播放暂停；导出页签显示预计输出文件名。