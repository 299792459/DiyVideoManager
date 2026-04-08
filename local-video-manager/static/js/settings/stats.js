import { fmtDuration, fmtSize } from "../core/format.js";

export function renderStatsSummary(data) {
  const db = data.db || {};
  const disk = data.disk || {};
  const box = document.getElementById("statsSummaryBox");
  if (!box) return;
  box.innerHTML = `
        <dl class="stats-dl">
          <dt>视频条数（正常）</dt><dd>${db.video_count ?? 0}</dd>
          <dt>回收站条数</dt><dd>${db.recycled_count ?? 0}</dd>
          <dt>标签数</dt><dd>${db.tag_count ?? 0}</dd>
          <dt>标签关联数</dt><dd>${db.video_tag_links ?? 0}</dd>
          <dt>总占用（索引）</dt><dd>${fmtSize(db.total_bytes)}</dd>
          <dt>总时长（索引）</dt><dd>${fmtDuration(db.total_duration_sec)}</dd>
          <dt>平均时长</dt><dd>${fmtDuration(db.avg_duration_sec)}</dd>
          <dt>总播放计数</dt><dd>${db.total_watch_events ?? 0}</dd>
          <dt>有封面</dt><dd>${db.videos_with_cover ?? 0}</dd>
          <dt>数据目录</dt><dd>${disk.data_dir || "-"}</dd>
          <dt>磁盘剩余</dt><dd>${disk.disk_free_gb ?? "-"} GB / 共 ${disk.disk_total_gb ?? "-"} GB（已用约 ${disk.disk_used_percent ?? "-"}%）</dd>
          <dt>数据库文件</dt><dd>${disk.db_file_mb ?? "-"} MB</dd>
          <dt>封面目录</dt><dd>${disk.covers_dir_mb ?? "-"} MB（${disk.cover_file_count ?? 0} 个文件）</dd>
        </dl>
      `;
}

export async function loadStatsSummary() {
  const box = document.getElementById("statsSummaryBox");
  try {
    const r = await fetch("/api/stats/summary");
    const data = await r.json();
    if (data.ok) renderStatsSummary(data);
  } catch (e) {
    if (box) box.textContent = "加载汇总失败: " + e;
  }
}

export function renderStatsSample(data) {
  const sys = data.system || {};
  const io = data.io_sample || {};
  let sysHtml = "";
  if (sys.psutil_error) {
    sysHtml = `<p class="muted">系统性能：${sys.psutil_error}（可 pip install psutil）</p>`;
  } else {
    sysHtml = `<p>CPU：${sys.cpu_percent ?? "-"}% &nbsp; 内存：${sys.memory_percent ?? "-"}%（${sys.memory_used_gb ?? "-"}/${sys.memory_total_gb ?? "-"} GB）</p>`;
  }
  const sampleBox = document.getElementById("statsSampleBox");
  if (sampleBox) {
    sampleBox.innerHTML = `
        ${sysHtml}
        <p>抽样 ${io.sample_n ?? 0} 条：stat 合计 <b>${io.stat_ms ?? 0}</b> ms；读取 4KB 合计 <b>${io.read_4k_ms ?? 0}</b> ms；缺失文件 ${io.missing_files ?? 0}</p>
      `;
  }
}

export async function runStatsSample() {
  const sampleBox = document.getElementById("statsSampleBox");
  const sample_size = Number(document.getElementById("statsSampleSize")?.value || 30);
  if (sampleBox) sampleBox.textContent = "正在抽样…";
  const r = await fetch("/api/stats/sample", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample_size }),
  });
  const data = await r.json();
  if (data.ok) renderStatsSample(data);
  else if (sampleBox) sampleBox.textContent = "抽样失败";
}
