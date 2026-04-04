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

## 方式一：GitHub Actions 自动生成（推荐）

仓库已包含：

- [`.github/workflows/build-desktop.yml`](../.github/workflows/build-desktop.yml)：推送 `main`（命中 `paths`）或手动 **Run workflow**，产物在 **Artifacts**。
- [`.github/workflows/release-desktop.yml`](../.github/workflows/release-desktop.yml)：推送 **`v*` 标签**时在 **Releases** 发布附件。

**macOS 产物**

| 文件 | 说明 |
|------|------|
| `AC-Tracker-macos.dmg` | **推荐**：打开后将 `.app` 拖入「应用程序」 |
| `AC-Tracker-macos-app.zip` | 仅 `.app` 压缩包 |
| `AC-Tracker-macos-folder.zip` | PyInstaller onedir 目录 |

**Windows 产物**

| 文件 | 说明 |
|------|------|
| `AC-Tracker-Windows-Setup.exe` | **推荐**：Inno Setup 安装程序（当前为**当前用户**安装目录，无需管理员；含开始菜单/可选桌面快捷方式） |
| `AC-Tracker-windows-portable.zip` | 便携版：解压后运行 `AC-Tracker.exe` |

> 代码签名与公证需自行在 Apple / Microsoft 侧配置；未签名时系统可能提示「无法验证开发者」。

**发布到 GitHub Releases**：

```bash
git tag v1.0.3
git push origin v1.0.3
```

---

## 方式二：本机用 PyInstaller 打包

```bash
python3 -m pip install -r requirements.txt -r requirements-desktop.txt
python3 -m PyInstaller packaging/acm_tracker.spec --noconfirm
```

- **macOS**：`dist/AC Tracker.app`；可再执行 `bash packaging/build_dmg.sh` 生成根目录 `AC-Tracker-macos.dmg`。
- **Windows**：`dist/AC-Tracker/AC-Tracker.exe`。安装 `.exe` 需先安装 [Inno Setup](https://jrsoftware.org/isinfo.php)，再在仓库根执行：

```powershell
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.0.3 packaging\AC-Tracker.iss
```

（版本号与 `app/main.py` 中 `version` 对齐。）

首次打包若缺隐式依赖，在 `acm_tracker.spec` 的 `hiddenimports` 中补充后重试。
