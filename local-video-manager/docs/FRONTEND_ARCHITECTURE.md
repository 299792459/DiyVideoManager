# 前端架构与模块文档

> 面向接手的 **AI Agent 或人类开发者**。
> 路径：`DiyVideoManager/local-video-manager`

---

## 一、技术栈

| 项 | 选型 |
|----|------|
| 模板 | Flask Jinja2 → `templates/index.html`（纯 HTML，无前端构建工具） |
| 脚本 | **原生 ES Modules**（`<script type="module">`，无 bundler） |
| 样式 | 单文件 `static/style.css`（CSS 变量 + Grid + Flex） |
| 浏览器要求 | 任何支持 ES Modules 的现代浏览器（Chrome 61+、Firefox 60+、Safari 11+） |

---

## 二、文件结构

```
templates/
  index.html          ← 纯 HTML 骨架，只有结构，无内联 JS

static/
  style.css           ← 全局样式（深色主题）
  js/
    main.js           ← ★ 入口：绑定 DOM 事件 + init()
    core/
      state.js        ← 全局可变单例 state（currentPage、selectedTagFilters 等）
      constants.js    ← localStorage 键名常量
      format.js       ← 纯函数：fmtSize、fmtDuration、fmtTime、escHtml
    ui/
      status.js       ← 三处状态栏（videoStatus / settingsStatus / tagManageStatus）
      nav.js          ← showView()（视图切换：视频 / 标签管理 / 设置）
      video-grid.js   ← renderVideos()（卡片 DOM 生成）、applyCardSize、closeAllCardMoreMenus
    video/
      browse.js       ← queryVideos()（GET /api/videos + 分页）、scanVideos、refreshCovers
      ai.js           ← aiSearchVideos()、renderAiPage()（AI 模式分页）
      ops.js          ← 单条视频操作：play、addTag、editTag、removeTag、clearTags、
                         uploadCover、refreshOneCover、recycle、restore、reveal、externalPlay、
                         purgeRecycleBin、exportAiData、autoGenerateTags
    tags/
      filter.js       ← 标签筛选条：renderTagFilterBar、saveTagFiltersToStorage
      manage.js       ← 标签管理页：loadTagsCatalog、renderTagManageTable、
                         renameTagGlobal、deleteTagGlobal
    settings/
      config.js       ← loadConfig / saveConfig（→ POST /api/config）
      stats.js        ← 统计汇总 & 性能抽样
      workflows.js    ← 标签导入、爬虫运行/导入、意图模型探测等长流程
```

---

## 三、模块依赖关系（简图）

```
main.js
 ├── core/*            所有模块均可引用，无副作用
 ├── ui/status.js      被 video/*、tags/*、settings/* 引用
 ├── ui/nav.js         ← 引用 settings/stats + tags/manage
 ├── ui/video-grid.js  ← 引用 core/*
 ├── video/browse.js   ← 引用 ui/video-grid、tags/filter、ui/status、settings/stats
 ├── video/ai.js       ← 引用 ui/video-grid、ui/status
 ├── video/ops.js      ← 引用 video/browse、video/ai、ui/status、ui/nav、settings/stats
 ├── tags/filter.js    ← 引用 core/*
 ├── tags/manage.js    ← 引用 video/browse、tags/filter、ui/status
 ├── settings/config.js← 引用 core/state、ui/status
 ├── settings/stats.js ← 引用 core/format（无循环）
 └── settings/workflows.js ← 引用 video/browse、ui/status
```

**无循环依赖**。`state.js` 是唯一的共享可变单例，所有模块通过 `import { state }` 读写。

---

## 四、页面视图

`index.html` 是一个多视图 SPA（无路由库，用 `showView()` 切换 `display:none`）。

| 视图 | `id` | 说明 |
|------|------|------|
| **视频** | `viewVideos` | 默认显示。搜索栏（关键词 + 标签下拉 AND 筛选 + 排序）、AI 搜索栏、分页工具、卡片网格 |
| **标签管理** | `viewTags` | 全局标签列表表格，支持重命名/删除 |
| **设置** | `viewSettings` | 路径配置、爬虫、标签导入导出、AI 模型、向量模型、统计 |

---

## 五、视频卡片 UI 要点

每张卡片由 `ui/video-grid.js → renderVideos()` 生成，结构如下：

```
article.card
  div.cover            ← 封面图 / 无封面占位
  div.content
    h3                 ← 文件名（溢出省略）
    p.meta × 2         ← 观看次数、时长、大小、修改时间
    div.tags-row-compact ← 标签 pill（单行横向滚动，点击=筛选切换）
    div.actions-main
      button[播放]
      div.card-more-wrap
        button[更多 ▾]     ← 触发浮层
        div.card-more-pop  ← 绝对定位浮层（标签编辑 + 文件 + 封面 + 删除/恢复）
```

### 浮层（card-more-pop）

- **不使用 `<details>`**，改为 JS 手动切换 `.hidden`。
- 点击页面其他区域或按 Esc 关闭（`closeAllCardMoreMenus()`）。
- 浮层内分区：**标签**（逐条改名/移除 + 加标签/清标签）→ **文件** → **封面** → **条目**。
- 浮层 `position: absolute; z-index: 80`，不会撑开卡片高度。

### 标签筛选

- 点击卡片上的标签 pill → 加入/移出 `state.selectedTagFilters`（AND 逻辑）→ 重新查询。
- 搜索栏上方的 `#tagFilterBar` 展示已选标签芯片，可逐个移除或清空。
- 持久化到 `localStorage(vm_tag_filters)`。

---

## 六、数据流

### 浏览模式（browse）

```
用户操作 → queryVideos(page)
  → GET /api/videos?search=&sort=&order=&page=&per_page=&recycled=&tags=
  → 后端返回 { videos, tags, page, total, total_pages }
  → renderVideos(videos)  更新卡片
  → renderTagFilterBar()  更新筛选条
  → updatePaginationUI()  更新分页
```

### AI 模式

```
aiSearchVideos()
  → POST /api/ai/search { question, top_k }
  → 全量结果存入 state.aiFullVideos
  → 前端分页：renderAiPage() 切片渲染
```

模式切换靠 `state.listMode`（`"browse"` / `"ai"`），翻页、操作后刷新的策略不同。

---

## 七、样式约定（style.css）

| CSS 变量 | 用途 |
|----------|------|
| `--grid-card-min` | 卡片最小宽度（用户可通过滑块 160–480px 调整） |

### 关键类名

| 类名 | 说明 |
|------|------|
| `.panel` / `.panel-compact` | 搜索区、设置区面板 |
| `.grid` | `display: grid; auto-fill` 卡片网格 |
| `.card` | 视频卡片容器，`overflow: visible`（浮层需要） |
| `.tags-row-compact` | 标签行：`flex-wrap: nowrap; overflow-x: auto`（单行横滚） |
| `.card-more-wrap` / `.card-more-pop` | 浮层定位锚点 / 浮层面板 |
| `.tag-filter-active` | 当前被选中的筛选标签高亮 |

---

## 八、localStorage 键

| 键 | 值类型 | 说明 |
|----|--------|------|
| `vm_grid_card_min` | string(number) | 卡片宽度 px |
| `vm_per_page` | string(number) | 每页条数 |
| `vm_show_recycle` | `"0"` / `"1"` | 是否显示回收站 |
| `vm_tag_filters` | JSON string[] | 已选标签名数组 |

---

## 九、常见修改指南

| 需求 | 改哪里 |
|------|--------|
| 改卡片布局/外观 | `ui/video-grid.js`（HTML 模板）+ `style.css` |
| 改列表请求参数 | `video/browse.js → queryVideos()` |
| 改 AI 搜索 | `video/ai.js` |
| 改单条视频操作（标签/封面/删除） | `video/ops.js` |
| 改搜索栏、筛选条 | `tags/filter.js` + `index.html` 对应的 HTML |
| 改标签管理页 | `tags/manage.js` |
| 改设置页面 | `settings/config.js`（读写 config）、`settings/workflows.js`（导入/爬虫） |
| 改统计 | `settings/stats.js` |
| 改状态栏文案逻辑 | `ui/status.js` |
| 改视图切换 | `ui/nav.js` |
| 新增全局共享状态 | `core/state.js` 加属性 |
| 新增格式化函数 | `core/format.js` |
| 新增 localStorage 键 | `core/constants.js` 加常量 |
| 改事件绑定 | `main.js`（所有 DOM 事件注册均在此处） |

---

## 十、后端 API 速览（前端依赖）

前端通过 `fetch` 调用以下主要端点（完整文档见 `README.md`）：

| 方法 | 路径 | 用于 |
|------|------|------|
| GET | `/api/videos` | 列表分页 |
| GET | `/api/config` | 加载配置 |
| POST | `/api/config` | 保存配置 |
| POST | `/api/scan` | 扫描视频 |
| POST | `/api/covers/refresh` | 批量刷新封面 |
| POST | `/api/tags/auto-generate` | 自动打标签 |
| POST | `/api/videos/:id/tags` | 添加标签 |
| PATCH | `/api/videos/:id/tags/:tid` | 改标签名 |
| DELETE | `/api/videos/:id/tags/:tid` | 移除标签 |
| POST | `/api/videos/:id/tags/clear` | 清空标签 |
| GET | `/api/tags/catalog` | 标签管理列表 |
| PATCH | `/api/tags/:id` | 全局重命名 |
| DELETE | `/api/tags/:id` | 全局删除 |
| POST | `/api/ai/search` | AI 搜索 |
| GET | `/api/stats/summary` | 统计汇总 |
| POST | `/api/stats/sample` | 性能抽样 |
| POST | `/api/videos/:id/cover/refresh` | 单条刷新封面 |
| POST | `/api/videos/:id/cover` | 上传封面 |
| POST | `/api/videos/:id/recycle` | 移入回收站 |
| POST | `/api/videos/:id/restore` | 恢复 |
| POST | `/api/videos/:id/reveal` | 在资源管理器打开 |
| POST | `/api/videos/:id/open-external` | 外部播放器 |
| POST | `/api/videos/:id/play` | 记录播放 |
| GET | `/api/videos/:id/stream` | 视频流 |
| POST | `/api/recycle/purge` | 清空回收站 |
| POST | `/api/tags/import-preview` | 标签导入预览 |
| POST | `/api/tags/import` | 标签导入 |
| POST | `/api/crawler/run` | 运行爬虫 |
| POST | `/api/crawler/import` | 导入爬虫结果 |
| GET | `/api/intent/status` | 意图模型状态 |
