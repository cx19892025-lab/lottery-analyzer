"""
独立窗口启动器 —— 让打包后的程序看起来像一个原生桌面软件。

背景：
    本项目界面是网页（Flask + ECharts），直接用系统默认浏览器打开会有
    地址栏、标签页、书签栏，且任务栏显示的是浏览器图标，观感不像独立软件。

做法：
    用一个 tkinter 容器窗口承载界面，内部通过 Chromium 系的
    `--app=<url>` 模式启动 Edge/Chrome。该模式没有地址栏、没有标签页，
    看起来就是一个独立应用窗口；关掉窗口时我们同步结束整个程序。

为什么不打包 Chromium：
    那会让分发包从 ~100MB 涨到 250-400MB。而 Windows 10/11 自带 Edge，
    实测覆盖绝大多数目标机器，代价几乎为零。

找不到浏览器时怎么办：
    回退到"用默认浏览器打开"，功能不受影响，只是观感差一些。
    绝不因为找不到 Edge 就让程序打不开。
"""
import os
import subprocess
import sys
import threading
import time

# Chromium 系浏览器的常见安装位置
_EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    # 用户级安装（无需管理员权限的 Chrome）
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_browser():
    """
    找一个能用 --app 模式的 Chromium 系浏览器。

    返回 (可执行文件路径, 名称)；找不到返回 (None, None)。
    """
    for path in _EDGE_CANDIDATES:
        if os.path.exists(path):
            return path, "Edge"
    for path in _CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path, "Chrome"
    return None, None


def _app_profile_dir():
    """
    --app 模式用的独立用户数据目录。

    不这么做的话，会复用用户日常浏览器的会话；万一用户主浏览器正开着，
    Edge 可能把我们的窗口合并进已有进程，导致窗口尺寸/关闭行为不受控。
    用独立目录能保证是干净、独立的进程，关掉即彻底退出。

    注意：这个目录会存 Edge 的缓存，**实测能涨到 200MB+ / 上千个文件**。
    因此它单独放在用户数据目录下的 `browser_profile/`，
    **不要**混进 data/（那里放数据库和配置，体积应保持很小）。
    """
    from paths import user_data_dir
    d = os.path.join(user_data_dir(), "browser_profile")
    os.makedirs(d, exist_ok=True)
    return d


def open_app_window(url, title="六合彩数据分析工具", width=1360, height=900):
    """
    以独立窗口方式打开界面。

    返回 (是否成功, 说明文字)：
      - (True, "Edge")  用 Edge 独立窗口打开
      - (True, "Chrome") 用 Chrome 独立窗口打开
      - (False, 原因)   没找到浏览器，调用方应回退到 webbrowser.open()
    """
    browser, name = find_browser()
    if not browser:
        return False, "未找到 Edge 或 Chrome"

    args = [
        browser,
        f"--app={url}",
        f"--user-data-dir={_app_profile_dir()}",
        # 关掉首次运行的引导页/默认浏览器检查提示
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate,DefaultBrowserSettingEnforcement",
        # 窗口初始尺寸（--app 模式下 window-size 生效）
        f"--window-size={width},{height}",
    ]
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True, name
    except OSError as e:
        return False, f"启动 {name} 失败: {e}"


def wait_for_server(url, timeout=40):
    """等 Flask 真正开始监听；返回 True 表示已就绪"""
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except urllib.error.HTTPError:
            return True  # 有响应即算就绪（哪怕 4xx/5xx）
        except Exception:
            time.sleep(0.35)
    return False


def _show_error_dialog(message):
    """无控制台时，用系统弹窗把致命错误告诉用户（否则程序会静默退出）"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "六合彩数据分析工具", 0x10)
    except Exception:
        print(message, file=sys.stderr)


def _show_info_dialog(message):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "六合彩数据分析工具", 0x40)
    except Exception:
        print(message)


def launch_window(url, on_close, title="六合彩数据分析工具"):
    """
    在后台线程里打开独立窗口，并在窗口关闭时回调 on_close()。

    实现说明：
      --app 模式没有提供"窗口已关闭"的回调，因此这里用最朴素但可靠的
      办法——轮询进程是否还活着。浏览器进程退出即认为窗口关闭。
      轮询间隔 1 秒，开销可忽略。
    """
    browser, name = find_browser()
    if not browser:
        return False, "未找到 Edge 或 Chrome"

    args = [
        browser,
        f"--app={url}",
        f"--user-data-dir={_app_profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate,DefaultBrowserSettingEnforcement",
        "--window-size=1360,900",
    ]

    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        return False, f"启动 {name} 失败: {e}"

    def _watch():
        # 先给浏览器一点启动时间，避免刚 Popen 就判死
        time.sleep(2.0)
        while True:
            if proc.poll() is not None:
                break
            time.sleep(1.0)
        # 浏览器进程结束 = 用户关了窗口 → 结束整个程序
        try:
            on_close()
        except Exception:
            os._exit(0)

    threading.Thread(target=_watch, daemon=True).start()
    return True, name
