# AI Agent 工作交接（压缩版）

> 目的：把与用户对话中形成的**强制约定**、**架构决策**和**本仓库要点**写在一处，便于换其他 Agent 继续开发。  
> 项目路径：`DiyVideoManager/local-video-manager`（Flask + SQLite 本地视频库 Web）。

---

## 一、与用户协作的强制 / 优先约定

1. **语言**：用户要求时用 **中文** 回复。
2. **执行**：在真实环境里**自己跑命令、改代码**；不要只给「请你运行」的说明就结束；遇到错误要换思路重试。
3. **代码风格**：改动紧贴需求，避免无关大重构；与现有文件命名/风格一致；无必要不写长文档或堆砌注释。
4. **引用代码**：说明实现时用仓库内**真实路径 + 行号** 的代码引用格式（便于一键跳转）。
5. **主文件瘦身**：**不要把爬虫/大块业务逻辑堆在 `app.py`**。独立逻辑放 `crawler/`、`lvm/` 等包，主程序只做注册与依赖注入。
6. **启动方式兼容**：用 `python app.py` 启动时**不能**依赖 `import app`（模块名是 `__main__`）。跨模块回调请用 **函数注入**（如 `CrawlerFlaskDeps`）或包内自包含实现。
7. **工作区规则（若同时在 Pacvue `commerceapi-3p` 仓库）**：长时间对话可把压缩纪要写到 **`<git用户名>-progress.md`**，避免上下文爆炸；本 handoff 文件侧重 **local-video-manager**。

---

## 二、本仓库架构要点

| 区域 | 说明 |
|------|------|
| `app.py` | Flask 路由、与 UI 直接相关的胶水；复杂逻辑尽量迁出。 |
| `lvm/` | 配置、数据库、媒体/封面、标签导入、搜索序列化等可复用模块（若与 `app.py` 并存，以 **`app.py` 实际引用为准**）。 |
| `crawler/` | 爬虫流水线：**`mock_source`**（可换真实解析）、**`pipeline`**、**`cover_io`**、**`flask_routes`**（`/api/crawler/*`）。通过 **`register_crawler_routes(app, CrawlerFlaskDeps(...))`** 注册。 |
| `templates/index.html` | 单页 HTML 骨架（纯结构，无内联 JS）。脚本入口：`<script type="module" src="/static/js/main.js">`。 |
| `static/style.css` | 全局样式（深色主题、Grid/Flex 布局、CSS 变量）。 |
| `static/js/` | **ES Modules**，按 `core / ui / video / tags / settings` 分层。详见 **`docs/FRONTEND_ARCHITECTURE.md`**。 |
| `config.json` + `data_dir` | 数据目录下放 `video_manager.db`、`covers/`、`crawler/input|output|cache/`。 |

---

## 三、业务与数据（易错点）

- **标签**：`tags` 全局表；`video_tags` 关联。改关联后需维护 **`videos.search_text`**（与文件名+标签名相关检索）；单条删除/重命名/导入等路径里已配合 **`_rebuild_search_text_for_video`** 或整批替换逻辑。
- **列表 API**：`GET /api/videos` 每条含 **`tags`**（名称数组）与 **`tag_items`**（`{id,name}`），供前端**逐条改/删**标签。列表 SQL 使用 **`json_group_array`** 子查询（不可用 `GROUP_CONCAT(... ORDER BY ...)`，Windows 自带 SQLite 3.43 不支持该语法）。
- **单视频标签**：`DELETE /api/videos/<vid>/tags/<tid>`；**改名/换关联**用 **`PATCH`**（指向全局已有名或新建）；**清空**用 **`POST .../tags/clear`**。
- **全局标签管理**：`GET /api/tags/catalog`；`PATCH/DELETE /api/tags/<id>`；删除标签会级联 `video_tags` 并需重算受影响视频的 `search_text`。
- **爬虫**：输入输出默认在 **`data_dir/crawler/input|output`**；步骤 1 曾要求可 **mock**，再接真实站点解析；导入结果可写回标签+封面（见 `docs/CRAWLER_README.md`）。

---

## 四、给其他 Agent 的接手顺序建议

1. 读 **`README.md`**（API、环境、Git 忽略项）。  
2. 读本文 + **`docs/FRONTEND_ARCHITECTURE.md`**（前端模块、依赖关系、改动指南）。  
3. 读 **`docs/CRAWLER_README.md`**（若动爬虫）。  
4. 改 UI 时同步看 **`static/js/`**（ES 模块）与 **`static/style.css`**；改哪个功能就改对应模块，入口事件绑定在 `main.js`。  
5. 新增 HTTP 接口时：保持与现有 JSON 风格一致；敏感配置不要写进仓库。

---

## 五、版本说明

- 本文档为 **对话与规则的人工压缩**，不替代代码；若与源码冲突，**以源码为准**。  
- 更新时：**只追加关键决策**，避免冗长聊天记录粘贴。
