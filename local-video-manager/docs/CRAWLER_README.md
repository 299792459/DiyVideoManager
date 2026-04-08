# 爬虫元数据流水线

## 代码位置

| 模块 | 说明 |
|------|------|
| `crawler/pipeline.py` | 读入 JSONL、mock 匹配、写出结果 |
| `crawler/mock_source.py` | 模拟站点数据 |
| `crawler/cover_io.py` | 下载封面、目录工具 |
| `crawler/import_body.py` | 读取 multipart/正文（与标签导入一致） |
| `crawler/flask_routes.py` | `/api/crawler/*` 路由，经 `register_crawler_routes(app, deps)` 挂到主应用 |
| `app.py` | 仅 `from crawler.flask_routes import ...` 并注入依赖，**不含爬虫实现代码** |

## 目录（均在「数据目录」下）

| 路径 | 用途 |
|------|------|
| `crawler/input/` | 上传的待处理 JSONL（带时间戳文件名） |
| `crawler/output/` | 爬虫结果 JSONL（`crawler_out_<时间戳>.jsonl`） |
| `crawler/cache/` | 预留（后续真实请求缓存） |
| `covers/` | 导入封面时写入的图片（与抽帧规则相同：按视频路径 MD5 命名 `.jpg`） |

## 输入格式

每行一个 JSON 对象，与标签导出一致，例如：

```json
{"i":5,"n":"示例.mp4","p":"C:\\Videos\\示例.mp4","t":[]}
```

- `i`：库内视频 ID（必填）
- `n`：文件名（用于 mock 匹配）
- `p`：路径（导入时可配合「严格校验路径」）
- `t`：标签数组

## Mock 行为（当前）

`crawler/mock_source.py` 中按文件名**子串**匹配（如包含「大华」「小米」），合并 mock 标签与 `cover_url`。未匹配的行不会出现在输出文件中。

后续将步骤 1 替换为真实网页解析时，保持 `step1_mock_discover()` 或等价注册表结构即可。

## 输出格式

在输入字段基础上增加（按需出现）：

- `code`：站点代号
- `actor_name`：演员名
- `matched_by`：匹配用到的子串
- `cover_url`：封面图片 URL
- `input_t`：原始输入标签
- `t`：合并后的标签列表

## 导入到系统

设置页「导入爬虫结果」会：

1. 按 `i` 查找视频；**回收站**中的记录跳过。
2. 用 `t` **整批替换**该视频标签（与「标签批量导入」一致）。
3. 若存在 `cover_url`，下载到 `covers/` 并更新该视频的封面字段。

可选查询参数：`strict_path=1`，当行内包含 `p` 且与库内路径不一致时跳过该行。
