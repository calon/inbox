const state = {
  articles: [],
  filtered: [],
  sources: [],
  update: null,
  fuse: null
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value) {
  if (!value) return "未知时间";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "未知时间";
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(d);
}

function relativeDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return formatDate(value);
}

function renderArticles() {
  const list = $("#article-list");
  const empty = $("#empty");

  if (!state.filtered.length) {
    list.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");

  list.innerHTML = state.filtered.map(article => `
    <article class="article-row py-5">
      <div class="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400">
        <span class="font-medium text-gray-600">${escapeHtml(article.source)}</span>
        <span>·</span>
        <span>${escapeHtml(article.category)}</span>
        <span>·</span>
        <time datetime="${escapeHtml(article.published || "")}"
              title="${escapeHtml(formatDate(article.published))}">
          ${escapeHtml(relativeDate(article.published))}
        </time>
      </div>
      <h2 class="article-title text-base font-medium text-gray-900">
        <a href="${escapeHtml(article.url)}"
           target="_blank"
           rel="noopener noreferrer"
           class="hover:underline">
          ${escapeHtml(article.title)}
        </a>
      </h2>
      ${article.summary ? `
        <p class="article-summary mt-2 max-w-4xl text-sm text-gray-600">
          ${escapeHtml(article.summary)}
        </p>
      ` : ""}
    </article>
  `).join("");
}

function rebuildFilters() {
  const categories = [...new Set(state.articles.map(x => x.category).filter(Boolean))].sort();
  const sources = [...new Set(state.articles.map(x => x.source).filter(Boolean))].sort();

  $("#category").innerHTML =
    `<option value="">全部分类</option>` +
    categories.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join("");

  $("#source").innerHTML =
    `<option value="">全部来源</option>` +
    sources.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join("");
}

function applyFilters() {
  const q = $("#search").value.trim();
  const category = $("#category").value;
  const source = $("#source").value;

  let articles = state.articles;

  if (q && state.fuse) {
    articles = state.fuse.search(q).map(result => result.item);
  }

  if (category) {
    articles = articles.filter(x => x.category === category);
  }

  if (source) {
    articles = articles.filter(x => x.source === source);
  }

  state.filtered = articles;
  renderArticles();
}

function renderSources() {
  const sourceHealth = $("#source-health");
  const sourceList = $("#source-list");

  const failures = state.sources.filter(x => x.last_error);
  if (!failures.length) {
    sourceHealth.classList.add("hidden");
    return;
  }

  sourceHealth.classList.remove("hidden");
  sourceList.innerHTML = state.sources.map(source => {
    const status = source.last_error
      ? `<span class="text-red-600">失败：${escapeHtml(source.last_error)}</span>`
      : `<span class="text-green-700">正常</span>`;

    return `
      <div class="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between">
        <span>${escapeHtml(source.name)}</span>
        <span class="text-xs">${status}</span>
      </div>
    `;
  }).join("");
}

async function loadConfig() {
  try {
    const response = await fetch("config-public.json", { cache: "no-store" });
    if (!response.ok) return;
    const config = await response.json();

    if (config.site?.title) {
      $("#site-title").textContent = config.site.title;
      document.title = config.site.title;
    }
    if (config.site?.description) {
      $("#site-description").textContent = config.site.description;
    }
  } catch {
    // config-public.json is optional.
  }
}

async function loadData() {
  const [news, sources, update] = await Promise.all([
    fetch("data/news.json", { cache: "no-store" }).then(r => r.json()),
    fetch("data/sources.json", { cache: "no-store" }).then(r => r.json()),
    fetch("data/update.json", { cache: "no-store" }).then(r => r.json())
  ]);

  state.articles = Array.isArray(news) ? news : [];
  state.sources = Array.isArray(sources) ? sources : [];
  state.update = update || {};

  state.fuse = new Fuse(state.articles, {
    keys: ["title", "summary", "source", "category"],
    threshold: 0.35,
    ignoreLocation: true,
    minMatchCharLength: 2
  });

  rebuildFilters();
  applyFilters();
  renderSources();

  if (state.update.updated) {
    $("#update-info").textContent =
      `更新于 ${formatDate(state.update.updated)} · ${state.update.articles ?? 0} 篇`;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  $("#search").addEventListener("input", applyFilters);
  $("#category").addEventListener("change", applyFilters);
  $("#source").addEventListener("change", applyFilters);

  await loadConfig();

  try {
    await loadData();
  } catch (error) {
    $("#article-list").innerHTML =
      `<div class="py-12 text-center text-sm text-red-600">数据加载失败：${escapeHtml(error.message)}</div>`;
  }
});
