# 安装包运行环境说明（终端用户）

## 是否需要安装 Python？

**不需要。**  
使用 PyInstaller 打出来的 **macOS `.app`**、**DMG** 中的内容，或 **Windows 安装程序 / 便携目录内的 `AC-Tracker.exe`**，已内置 Python 解释器与依赖库，**不要求**用户在系统里再安装 Python、pip 或虚拟环境。

解压 / 复制整个分发目录即可运行（不要把单个 exe 单独拷走而丢掉同目录下的 `_internal` 等文件）。

---

## 仍可能需要的系统组件（与 Python 无关）

### Windows

- **Microsoft Edge WebView2 Runtime**（用于显示内嵌网页窗口）。  
  - Windows 11 及部分已装新版 Edge 的环境通常**已自带**。  
  - 若启动后窗口空白或报错，请安装：[WebView2 运行时](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)（Evergreen 安装包即可）。
- **安装程序**（`AC-Tracker-Windows-Setup.exe`）默认安装到**当前用户**目录（`%LOCALAPPDATA%\Programs\AC Tracker`），无需管理员权限；若 SmartScreen 提示「未知发布者」，属未签名软件常见情况，可按提示「仍要运行」或自行在「Windows 安全中心」中放行。
- 若安装后双击无反应或瞬间退出：请到 **`%USERPROFILE%\.acm-tracker\ac-tracker.log`** 查看启动日志（桌面版会将错误写入该文件）；并确认已安装 [WebView2 运行时](https://developer.microsoft.com/microsoft-edge/webview2/)。
- **打包版说明**：界面使用 pywebview 的 Windows（WinForms）后端，依赖 **pythonnet** 与系统上的 **.NET Framework 4.x**（Windows 10/11 通常已具备）。安装包会在启动时自动将内嵌的 `python3xx.dll` 告知 CLR（`PYTHONNET_PYDLL`），避免「无窗口、进程秒退」类问题。
- 若日志中出现 `Failed to resolve Python.Runtime`、`cannot call null pointer` 等与 **pythonnet/CLR** 相关的字样：请使用**最新发布**的安装包/便携包；勿只复制单个 `.exe` 而丢弃同目录的 **`_internal` 文件夹**及全部文件。
- 一般无需单独安装 **.NET SDK**；开发与运行期需要的是系统自带的 **.NET Framework** 运行时组件，而非 SDK。

### macOS

- 使用系统 **WebKit**，一般无额外安装步骤。  
- **DMG**：打开后将 **AC Tracker** 拖入 **应用程序** 文件夹即可。  
- 若从未签名的 `.app` 启动被拦截：在 **系统设置 → 隐私与安全性** 中选择仍要打开，或右键 **打开** 一次。

### 网络与数据

- 首次运行会在用户目录创建 **`~/.acm-tracker/`**（Windows：`%USERPROFILE%\.acm-tracker\`）存放 SQLite 与 `.env`，**不需要**事先配置项目里的开发用 `.env`。
- 同步各 OJ 需要本机网络访问对应网站。

### 版本与更新提示

- 界面提供 **「关于」**，并在检测到 **GitHub 上存在更新的正式发行版**时显示顶部提示条（可「稍后提醒」；对**该版本号**忽略一次，下次更高版本仍会提示）。
- 检查通过服务端请求 **GitHub 公开 API**（`GET .../releases/latest`），仅用于比对 **语义化版本号** 与获取 **发行页链接**，**不**上传账号、Cookie 或刷题数据。
- 服务端对结果做**短时缓存**（约数分钟），减少对 GitHub 的请求次数。
- 完全关闭更新检查：在环境变量或 `.env` 中设置 **`ACM_TRACKER_DISABLE_UPDATE_CHECK=1`**（参见仓库根目录 `.env.example`）。关闭后「关于」仍可用，但不再请求 GitHub。

---

## 如何自检「无 Python 环境」是否可用？

1. 在一台**未安装 Python** 的机器上（或临时从 PATH 中去掉 Python）解压发布包。  
2. 直接双击运行 **macOS：`AC Tracker.app`**，或 **Windows：`AC-Tracker.exe`**。  
3. 若窗口能打开且页面能加载，即说明满足「无独立 Python 环境」运行。

开发者在本地打完包后，可在**有 Python 的构建机**上运行仓库中的脚本做一次 HTTP 冒烟测试（见同目录 `verify_bundle.sh`）。

---

## 分发形态说明

- **macOS**：除 `.app` / zip 外，Release 还提供 **`.dmg`**（内含应用程序与「应用程序」文件夹快捷方式），便于拖拽安装。  
- **Windows**：除便携 zip 外，提供 **Inno Setup 生成的安装程序**（开始菜单快捷方式、可选桌面图标、卸载入口）。未做代码签名时，以系统安全提示为准。
