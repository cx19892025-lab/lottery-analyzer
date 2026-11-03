"""
路径解析 —— 统一处理「源码运行」与「PyInstaller 打包运行」两种形态。

为什么要单独一个模块：
    打包成 exe 后，程序所在目录（`sys._MEIPASS` / exe 同级）**可能是只读的**，
    不能把数据库、设置写在那里；而只读资源（模板/静态文件/初始数据）又必须从
    包内取。两件事必须分开，否则要么打包后写不进去，要么源码运行时找不到文件。

两种路径：
    resource_path()  → 只读资源。打包后在包内，源码运行在项目目录。
    user_data_path() → 可写数据。始终在用户目录（Windows: %APPDATA%\\LotteryAnalyzer），
                       打包后首次运行会把包内的初始数据复制过去。

源码运行时 user_data_path() 也指向用户目录吗？
    不是。为了让开发时的数据仍然落在项目 data/ 下（方便调试、也避免污染本机
    APPDATA），源码运行直接沿用项目目录。只有打包后才切到用户目录。
"""
import os
import shutil
import sys

APP_NAME = "LotteryAnalyzer"


def is_frozen():
    """是否运行在 PyInstaller 打包出的 exe 中"""
    return getattr(sys, "frozen", False)


def resource_path(*parts):
    """
    只读资源路径（模板、静态文件、包内初始数据）。

    打包后 PyInstaller 会把数据解压到 sys._MEIPASS（onedir 模式下即 _internal），
    源码运行则就是本文件所在目录。
    """
    if is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def exe_dir():
    """
    exe 所在目录（源码运行时为项目目录）。

    打包后 exe 同级还会放一份 data/（数据库与 settings.json），
    这是**给用户看的**：想改配置可以直接用记事本打开，
    想换数据可以直接替换文件。它和 _internal 里的资源是两回事。
    """
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _project_root():
    return os.path.dirname(os.path.abspath(__file__))


def user_data_dir():
    """
    可写数据目录。

    - 源码运行：项目目录下的 data/
    - 打包运行：%APPDATA%\\LotteryAnalyzer（Windows）或 ~/.local/share/LotteryAnalyzer
    """
    if not is_frozen():
        return os.path.join(_project_root(), "data")

    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP_NAME)


def user_data_path(*parts):
    """可写数据文件路径（数据库、settings.json）"""
    return os.path.join(user_data_dir(), *parts)


def ensure_user_data(*seed_files):
    """
    确保用户数据目录存在；对每个 seed 文件，若用户目录里还没有，
    就复制一份过去。

    seed 文件的查找顺序（先找到先用）：
      1. exe 同级的 data/  —— 打包时放的那份，用户可见、可自行替换
      2. 包内 data/        —— PyInstaller 的 _internal 里（如果有）

    顺序很重要：打包后 exe 同级那份才是"可编辑的初始配置"，
    用户直接改它就能影响首次运行的行为。

    返回 {文件名: "copied" | "exists" | "missing"}，便于启动日志与排错。
    """
    result = {}
    target_dir = user_data_dir()
    os.makedirs(target_dir, exist_ok=True)

    for name in seed_files:
        target = os.path.join(target_dir, name)
        if os.path.exists(target):
            result[name] = "exists"
            continue

        candidates = [
            os.path.join(exe_dir(), "data", name),      # exe 同级（打包时放的）
            resource_path("data", name),                # 包内
        ]
        source = next((c for c in candidates if os.path.exists(c)), None)

        if source is None:
            result[name] = "missing"
            continue
        try:
            shutil.copy2(source, target)
            result[name] = "copied"
        except OSError as e:
            result[name] = f"copy_failed: {e}"
    return result
