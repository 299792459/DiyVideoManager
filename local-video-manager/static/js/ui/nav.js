import { loadStatsSummary } from "../settings/stats.js";
import { loadTagsCatalog } from "../tags/manage.js";

export function showView(which) {
  const viewVideos = document.getElementById("viewVideos");
  const viewTags = document.getElementById("viewTags");
  const viewSettings = document.getElementById("viewSettings");
  const navVideos = document.getElementById("navVideos");
  const navTags = document.getElementById("navTags");
  const navSettings = document.getElementById("navSettings");
  if (!viewVideos || !viewTags || !viewSettings) return;

  const isVideos = which === "videos";
  const isTags = which === "tags";
  const isSettings = which === "settings";
  viewVideos.classList.toggle("hidden", !isVideos);
  viewTags.classList.toggle("hidden", !isTags);
  viewSettings.classList.toggle("hidden", !isSettings);
  navVideos?.classList.toggle("active", isVideos);
  navTags?.classList.toggle("active", isTags);
  navSettings?.classList.toggle("active", isSettings);
  if (isSettings) loadStatsSummary();
  if (isTags) loadTagsCatalog();
}
