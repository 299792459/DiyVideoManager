# Local Video Manager (Windows)

一个用于管理本地视频文件的 Web 应用，支持：

1. 统计视频观看次数
2. 手动打标签 + 按标签筛选
3. 根据文件名关键词统计并自动生成标签
4. 文件名意图搜索（中文同义词扩展，类似轻量 RAG 检索体验）
5. AI 提问式搜索（调用大模型根据语义挑选视频，可接 OpenAI 兼容接口/龙虾网关）
6. 多维排序（修改时间、观看次数、时长、大小、热门度）
7. 封面管理（扫描不生成封面；单独「刷新封面」抽默认帧 + 手动上传）
8. 视频网站风格的基础数据架构（视频表、标签表、关系表）
9. 所有数据目录可自定义（数据库、封面等可放到 D/E 盘）
10. AI 数据导出（JSON/JSONL，便于喂给模型、龙虾或其他 RAG 流程）

## 技术栈

- Python 3.10+
- Flask
- SQLite
- ffmpeg + ffprobe（用于获取时长、抽封面）

## 启动

```bash
cd local-video-manager
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

浏览器打开：<http://127.0.0.1:5050>

## 首次使用建议

1. 在页面顶部设置 `数据目录`（例如 `D:\video-manager-data`）。
2. 设置 `视频目录`（可多个，用分号分隔）。
3. 点击“保存配置”。
4. 点击“扫描视频”建立索引（**仅元数据，不生成封面**）。
5. 点击「刷新封面（仅缺封面）」或卡片上「刷新封面」生成默认封面。
6. 点击“根据文件名自动打标签”生成标签。
7. 在 AI 配置中填写 Base URL、Model、API Key，勾选启用后可使用“AI搜索”。

## 日志

- 运行日志写入项目目录：`local-video-manager.log`（与 `app.py` 同级）。
- 关键操作（扫描、刷新封面、配置保存、列表查询、AI 搜索、播放计数、标签等）会记录。

## 封面刷新 API

- **批量**：`POST /api/covers/refresh`，JSON：`{"only_missing": true}`（仅缺封面）或 `false`（全部重生成）。
- **单条**：`POST /api/videos/<id>/cover/refresh`

## AI 搜索与数据对接

- **AI搜索接口**：`POST /api/ai/search`
  - 入参：`{"question":"...","top_k":30}`
  - 出参：返回匹配视频列表 + 来源（`llm`/`fallback`）+ 原因说明。
- **导出数据接口**：`GET /api/ai/export?format=jsonl`
  - 可直接导出 JSONL，适合接入外部大模型检索或 RAG 建库。
- **兼容方式**：采用 OpenAI Chat Completions 兼容协议（`{base_url}/chat/completions`）。
  - 你可填官方地址，也可填公司网关或“龙虾”兼容网关地址。

## 注意

- 默认封面规则：时长 ≥10s 为「最后 60 秒内第一帧」；时长 &lt;10s 为「接近最后一帧」。
- **ffmpeg / ffprobe 为必填**（扫描时长、刷新封面）。程序会依次查找：环境变量 `FFMPEG_PATH` / `FFPROBE_PATH`、系统 **PATH**、常见目录（如 `C:\Program Files\ffmpeg\bin`、WinGet 包目录等）。
- 若仍报「未找到 ffmpeg」：在 **管理员 PowerShell** 执行  
  `winget install --id Gyan.FFmpeg -e`  
  安装完成后**重启终端与本程序**，或将解压后的 `bin` 目录加入系统环境变量 **PATH**。
- 当前意图搜索实现为“同义词扩展 + 字符重叠匹配 + 标签融合检索”，可继续升级为向量模型版。
