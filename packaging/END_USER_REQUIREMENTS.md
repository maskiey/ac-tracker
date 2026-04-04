# 安装包运行环境说明（终端用户）

## 是否需要安装 Python？

**不需要。**  
使用 PyInstaller 打出来的 **macOS `.app`** 或 **Windows `AC-Tracker` 文件夹内的 `AC-Tracker.exe`** 已内置 Python 解释器与依赖库，**不要求**用户在系统里再安装 Python、pip 或虚拟环境。

解压 / 复制整个分发目录即可运行（不要把单个 exe 单独拷走而丢掉同目录下的 `_internal` 等文件）。

---

## 仍可能需要的系统组件（与 Python 无关）

### Windows

- **Microsoft Edge WebView2 Runtime**（用于显示内嵌网页窗口）。  
  - Windows 11 及部分已装新版 Edge 的环境通常**已自带**。  
  - 若启动后窗口空白或报错，请安装：[WebView2 运行时](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)（Evergreen 安装包即可）。
- 一般无需单独安装 **.NET**，当前 pywebview 的 WebView2 后端不额外要求用户手动装 .NET SDK。

### macOS

- 使用系统 **WebKit**，一般无额外安装步骤。  
- 若从未签名的 `.app` 启动被拦截：在 **系统设置 → 隐私与安全性** 中选择仍要打开，或右键 **打开** 一次。

### 网络与数据

- 首次运行会在用户目录创建 **`~/.acm-tracker/`**（Windows：`%USERPROFILE%\.acm-tracker\`）存放 SQLite 与 `.env`，**不需要**事先配置项目里的开发用 `.env`。
- 同步各 OJ 需要本机网络访问对应网站。

---

## 如何自检「无 Python 环境」是否可用？

1. 在一台**未安装 Python** 的机器上（或临时从 PATH 中去掉 Python）解压发布包。  
2. 直接双击运行 **macOS：`AC Tracker.app`**，或 **Windows：`AC-Tracker.exe`**。  
3. 若窗口能打开且页面能加载，即说明满足「无独立 Python 环境」运行。

开发者在本地打完包后，可在**有 Python 的构建机**上运行仓库中的脚本做一次 HTTP 冒烟测试（见同目录 `verify_bundle.sh`）。

---

## 与「安装程序」的区别

当前产物是 **可直接运行的应用包 / 文件夹**，不是安装向导（.msi / .dmg 安装器）。若需要专业安装包，需在上述产物基础上再用 Inno Setup、WiX、`create-dmg` 等工具制作（并自行代码签名）。
