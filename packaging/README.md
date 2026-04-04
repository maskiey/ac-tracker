# 桌面安装包构建

## 本地试跑（不打包）

```bash
pip install -r requirements-desktop.txt
python run_desktop.py
```

数据与配置写入用户目录 `~/.acm-tracker/`（Windows 为 `%USERPROFILE%\.acm-tracker\`）。

## Windows / macOS 可执行文件

在项目根目录：

```bash
pip install -r requirements-desktop.txt
python -m PyInstaller packaging/acm_tracker.spec
```

或使用脚本：`packaging/build_macos.sh`、`packaging/build_windows.ps1`。

**macOS 注意**：`pywebview` 依赖 PyObjC；请使用带预编译轮子的 Python 版本（推荐官方 python.org 的 3.10+），若 `pip install pywebview` 尝试本地编译失败，请先升级 pip 再试，或换用对应架构的 wheel。

- **Windows**：`dist/AC-Tracker/AC-Tracker.exe`，可将整个 `AC-Tracker` 文件夹打成 zip 分发。
- **macOS**：`dist/AC Tracker.app`，可压缩为 zip 或使用 `hdiutil create` 制作 `.dmg` 分发。

首次打包若缺少隐式依赖，在 `acm_tracker.spec` 的 `hiddenimports` 中补充模块名后重试。

**签名与公证**：面向公开发布时，请在 Apple Developer / Windows 代码签名流程下对二进制签名；本仓库不提供证书。
