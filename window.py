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


def find_bundled_chromium():
    """
    找随包分发的独立 Chromium（首选）。

    为什么要自带浏览器（V1.8）：
      早期版本借用用户机器上的 Edge/Chrome，虽然用了独立 profile，
      但 Edge 仍会弹「登录以同步」引导，且与用户日常浏览器共用同一套
      进程与身份体系——**存在影响用户账号的风险**（用户实际遇到账号被封）。

      自带一份 Chromium 可以彻底隔离：不读用户的任何配置、不共享任何
      身份信息、不弹登录提示。代价是分发包从 ~51MB 涨到 ~300MB。

    查找顺序：
      1. exe 同级 browser/          —— 打包时放的（用户可见，可自行替换）
      2. 包内 browser/              —— PyInstaller 的 _internal 里
      3. 开发时项目根 browser/      —— 源码运行
    """
    from paths import resource_path, exe_dir

    candidates = [
        os.path.join(exe_dir(), "browser", "chrome.exe"),
        resource_path("browser", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path, "内置 Chromium"
    return None, None


def find_browser():
    """
    找一个能用 --app 模式的浏览器。

    优先用**随包自带的 Chromium**（完全独立，不碰用户账号）；
    找不到才回退到系统 Edge/Chrome（并施加更严格的禁登录参数）。

    返回 (可执行文件路径, 名称)；找不到返回 (None, None)。
    """
    bundled, bname = find_bundled_chromium()
    if bundled:
        return bundled, bname

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


# 禁登录 / 禁同步 / 禁各类"引导"的参数。
# 这些参数对内置 Chromium 与系统 Edge/Chrome 都适用。
# 目的：不让程序弹出任何账号、登录、同步相关的东西。
# 即使用户手动去点"登录"，请求也到不了微软/谷歌的账号服务。
_NO_ACCOUNT_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-sync",                      # 关闭同步（登录后才会用到）
    "--disable-background-networking",     # 不后台连账号/更新服务
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-client-side-phishing-detection",
    "--disable-features=" + ",".join([
        "Translate",
        "DefaultBrowserSettingEnforcement",
        # Edge 的账号/同步相关特性
        "msEdgeIdentityFeature",
        "msImplicitSignin",
        "msSync",
        "EdgeSync",
        "SigninAllowed",
        "SyncDisabled",
        "EdgeCollections",
        "EdgeShoppingAssistant",
        "ShowRecommendations",
        "EdgeSidebar",
        # Chrome 的登录引导
        "ChromeSignin",
        "AccountConsistency",
        "SyncPromoUI",
        "SignInProfileCreation",
    ]),
    "--disable-background-mode",
    "--no-service-autorun",
    "--password-store=basic",              # 不碰系统凭据库
    "--use-mock-keychain",
]


def open_app_window(url, title="六合彩数据分析工具", width=1360, height=900):
    """
    以独立窗口方式打开界面。

    返回 (是否成功, 说明文字)：
      - (True, "内置 Chromium") 用随包自带的独立浏览器（首选）
      - (True, "Edge"/"Chrome") 回退到系统浏览器
      - (False, 原因)           没找到浏览器，调用方应回退到 webbrowser.open()
    """
    browser, name = find_browser()
    if not browser:
        return False, "未找到内置 Chromium，也没有 Edge 或 Chrome"

    args = [
        browser,
        f"--app={url}",
        f"--user-data-dir={_app_profile_dir()}",
        # 窗口初始尺寸（--app 模式下 window-size 生效）
        f"--window-size={width},{height}",
    ] + _NO_ACCOUNT_FLAGS
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


def _find_app_windows(profile_dir):
    """
    查找属于本程序 profile 的**可见顶层窗口**。

    为什么不看 Popen 的进程：
      Edge 是多进程架构。如果用户机器上已经有 Edge 在跑，我们 Popen 出来的
      那个"启动器"进程会立刻把请求转交给已有进程然后**自己退出**。
      若据此判断"窗口已关闭"，程序会在打开约 2 秒后自杀
      （V1.5.1 的真实 Bug，表现为界面加载到一半就 "Failed to fetch"）。

    所以改为按窗口来判断：枚举所有可见顶层窗口，
    用窗口所属进程的**命令行里是否含我们的 profile 目录**来识别。
    只要还有一个这样的窗口存在，就认为程序在运行。

    性能：进程→profile 的匹配结果按 pid 缓存，避免每次轮询都查进程命令行。

    返回窗口句柄列表。
    """
    import ctypes
    from ctypes import wintypes

    # 刷新"属于本程序的浏览器进程"集合（批量查询，约 1 秒），
    # 之后 5 秒内复用，避免每次轮询都查。
    global _profile_pids, _last_refresh
    now = time.time()
    if now - _last_refresh[0] > 5.0:
        _profile_pids = _refresh_browser_pids(profile_dir)
        _last_refresh[0] = now

    user32 = ctypes.windll.user32
    handles = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )

    def _enum(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        # 只看有标题的窗口，过滤掉 IME / HintWnd 之类的辅助窗口
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _process_matches_profile(pid.value, profile_dir):
            handles.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(_enum), 0)
    return handles


# pid -> 是否属于本程序 profile 的缓存。
# 一次运行内进程身份不会变，缓存可避免反复查命令行。
_profile_pid_cache = {}

# 窗口句柄 -> 是否属于本程序（窗口句柄在同一窗口生命周期内稳定）
_window_cache = {}


def _refresh_browser_pids(profile_dir):
    """
    查出所有属于本程序 profile 的浏览器进程 pid。

    **不使用 PowerShell / wmic**：实测在 PATH 被精简的环境下
    （例如打包运行时）`powershell` 无法解析，查询会静默失败并返回空集合，
    导致窗口检测误判"窗口已关闭"而让程序自杀。
    这里改用 Win32 原生 API（NtQueryInformationProcess 读 PEB 命令行），
    毫秒级、无外部依赖。

    返回 pid 集合；任何异常都返回空集合（调用方需能容忍）。
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    TH32CS_SNAPPROCESS = 0x00000002
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    pids = set()
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return pids

    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return pids
        while True:
            exe = entry.szExeFile.decode("mbcs", errors="ignore").lower()
            if exe in ("msedge.exe", "chrome.exe"):
                cmd = _read_process_cmdline(entry.th32ProcessID)
                if cmd and profile_dir.lower() in cmd.lower():
                    pids.add(entry.th32ProcessID)
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)

    return pids


def _read_process_cmdline(pid):
    """
    读取指定进程的完整命令行（含参数）。

    原理：OpenProcess → NtQueryInformationProcess 取 PEB 地址 →
    ReadProcessMemory 读 PEB → 取 ProcessParameters → 读 CommandLine。
    这是获取他进程命令行的标准做法，不需要管理员权限
    （只要目标进程同用户、且用 PROCESS_QUERY_LIMITED_INFORMATION 打开）。
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    PROCESS_VM_READ = 0x0010

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", ctypes.c_void_p),
        ]

    class PROCESS_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Reserved1", ctypes.c_void_p),
            ("PebBaseAddress", ctypes.c_void_p),
            ("Reserved2", ctypes.c_void_p * 2),
            ("UniqueProcessId", ctypes.c_void_p),
            ("Reserved3", ctypes.c_void_p),
        ]

    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid
    )
    if not handle:
        return None

    try:
        pbi = PROCESS_BASIC_INFORMATION()
        status = ntdll.NtQueryInformationProcess(
            handle, 0, ctypes.byref(pbi), ctypes.sizeof(pbi), None
        )
        if status != 0 or not pbi.PebBaseAddress:
            return None

        # 64 位下 PEB->ProcessParameters 偏移 0x20
        ptr_size = ctypes.sizeof(ctypes.c_void_p)
        params_off = 0x20 if ptr_size == 8 else 0x10
        params_ptr = ctypes.c_void_p()
        if not kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(pbi.PebBaseAddress + params_off),
            ctypes.byref(params_ptr), ptr_size, None
        ):
            return None
        if not params_ptr.value:
            return None

        # RTL_USER_PROCESS_PARAMETERS->CommandLine 偏移 0x70（64 位）/ 0x40（32 位）
        cmd_off = 0x70 if ptr_size == 8 else 0x40
        us = UNICODE_STRING()
        if not kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(params_ptr.value + cmd_off),
            ctypes.byref(us), ctypes.sizeof(us), None
        ):
            return None
        if not us.Buffer or us.Length == 0:
            return None

        buf = ctypes.create_unicode_buffer(us.Length // 2 + 1)
        if not kernel32.ReadProcessMemory(
            handle, ctypes.c_void_p(us.Buffer), buf, us.Length, None
        ):
            return None
        return buf.value
    except Exception:
        return None
    finally:
        kernel32.CloseHandle(handle)


def _process_matches_profile(pid, profile_dir):
    """该进程是否属于本程序 profile（走批量查询得到的缓存）"""
    if not pid:
        return False
    return pid in _profile_pids


# 属于本程序 profile 的浏览器 pid 集合（由 _refresh_browser_pids 刷新）
_profile_pids = set()
_last_refresh = [0.0]


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
      办法——轮询窗口是否还存在（按 profile 归属识别）。
      轮询间隔 1.5 秒，开销可忽略。

    ⚠️ 不要在这里另写一份启动参数。历史上这里和 open_app_window()
       各有一份 args 列表，V1.8 加禁登录参数时只改了其中一处，
       导致实际生效的仍是旧参数（排查花了很久）。
       统一走 open_app_window()，只有一处需要维护。
    """
    profile = _app_profile_dir()

    ok, name = open_app_window(url, title=title)
    if not ok:
        return False, name

    def _watch():
        # 第一阶段：等窗口出现（最多 30 秒）。
        # 不能一 Popen 就判定，因为浏览器启动需要时间。
        appeared = False
        for _ in range(60):
            time.sleep(0.5)
            if _find_app_windows(profile):
                appeared = True
                break

        if not appeared:
            # 窗口一直没出现：可能是浏览器启动失败，
            # 但服务本身还在，用户仍可手动访问，所以不退出程序。
            print("[警告] 未检测到应用窗口，服务仍在运行，可手动访问界面")
            sys.stdout.flush() if sys.stdout else None
            return

        # 第二阶段：窗口出现后，持续监视它是否还存在。
        # 连续 3 次查不到才认定关闭，避免窗口重绘/切换时的瞬时抖动误判。
        misses = 0
        while True:
            time.sleep(1.5)
            if _find_app_windows(profile):
                misses = 0
            else:
                misses += 1
                if misses >= 3:
                    break

        # 窗口确实关闭了 → 结束整个程序
        try:
            on_close()
        except Exception:
            os._exit(0)

    threading.Thread(target=_watch, daemon=True).start()
    return True, name
