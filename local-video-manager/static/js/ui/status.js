export function setVideoStatus(text, isErr = false) {
  const el = document.getElementById("videoStatus");
  if (!el) return;
  el.textContent = text;
  el.className = "inline-status " + (isErr ? "err" : "ok");
}

export function setSettingsStatus(text, isErr = false) {
  const el = document.getElementById("settingsStatus");
  if (!el) return;
  el.textContent = text;
  el.className = "inline-status " + (isErr ? "err" : "ok");
}

export function setTagManageStatus(text, isErr = false) {
  const el = document.getElementById("tagManageStatus");
  if (!el) return;
  el.textContent = text;
  el.className = "inline-status " + (isErr ? "err" : "ok");
}
