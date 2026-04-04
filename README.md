# AC Tracker

维护者：[@maskiey](https://github.com/maskiey)

自托管的刷题记录可视化：用 FastAPI + SQLite 汇总多平台提交，展示年度 AC 热力图、周期统计、知识点分布与规则化周报文案。前端使用原生 JS 与 [Apache ECharts](https://echarts.apache.org/)（通过 [jsDelivr](https://www.jsdelivr.com/) CDN 加载）。

## 法律与第三方说明

- **独立项目**：本仓库与 Codeforces、洛谷、AtCoder、牛客等网站**无隶属关系**。各平台名称与标识归权利人所有，本项目仅作技术说明与链接用途。
- **使用责任**：抓取与同步依赖各站公开接口或页面结构；请自行遵守各平台服务条款与速率限制。**勿将账号 Cookie 或令牌提交到公开仓库**。
- **第三方许可**：运行时依赖见 `requirements.txt`；图表库为 Apache License 2.0。若你分发衍生作品，请保留相应版权声明。

## 功能概览

- 同步 **Codeforces / 洛谷 / 牛客 ACM / AtCoder** 等来源（见连接设置与 `.env`）
- 本地 SQLite 存储，支持增量同步与后台轮询（可选）
- 「贡献图」式年度 AC 热力图、周/日/月统计
- 知识点柱状图与饼图、按标签与日期查题
- 补题（未 AC）列表、PWA 安装（可选）

## 目录结构

```text
acm-tracker/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── fetcher.py
│   ├── extra_oj.py
│   ├── schemas.py
│   ├── services/
│   ├── templates/
│   └── static/
├── tests/
├── data/                 # SQLite 等运行时数据（默认不纳入版本库）
├── .env.example
├── requirements.txt      # 运行所需
├── requirements-dev.txt  # 含 pytest，开发/CI 使用
├── requirements-desktop.txt  # 桌面壳 + 打包
├── run_desktop.py        # 嵌入窗口入口
├── packaging/            # PyInstaller 配置与构建说明
├── LICENSE
└── README.md
```

## 环境与启动

**Python 3.9+**（推荐当前稳定版本）。

```bash
cd acm-tracker
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：数据库路径、各 OJ 账号与 Cookie 等
uvicorn app.main:app --reload --app-dir .
```

浏览器访问：<http://127.0.0.1:8000>

## 桌面端（嵌入窗口）

安装额外依赖后可直接运行桌面壳（本地起服务 + 窗口打开 `http://127.0.0.1:17890`）：

```bash
pip install -r requirements-desktop.txt
python run_desktop.py
```

配置与数据库默认在用户目录 `~/.acm-tracker/`。

- **预编译安装包**：在 **Actions** 中运行 **Build desktop packages**，于 **Artifacts** 下载：macOS 含 **`.dmg`** 与 `.app` zip；Windows 含 **`AC-Tracker-Windows-Setup.exe`**（安装包）与 **`AC-Tracker-windows-portable.zip`**（便携版）。详见 [packaging/README.md](packaging/README.md)。
- **本地打包**：见 [packaging/README.md](packaging/README.md)。
- **无 Python 环境能否运行**：可以，安装包内已带运行时；例外与系统组件见 [packaging/END_USER_REQUIREMENTS.md](packaging/END_USER_REQUIREMENTS.md)。

## 主要 HTTP 路由

| 路径 | 说明 |
|------|------|
| `/` `/knowledge` `/problems` `/settings` | 页面（类 App 底栏切换；`/sync` 重定向到 `/settings`） |
| `/heatmap` | 重定向至总览锚点（兼容旧链接） |
| `GET /api/health` | 健康检查 |
| `POST /api/sync` | 触发同步（body：`source`, `force_full`） |
| `GET /api/heatmap?year=` | 年度热力图数据 |
| `GET /api/summary` | 总览数字与最近同步 |
| `GET /api/stats/weekly` | 本周统计 |
| `GET /api/stats/period?period=` | `day` / `week` / `month` / `year` |
| `GET /api/stats/tags?oj=` | 知识点分布 |
| `GET /api/stats/sources` | 来源占比 |
| `GET /api/tags/options` | 标签自动完成 |
| `GET /api/problems/by-tag` `by-date` `unsolved` | 题目列表 |
| `GET /api/report/weekly` | 周报文案 |
| `GET/POST /api/config` | 读取/保存配置 |
| `GET /api/sync/runs` | 同步历史 |
| `GET /api/debug/luogu` | 调试：解析洛谷 UID 等（生产环境建议限制访问） |

## 开发与测试

```bash
pip install -r requirements-dev.txt
pytest
```

## 安全

见 [SECURITY.md](SECURITY.md)。

## 许可

MIT License，见 [LICENSE](LICENSE)。
