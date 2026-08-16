
const tg = window.Telegram?.WebApp ?? null;
if (tg) {
  tg.ready();
  tg.expand();
}


async function apiFetch(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
    "X-Telegram-Init-Data": tg?.initData ?? "",
  };
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    tg?.showAlert?.("Ошибка авторизации. Попробуйте закрыть и открыть мини-приложение заново.");
    throw new Error("401 Unauthorized");
  }
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.clone().json();
      detail = data?.detail || "";
    } catch (_) { /* тело не JSON — не страшно */ }
    const err = new Error(detail || `${res.status} ${res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return res;
}

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}
function fmtDateTime(iso) {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

