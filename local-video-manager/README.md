# Local Video Manager（本地视频管理）

基于 Flask + SQLite 的本地视频库 Web 界面，用于浏览、标签、搜索、封面与统计。**数据目录可自定义**，不强制占用 C 盘。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **视频 / 设置分栏** | 顶部「视频」「设置」切换；视频页专注列表与搜索，设置页集中路径、扫描、AI 与系统统计。 |
| **紧凑搜索区** | 「本地筛选」与「AI 提问」双栏并排（窄屏自动单列）；关键词/AI 输入各占模块内一行，分页与卡片宽度独立为「分页与外观」模块。 |
| **分页** | 列表支持 `page` / `per_page`；每页条数可选（12～96）。**浏览模式**由服务端分页；**AI 搜索**结果在前端分页（不重复调模型）。 |
| **卡片大小** | 滑块调节 `--grid-card-min`（约 160～480px），拖动即可改变一屏列数；偏好存于浏览器 `localStorage`（`vm_grid_card_min`、`vm_per_page`）。 |
| **观看次数** | 播放时递增计数。 |
| **标签** | 手动打标签；按标签筛选；可按文件名统计自动生成标签。 |
| **意图搜索** | 本地同义词扩展 + 字符重叠（非向量模型）。 |
| **AI 搜索** | OpenAI 兼容 Chat Completions，可选启用；失败时回退本地匹配。 |
| **封面** | 扫描**不**生成封面；批量「跳过已有」或「强制全部」；单条可普通刷新（有则跳过）或强刷。短于 10 秒默认接近**最后一帧**；否则「最后 60 秒内第一帧」。支持手动上传。 |
| **回收站** | 删除为软删除：字段 `recycled_at`（**非标签**）。列表勾选「显示回收站」仅看回收站条目；扫描时若库中路径已不存在则自动移入回收站；设置中可**清空回收站**并删除磁盘文件。 |
| **外部播放 / 定位** | 可选配置 `player.external_path`，卡片「外部播放」；「打开位置」在系统文件管理器中选中该文件。 |
| **标签语义（本地）** | 可选启用 `intent`：依赖 **fastembed** + 小尺寸 ONNX 模型（默认 `BAAI/bge-small-zh-v1.5`），仅对**标签名字符串**建向量，与原有字符级意图分加权融合；不占 GPU，首次使用会下载模型（约百余 MB）。 |
| **系统统计** | 轻量汇总（库条数、磁盘、`covers` 体积等）；**性能抽样**需手动触发（CPU/内存 + 随机视频 stat/4KB 读）。 |
| **日志** | `local-video-manager.log`（与 `app.py` 同级）。 |

---

## 环境要求

- Python 3.10+
- **ffmpeg / ffprobe**（时长、默认封面；程序会尝试 PATH、常见安装目录及环境变量 `FFMPEG_PATH` / `FFPROBE_PATH`）
- 依赖见 `requirements.txt`（含 `Flask`、`psutil` 等）

```bash
cd local-video-manager
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python app.py
```

浏览器访问：<http://127.0.0.1:5050>

---

## Git 与克隆到新电脑

- 仓库根目录与子目录均有 **`.gitignore`**，默认**不跟踪**：
  - **`config.json`**（路径与密钥）、**`data/`**、**`*.db`**、**`*.log`**（含 `local-video-manager.log`）；
  - **`.idea/`**（JetBrains：含 **`vcs.xml`**、`modules.xml`、`*.iml` 等）、**`.vscode/`**；
  - Python 缓存、**`.venv/`** 等。  
  若这些文件曾被 `git add` 过，需执行 **`git rm --cached`** 从版本库移除（本地文件保留），否则仅加 `.gitignore` 不会自动从远程消失。
- 仓库内提供 **`config.json.example`** 作为模板；克隆后可直接复制为 `config.json` 再改，或**首次运行 `python app.py`** 让程序自动生成默认 `config.json`。
- 若你曾经把 `config.json` / `data/` 提交进过 Git，需要从索引移除（保留本地文件）：  
  `git rm -r --cached config.json data/`  
  然后提交；**勿**把含真实路径的配置再推送到远程。

---

## 首次使用

1. 打开 **「设置」**，填写 **数据目录**（建议非 C 盘）与 **视频目录**（多个用英文分号 `;` 分隔）。  
2. 点击 **保存配置**。  
3. **扫描视频**（仅写入索引与时长，**不**生成封面）。  
4. 回到 **「视频」**，按需 **批量刷新封面（跳过已有）**；单条用 **刷新封面**（有封面则跳过）或 **强刷封面**。  
5. 可选：**根据文件名自动打标签**；配置 AI 后使用 **AI 搜索**。

---

## API 摘要（本地）

| 接口 | 说明 |
|------|------|
| `GET/POST /api/config` | 配置：`data_dir`、`library_dirs`、`llm`、`stats`、**`player.external_path`**、**`intent`**（`enabled`、`model`、`lexical_blend` 0～1、`min_semantic` 0～1）等。 |
| `GET /api/intent/status?probe=1` | 是否安装 fastembed；`probe=1` 时尝试加载当前 `intent.model`（可能触发下载）。 |
| `POST /api/scan` | 扫描入库（不生成封面）；结束后将**仍有效但路径已不存在**的活跃条目移入回收站，响应 **`moved_invalid_to_recycle`**。 |
| `GET /api/videos` | 列表；参数含 **`recycled=1`**（仅回收站）、`search`、`sort`、`order`、**`page`**、**`per_page`**（6～200）；**标签多选**：重复参数 **`tags=a&tags=b`**（**AND**：同时包含所选标签），兼容旧参数 **`tag=单标签`**；返回 **`recycled_view`**、**`tag_filters`** 等。 |
| `POST /api/videos/<id>/recycle` | 软删除（移入回收站）。 |
| `POST /api/videos/<id>/restore` | 从回收站恢复。 |
| `POST /api/videos/<id>/open-external` | 使用配置的 `player.external_path` 打开视频。 |
| `POST /api/videos/<id>/reveal` | 在系统文件管理器中定位文件。 |
| `POST /api/recycle/purge` | 清空回收站：删除磁盘上的视频与封面文件，并删除对应库记录。 |
| `POST /api/covers/refresh` | 批量刷新封面：`{"only_missing": true}` 只处理**尚无封面**的视频（默认）；`only_missing: false` **强制**为全部非回收站视频重生成。 |
| `POST /api/videos/<id>/cover/refresh` | 单条刷新；JSON 体 **`force`**（默认 `false`）：已有封面文件则**跳过**并返回 **`skipped: true`**；**`force: true`** 强制重生成。成功时返回 **`cover_url`**。 |
| `POST /api/ai/search` | AI 检索；与页面配合时结果在前端分页。 |
| `GET /api/stats/summary` | 库与磁盘轻量汇总。 |
| `POST /api/stats/sample` | 按需性能抽样（需 `psutil` 时测 CPU/内存）。 |
| `GET /api/ai/export?format=jsonl` | 导出 JSONL 供外部 RAG / 模型使用。 |
| `GET /api/tags/export` | 下载 `tags_export.jsonl`：每行 `i`（视频 ID）、`n`（文件名）、`p`（完整路径）、`t`（标签名数组），UTF-8、紧凑 JSON。 |
| `GET /api/tags/export-readme` | 下载给大模型阅读的格式说明（与 `docs/TAGS_LLM_README.md` 一致）。 |
| `POST /api/tags/import-preview` | 导入前预览：与 `import` 相同正文与 `strict_path`，不写库；返回 `would_apply`、`samples`（旧/新标签示例）、各类跳过计数与解析错误。 |
| `POST /api/tags/import` | 导入大模型处理后的 JSONL：`multipart/form-data` 字段 `file`，或 **raw body** 直接贴全文。可选 `?strict_path=1`：行内 `p` 与库不一致时跳过。返回 `updated`、`skipped_*`、`errors`。 |

**标签批量整理**：建议先 **备份数据目录** 下的 `video_manager.db`。导出 → 外部重写 `t` → 再导入；仅文件中出现的 `i` 会被更新。若视频曾移动/重扫导致 ID 变化，需 **重新导出** 再交给模型。

---

## 注意事项

### 路径与配置

- **`config.json`** 与数据库、封面均在 **`data_dir`** 下（由你指定）；移动项目目录后，若使用**绝对路径**的 `library_dirs`，请检查是否仍有效。  
- 视频目录保存后务必点 **保存配置**，否则 `library_dirs` 为空会导致扫描不到文件。

### ffmpeg

- 若报 `missing executable: ffmpeg` 或未找到工具：安装 FFmpeg 并将 `bin` 加入系统 **PATH**，或设置环境变量 **`FFMPEG_PATH`** / **`FFPROBE_PATH`** 指向完整 `exe` 路径，**重启终端与本程序**。  
- Windows 可用：`winget install --id Gyan.FFmpeg -e`（以官方文档为准）。

### 扫描与封面

- **扫描**与**刷新封面**分离：大批量扫描后再统一刷新封面，避免一次请求耗时过长。  
- **批量刷新封面（跳过已有）**：只给当前**没有封面**的条目生成，已有封面不重复抽帧。  
- **批量强制刷新全部**：无论是否已有封面都会重生成；单条可在卡片上使用 **强刷封面**，或调用接口时传 **`force: true`**。若曾手动上传封面，强制刷新会按默认规则重新生成并可能覆盖记录。

### 分页与 AI

- **普通查询**：分页由 **服务端**按当前筛选/排序结果切片。  
- **AI 搜索**：一次请求返回当前模型/回退下的**全部匹配**（上限受 `top_k` 等约束），**翻页仅在前端切片**，切换回「查询」即回到服务端分页。  
- 扫描或自动打标签成功后，列表会 **回到第 1 页** 并刷新。

### 卡片大小与每页条数

- 存在浏览器 **localStorage** 中；清理站点数据会丢失，需重新调节。  
- 卡片过窄/过多列可能影响文件名与按钮可读性，请按屏幕自行平衡。

### 性能统计

- **`GET /api/stats/summary`** 开销小，可频繁调用。  
- **`POST /api/stats/sample`** 会随机访问若干视频文件的元数据与前几 KB 读取，**仅在点击/开启抽样时执行**，勿在脚本里高频轮询。  
- 未安装 **`psutil`** 时，抽样结果中的 CPU/内存可能不可用，需 `pip install psutil`。

### 安全与隐私

- 服务默认监听 **127.0.0.1**，仅本机访问；若改为 `0.0.0.0` 暴露局域网，请注意鉴权与防火墙。  
- **API Key** 等敏感信息勿提交到公共仓库；日志中保存配置时会对 Key 打码，但仍勿泄露 `config.json`。

### 开发与调试

- Flask `debug=True` 时修改代码会重载；生产环境请关闭 debug 并使用正式 WSGI 服务器。

---

## 项目结构（主要文件）

```
local-video-manager/
  .gitignore             # 忽略本地数据、日志、配置等
  app.py                 # Flask 应用与 API
  config.json.example    # 配置模板（可提交）
  config.json            # 本机配置（默认被 gitignore，不提交）
  requirements.txt
  templates/index.html   # 单页：视频 / 设置视图
  static/style.css
  data/                  # 默认数据目录（gitignore，含库与封面）
  local-video-manager.log # 日志（gitignore，运行后生成）
```

---

## 更新记录（功能同步说明）

以下能力已在界面与后端实现，并反映于本文档：

- 视频页与设置页分离；紧凑「搜索与列表」单面板布局。  
- 列表分页（`page` / `per_page`）与每页条数选择；卡片宽度滑块与 `localStorage`。  
- 扫描不生成封面；独立刷新封面及日志。  
- FFmpeg 多路径解析；短视频封面规则。  
- 系统统计与按需性能抽样；`psutil` 可选。  
- AI 搜索与 JSONL 导出；配置项 `stats`、`llm`。

若升级依赖或 Python 版本，请重新执行 `pip install -r requirements.txt` 并阅读各包发行说明。
