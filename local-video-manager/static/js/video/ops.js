import { state } from "../core/state.js";
import { queryVideos } from "./browse.js";
import { renderAiPage } from "./ai.js";
import { setVideoStatus, setSettingsStatus } from "../ui/status.js";
import { loadStatsSummary } from "../settings/stats.js";
import { showView } from "../ui/nav.js";

function patchVideoTagInAiList(videoId, updater) {
  const v = state.aiFullVideos.find(x => x.id === videoId);
  if (v) updater(v);
}

export async function refreshOneCover(videoId, force = false) {
  setVideoStatus(force ? "正在强制重新生成封面..." : "正在刷新封面...");
  const r = await fetch(`/api/videos/${videoId}/cover/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force: !!force }),
  });
  const data = await r.json();
  if (data.ok && data.skipped) {
    if (state.listMode === "browse") await queryVideos(state.currentPage);
    else renderAiPage();
    setVideoStatus(data.message || "已有封面，已跳过");
    return;
  }
  if (data.ok) {
    if (state.listMode === "ai" && data.cover_url) {
      const v = state.aiFullVideos.find(x => x.id === videoId);
      if (v) v.cover_url = data.cover_url;
      renderAiPage();
    } else {
      await queryVideos(state.currentPage);
    }
    setVideoStatus("封面已刷新");
  } else setVideoStatus(data.error || "刷新失败", true);
}

export async function autoGenerateTags() {
  setSettingsStatus("正在生成标签...");
  const r = await fetch("/api/tags/auto-generate", { method: "POST" });
  const data = await r.json();
  if (data.ok) {
    setSettingsStatus(`自动标签：生成 ${data.generated_tags}，关联 ${data.attached}`);
    const viewSettings = document.getElementById("viewSettings");
    if (viewSettings && !viewSettings.classList.contains("hidden")) loadStatsSummary();
    state.listMode = "browse";
    await queryVideos(1);
  } else setSettingsStatus("自动标签失败", true);
}

export async function clearVideoTags(videoId) {
  if (!confirm("确定移除该视频的全部标签？")) return;
  setVideoStatus("正在清除标签…");
  const r = await fetch(`/api/videos/${videoId}/tags/clear`, { method: "POST" });
  const data = await r.json();
  if (!data.ok) {
    setVideoStatus(data.error || "清除失败", true);
    return;
  }
  setVideoStatus("已清除该视频的全部标签");
  if (state.listMode === "browse") await queryVideos(state.currentPage);
  else {
    const v = state.aiFullVideos.find(x => x.id === videoId);
    if (v) {
      v.tags = [];
      v.tag_items = [];
    }
    renderAiPage();
  }
}

export async function removeSingleTagFromVideo(videoId, tagId) {
  if (!confirm("从该视频移除此标签？")) return;
  setVideoStatus("正在移除标签…");
  const r = await fetch(`/api/videos/${videoId}/tags/${tagId}`, { method: "DELETE" });
  const data = await r.json();
  if (!data.ok) {
    setVideoStatus(data.error || "移除失败", true);
    return;
  }
  setVideoStatus("已移除该标签");
  if (state.listMode === "browse") await queryVideos(state.currentPage);
  else {
    patchVideoTagInAiList(videoId, v => {
      v.tag_items = (v.tag_items || []).filter(t => t.id !== tagId);
      v.tags = (v.tag_items || []).map(t => t.name);
    });
    renderAiPage();
  }
}

export async function editSingleTagOnVideo(videoId, tagId) {
  const list = state.listMode === "ai" ? state.aiFullVideos : state.currentVideos;
  const row = list.find(x => x.id === videoId);
  const cur = row && row.tag_items ? row.tag_items.find(t => t.id === tagId) : null;
  const curName = cur ? cur.name : "";
  const nn = prompt("修改该视频上的标签名称（将使用库中已有同名标签或新建）", curName);
  if (nn === null) return;
  const name = nn.trim();
  if (!name) {
    setVideoStatus("名称不能为空", true);
    return;
  }
  if (name === curName) return;
  setVideoStatus("正在修改标签…");
  const r = await fetch(`/api/videos/${videoId}/tags/${tagId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await r.json();
  if (!data.ok) {
    setVideoStatus(data.error || "修改失败", true);
    return;
  }
  const newId = data.tag_id != null ? data.tag_id : tagId;
  setVideoStatus("标签已更新");
  if (state.listMode === "browse") await queryVideos(state.currentPage);
  else {
    patchVideoTagInAiList(videoId, v => {
      if (!v.tag_items) v.tag_items = [];
      const i = v.tag_items.findIndex(t => t.id === tagId);
      if (i >= 0) {
        v.tag_items[i] = { id: newId, name };
        const seen = new Set();
        v.tag_items = v.tag_items.filter(t => {
          if (seen.has(t.id)) return false;
          seen.add(t.id);
          return true;
        });
      }
      v.tags = v.tag_items.map(t => t.name);
    });
    renderAiPage();
  }
}

export async function addTag(videoId) {
  const tag = prompt("输入要添加的标签");
  if (!tag) return;
  const r = await fetch(`/api/videos/${videoId}/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag: tag.trim() }),
  });
  const data = await r.json();
  if (data.ok) {
    const tid = data.tag_id;
    const name = tag.trim();
    if (state.listMode === "ai") {
      const v = state.aiFullVideos.find(x => x.id === videoId);
      if (v) {
        v.tags = v.tags || [];
        if (!v.tags.includes(name)) v.tags.push(name);
        if (tid != null) {
          v.tag_items = v.tag_items || [];
          if (!v.tag_items.some(x => x.id === tid)) v.tag_items.push({ id: tid, name });
        }
      }
      renderAiPage();
    } else {
      await queryVideos(state.currentPage);
    }
    setVideoStatus("标签已添加");
  } else setVideoStatus(data.error || "失败", true);
}

export async function uploadCover(videoId) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/*";
  input.onchange = async () => {
    if (!input.files || !input.files[0]) return;
    const fd = new FormData();
    fd.append("file", input.files[0]);
    const r = await fetch(`/api/videos/${videoId}/cover`, { method: "POST", body: fd });
    const data = await r.json();
    if (data.ok) {
      if (state.listMode === "ai" && data.cover_url) {
        const v = state.aiFullVideos.find(x => x.id === videoId);
        if (v) v.cover_url = data.cover_url;
        renderAiPage();
      } else {
        await queryVideos(state.currentPage);
      }
      setVideoStatus("封面已更新");
    } else setVideoStatus(data.error || "失败", true);
  };
  input.click();
}

export async function recycleVideo(videoId) {
  const r = await fetch(`/api/videos/${videoId}/recycle`, { method: "POST" });
  const data = await r.json();
  if (data.ok) {
    await queryVideos(state.currentPage);
    setVideoStatus("已移入回收站（文件仍在磁盘）");
  } else setVideoStatus(data.error || "操作失败", true);
}

export async function restoreVideo(videoId) {
  const r = await fetch(`/api/videos/${videoId}/restore`, { method: "POST" });
  const data = await r.json();
  if (data.ok) {
    await queryVideos(state.currentPage);
    setVideoStatus("已从回收站恢复");
  } else setVideoStatus(data.error || "操作失败", true);
}

export async function openExternalPlay(videoId) {
  setVideoStatus("正在启动外部播放器…");
  const r = await fetch(`/api/videos/${videoId}/open-external`, { method: "POST" });
  const data = await r.json();
  if (data.ok) setVideoStatus("已请求外部播放器打开");
  else setVideoStatus(data.error || "外部播放失败", true);
}

export async function revealVideoPath(videoId) {
  const r = await fetch(`/api/videos/${videoId}/reveal`, { method: "POST" });
  const data = await r.json();
  if (data.ok) setVideoStatus("已在资源管理器中定位");
  else setVideoStatus(data.error || "无法打开位置（文件可能已不存在）", true);
}

export async function purgeRecycleBin() {
  if (!confirm("将永久删除回收站中条目对应的磁盘视频文件及封面文件，并清除数据库记录。不可恢复。确定？")) return;
  setSettingsStatus("正在清空回收站…");
  const r = await fetch("/api/recycle/purge", { method: "POST" });
  const data = await r.json();
  if (!data.ok) {
    setSettingsStatus("清空失败", true);
    return;
  }
  let m = `已删除磁盘文件 ${data.files_deleted} 个，库记录 ${data.rows_removed} 条`;
  if (data.errors && data.errors.length) m += `；警告 ${data.errors.length} 条`;
  setSettingsStatus(m, !!(data.errors && data.errors.length));
  const viewSettings = document.getElementById("viewSettings");
  if (viewSettings && !viewSettings.classList.contains("hidden")) loadStatsSummary();
  showView("videos");
  await queryVideos(1);
}

export async function playVideo(videoId) {
  const v = state.currentVideos.find(x => x.id === videoId);
  const playerTitle = document.getElementById("playerTitle");
  const player = document.getElementById("player");
  const playerDialog = document.getElementById("playerDialog");
  if (!v || !player || !playerDialog) return;
  if (playerTitle) playerTitle.textContent = v.filename;
  player.src = `/api/videos/${videoId}/stream`;
  playerDialog.showModal();
  await fetch(`/api/videos/${videoId}/play`, { method: "POST" });
  if (state.listMode === "ai") {
    const row = state.aiFullVideos.find(x => x.id === videoId);
    if (row) row.watch_count = (row.watch_count || 0) + 1;
    renderAiPage();
  } else {
    await queryVideos(state.currentPage);
  }
}

export function exportAiData() {
  window.open("/api/ai/export?format=jsonl", "_blank");
}
