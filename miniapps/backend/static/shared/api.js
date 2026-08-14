/**
 * Общий JS-хелпер для мини-апп «Спокойный рассвет».
 * Подключается через <script src="/shared/api.js"></script> перед основным скриптом.
 *
 * Экспортирует:
 *   tg     — window.Telegram.WebApp (уже инициализированный)
 *   apiFetch(path, options) — fetch с автоматическим заголовком X-Telegram-Init-Data
 */

const tg = window.Telegram?.WebApp ?? null;
if (tg) {
  tg.ready();
  tg.expand();
}

/**
 * Авторизованный fetch к /api/...
 * Автоматически добавляет X-Telegram-Init-Data из tg.initData.
 * @param {string} path — путь относительно корня, например '/api/reviews/feed'
 * @param {RequestInit} [options] — стандартные опции fetch
 */
async function apiFetch(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
    "X-Telegram-Init-Data": tg?.initData ?? "",
  };
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    // initData не прошла проверку — покажем ошибку пользователю
    tg?.showAlert?.("Ошибка авторизации. Попробуйте закрыть и открыть мини-приложение заново.");
    throw new Error("401 Unauthorized");
  }
  if (!res.ok) {
    // Раньше ошибки 4xx/5xx (например, "фото слишком большое" или ошибка на
    // сервере) молча проглатывались — apiFetch возвращал res как есть, и
    // код-вызывающая сторона считала запрос успешным. Теперь бросаем ошибку
    // с текстом от сервера, чтобы её можно было показать пользователю.
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

/**
 * Форматирует дату/время в читаемый вид на русском.
 */
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

