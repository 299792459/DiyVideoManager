import { state } from "../core/state.js";
import { setSettingsStatus } from "../ui/status.js";
import { queryVideos } from "../video/browse.js";
export async function importTagsFromFile(file) {
  const strict = document.getElementById("tagsImportStrictPath")?.checked ? "1" : "0";
  const fdPrev = new FormData();
  fdPrev.append("file", file);
  setSettingsStatus("正在分析导入文件…");
  const pr = await fetch("/api/tags/import-preview?strict_path=" + encodeURIComponent(strict), {
    method: "POST",
    body: fdPrev,
  });
  let prev;
  try {
    prev = await pr.json();
  } catch (e) {
    setSettingsStatus("预览失败：响应不是 JSON", true);
    return;
  }
  if (!prev.ok) {
    setSettingsStatus(prev.error || "预览失败", true);
    return;
  }
  let summary = `非空行 ${prev.lines_nonempty}，将写入 ${prev.would_apply} 条视频`;
  if (prev.would_change != null) summary += `（其中约 ${prev.would_change} 条标签与当前不同）`;
  summary += `；跳过：无此ID ${prev.skipped_no_video}，路径不一致 ${prev.skipped_path}，缺字段t ${prev.skipped_no_t}`;
  if (prev.errors && prev.errors.length) summary += `；JSON解析错误 ${prev.errors.length} 行`;
  if (prev.samples && prev.samples.length) {
    summary += "\n\n示例（最多15条中的前6条）：\n";
    prev.samples.slice(0, 6).forEach(s => {
      summary += `  #${s.i} ${s.n}\n    当前 ${JSON.stringify(s.old)} → 新 ${JSON.stringify(s.new)}\n`;
    });
  }
  if (!window.confirm("确认按以下内容导入标签？\n\n" + summary)) {
    setSettingsStatus("已取消导入");
    return;
  }

  const fd = new FormData();
  fd.append("file", file);
  setSettingsStatus("正在导入标签…");
  const r = await fetch("/api/tags/import?strict_path=" + encodeURIComponent(strict), {
    method: "POST",
    body: fd,
  });
  let data;
  try {
    data = await r.json();
  } catch (e) {
    setSettingsStatus("导入失败：响应不是 JSON", true);
    return;
  }
  if (!data.ok) {
    setSettingsStatus(data.error || "导入失败", true);
    return;
  }
  const parts = [
    `已更新 ${data.updated}`,
    data.skipped_no_video ? `无此 ID ${data.skipped_no_video}` : "",
    data.skipped_path ? `路径跳过 ${data.skipped_path}` : "",
    data.skipped_no_t ? `缺 t 跳过 ${data.skipped_no_t}` : "",
  ].filter(Boolean);
  let msg = parts.join("，");
  if (data.errors && data.errors.length) {
    msg += " | 错误行 " + data.errors.length + "（见控制台）";
    console.warn("tags import errors", data.errors);
  }
  setSettingsStatus(msg, !!(data.errors && data.errors.length));
  state.listMode = "browse";
  await queryVideos(1);
}

export async function importCrawlerResult(file) {
  const strict = document.getElementById("crawlerImportStrictPath")?.checked ? "1" : "0";
  if (!window.confirm("将按文件中的 i 整批替换标签，并下载 cover_url 替换封面。确定？")) {
    setSettingsStatus("已取消导入");
    return;
  }
  setSettingsStatus("正在导入爬虫结果…");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/crawler/import?strict_path=" + encodeURIComponent(strict), {
      method: "POST",
      body: fd,
    });
    const data = await r.json();
    if (!data.ok) {
      setSettingsStatus(data.error || "导入失败", true);
      return;
    }
    const parts = [
      `已更新 ${data.updated} 条`,
      data.covers_updated != null ? `封面 ${data.covers_updated}` : "",
      data.skipped_recycled ? `跳过回收站 ${data.skipped_recycled}` : "",
      data.skipped_no_video ? `无此 ID ${data.skipped_no_video}` : "",
      data.skipped_path ? `路径不一致 ${data.skipped_path}` : "",
    ].filter(Boolean);
    let msg = parts.join("，");
    if (data.cover_errors && data.cover_errors.length) {
      msg += " | 封面失败 " + data.cover_errors.length + "（见控制台）";
      console.warn("crawler cover_errors", data.cover_errors);
    }
    if (data.errors && data.errors.length) {
      msg += " | 错误行 " + data.errors.length;
      console.warn("crawler import errors", data.errors);
    }
    setSettingsStatus(msg, !!(data.errors && data.errors.length));
    state.listMode = "browse";
    await queryVideos(1);
  } catch (err) {
    setSettingsStatus("请求失败: " + err, true);
  }
}

export async function probeIntentModel() {
  const el = document.getElementById("intentStatusLine");
  if (el) el.textContent = "正在检测（首次会下载模型，请稍候）…";
  try {
    const r = await fetch("/api/intent/status?probe=1");
    const d = await r.json();
    if (!el) return;
    if (!d.fastembed_installed) {
      el.textContent = "未安装 fastembed：请在环境中执行 pip install fastembed";
      return;
    }
    if (d.probe && d.probe.ok) {
      el.textContent = `模型可加载，向量维度 ${d.probe.dim}（模型：${d.model || ""}）`;
    } else {
      el.textContent = (d.probe && d.probe.error) || "加载失败";
    }
  } catch (e) {
    if (el) el.textContent = "请求失败: " + e;
  }
}

export async function runCrawlerPipeline(file) {
  setSettingsStatus("正在运行爬虫流水线…");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await fetch("/api/crawler/run", { method: "POST", body: fd });
    const data = await r.json();
    if (!data.ok) {
      setSettingsStatus(data.error || "爬虫失败", true);
      return;
    }
    const dl = document.getElementById("crawlerLastDownload");
    if (dl) {
      dl.href = data.download_url || "#";
      dl.style.display = "inline";
      dl.textContent = "下载输出：" + (data.output_file || "");
    }
    setSettingsStatus(
      `完成：写入 ${data.lines_out != null ? data.lines_out : "?"} 行，` +
        `跳过无匹配 ${data.skipped_no_match != null ? data.skipped_no_match : "?"}，` +
        `输入已保存（见数据目录 crawler/input）`
    );
  } catch (err) {
    setSettingsStatus("请求失败: " + err, true);
  }
}
