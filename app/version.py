"""应用版本与仓库信息（单一来源，供 FastAPI、关于页与更新检查使用）。"""

APP_NAME = "AC Tracker"
APP_NAME_FULL = "AC Tracker · 刷题轨迹"
APP_VERSION = "1.0.12"

REPO_OWNER = "maskiey"
REPO_NAME = "acm-tracker"
GITHUB_REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
GITHUB_RELEASES_LATEST_URL = f"{GITHUB_REPO_URL}/releases/latest"
GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
