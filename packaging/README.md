# 桌面安装包构建

**终端用户是否需要 Python？** 不需要 — 详见 [END_USER_REQUIREMENTS.md](END_USER_REQUIREMENTS.md)（含 Windows WebView2、macOS 说明）。

打包完成后可在本机执行冒烟测试（验证冻结程序能响应 `/api/health`，**不要求**系统 PATH 里有 `python`）：

```bash
bash packaging/verify_bundle.sh
```

## 本地试跑（开发调试）

在项目根目录：

```bash
cd /path/to/acm-tracker
python3 -m pip install -r requirements-desktop.txt
python3 run_desktop.py
```

数据与配置写入用户目录 `~/.acm-tracker/`（Windows 为 `%USERPROFILE%\.acm-tracker\`）。

---

## 方式一：GitHub Actions 自动生成（推荐，可同时出 macOS + Windows）

仓库已包含：

- [`.github/workflows/build-desktop.yml`](../.github/workflows/build-desktop.yml)：推送 `main`（命中 `paths`）或手动 **Run workflow**，产物在 **Artifacts**。
- [`.github/workflows/release-desktop.yml`](../.github/workflows/release-desktop.yml)：推送 **`v*` 标签**时在 **Releases** 页面发布 zip（并保留自动生成说明）。

**仅 CI 构建（不进 Releases）**：将代码推送到 GitHub → **Actions** → **Build desktop packages** → **Run workflow**（或命中 `paths` 的 `main` 推送）。

**发布到 GitHub Releases**（推荐发版流程）：

```bash
git tag v1.0.0   # 版本号自定，须匹配 v*
git push origin v1.0.0
```

完成后在仓库 **Releases** 下载：

- `AC-Tracker-macos-app.zip`（`.app`）、`AC-Tracker-macos-folder.zip`（onedir）
- `AC-Tracker-windows.zip`（解压后运行 `AC-Tracker.exe`）

手动 Run **Build desktop packages** 时，仍在对应 **Workflow run** → **Artifacts** 下载同名 zip。

---

## 方式二：本机用 PyInstaller 打包

```bash
python3 -m pip install -r requirements.txt -r requirements-desktop.txt
python3 -m PyInstaller packaging/acm_tracker.spec --noconfirm
```

- **macOS**：`dist/AC Tracker.app`，另有 `dist/AC-Tracker/` onedir。可用 `packaging/build_macos.sh`。
- **Windows**（需在 Windows 上执行）：`dist/AC-Tracker/AC-Tracker.exe`，将整个 `AC-Tracker` 文件夹打成 zip 分发。可用 `packaging/build_windows.ps1`。

**macOS 注意**：`pywebview` 依赖 PyObjC；请使用带预编译轮子的 Python（推荐 python.org 的 3.10+）。若编译失败，优先用 **方式一** 在 `macos-latest` 上构建。

首次打包若缺隐式依赖，在 `acm_tracker.spec` 的 `hiddenimports` 中补充后重试。

**签名与公证**：公开发布时请在 Apple / Microsoft 侧完成代码签名；本仓库不提供证书。
