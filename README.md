# RSS News Aggregator

一个配置驱动、无数据库、无常驻服务器的 RSS/Atom 新闻聚合器，适合部署到 GitHub Pages。

## 特点

- RSS / Atom 自动识别
- 多源并行抓取
- ETag / Last-Modified 条件请求
- 失败重试
- 文章去重
- 发布时间统一为 UTC
- 分类与源管理
- 文章保留期限
- GitHub Actions 定时运行
- 抓取周期通过 `config.yaml` 配置
- 部署仓库通过 GitHub Actions Variables 配置
- 前端纯静态 HTML + JS
- Fuse.js 本地全文搜索
- Tailwind CSS CDN + Pure.css 风格布局
- 移动端适配
- 更新状态与源失败状态
- 不保存文章正文，只保存 RSS/Atom 提供的标题、摘要、链接等元数据

## 快速开始

1. 将本项目放入 GitHub 仓库。
2. 修改 `config.yaml` 中的站点信息和 RSS 源。
3. 修改 `.github/workflows/update.yml` 中的 `SITE_REPO`，或在仓库 Settings → Secrets and variables → Actions → Variables 设置：
   - `DEPLOY_REPO`: `owner/repository`
   - `DEPLOY_BRANCH`: `gh-pages`
   - `DEPLOY_PATH`: `/`
4. 如果部署到同一个仓库，可不设置 `DEPLOY_REPO`，工作流会直接部署到当前仓库。
5. 在 GitHub Pages 中选择部署分支/目录，或让工作流推送到 `gh-pages`。
6. 手动运行一次 `Update RSS` workflow 测试。

## 抓取周期

`config.yaml`：

```yaml
schedule:
  interval: "30m"
  timezone: "Asia/Taipei"
```

支持：

- `15m`
- `30m`
- `1h`
- `6h`
- `1d`

GitHub Actions 最终按 workflow 的调度运行；程序内部仍会根据每个 feed 的 `refresh` 设置决定是否真正请求。

注意：GitHub Actions 的 scheduled workflow 并不保证精确到分钟执行，尤其在高负载时可能延迟。因此这里的周期是“目标周期”，不是硬实时 SLA。

## 单个源独立刷新周期

```yaml
feeds:
  - name: Reuters
    url: "https://example.com/feed.xml"
    category: world
    enabled: true
    refresh: "30m"
```

如果没有设置 `refresh`，使用全局周期。

## GitHub Actions 部署

当前仓库部署：

```text
DEPLOY_REPO = 留空
```

另一个仓库部署：

```text
DEPLOY_REPO = yourname/my-news-site
DEPLOY_BRANCH = gh-pages
DEPLOY_PATH = /
```

跨仓库部署需要有写入目标仓库的 GitHub token，并设置：

```text
DEPLOY_TOKEN
```

如果部署到当前仓库，可以使用默认 `GITHUB_TOKEN`。

## 本地运行

需要 Python 3.11+：

```bash
pip install -r requirements.txt
python scripts/fetch_rss.py
```

然后启动静态服务器：

```bash
python -m http.server 8000 -d site
```

打开：

```text
http://localhost:8000
```

## 数据结构

生成：

```text
site/data/
├── news.json
├── sources.json
└── update.json
```

文章只保存 RSS/Atom 元数据，不抓取完整正文。

## 注意事项

### CORS

本项目采用“服务端/Actions 抓 RSS，浏览器读取 JSON”的模式，因此前端不直接访问 RSS，不依赖 RSS 源提供 CORS。

### robots / 服务条款

部署前应检查 RSS 提供方的使用条款、robots 策略以及合理访问频率。建议优先使用官方 RSS/Atom feed。

### GitHub Actions 频率

不要将大量 RSS 源设置成过短周期。15～60 分钟通常更适合普通新闻聚合。

## 目录

```text
.
├── config.yaml
├── requirements.txt
├── scripts/
│   ├── fetch_rss.py
│   └── generate_schedule.py
├── site/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── data/
└── .github/
    └── workflows/
        └── update.yml
```
