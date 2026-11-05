"""
打包脚本 —— 生成可分发的 Windows 文件夹版（onedir）。

用法：
    python build_exe.py              # 正常打包（含当前 API 配置）
    python build_exe.py --no-key     # 打包但清空 API Key（安全版）

产出：
    dist/六合彩分析工具/
        ├── 六合彩分析工具.exe
        ├── _internal/          依赖与静态资源
        ├── browser/            随包分发的独立 Chromium（见下）
        └── data/
            ├── lottery.db      4404 期初始数据
            ├── settings.json   预置配置（可能含分享者的 Key）
            └── SHARED_BUILD    标记"Key 由分享者提供"，设置页据此提示

把整个 dist/六合彩分析工具/ 目录压缩成 zip 发给别人即可。

关于随包 Chromium（V1.8）：
    早期版本借用用户机器上的 Edge/Chrome 起独立窗口。虽然用了独立
    profile，但 Edge 仍会弹「登录以同步」引导，且与用户日常浏览器
    共用同一套进程与身份体系——**存在影响用户账号的风险**
    （用户实际遇到账号被封）。

    因此改为随包分发一份完整 Chromium，彻底隔离：
    不读用户任何配置、不共享身份、不弹登录提示。
    代价是包体积从 ~51MB 涨到 ~200MB（压缩后）。

    来源：https://storage.googleapis.com/chromium-browser-snapshots/Win_x64/
    已删除其中的 interactive_ui_tests.exe（358MB 测试程序）等无用文件，
    并把 locales 精简为中英文。**不要删除 159.0.8144.0.manifest**——
    它是 SxS 清单，删掉会报「应用程序的并行配置不正确」而无法启动。

⚠️ 安全提醒：默认会带上当前 data/settings.json 里的 API Key，
   拿到包的人可以直接打开该文件看到明文。分享前请确认这是你想要的。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "六合彩分析工具"
DIST_DIR = os.path.join(ROOT, "dist", APP_NAME)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _read_current_settings():
    path = os.path.join(ROOT, "data", "settings.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def build(include_key=True):
    sep = ";" if os.name == "nt" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",                      # 文件夹版：启动快、杀软误报少
        "--name", APP_NAME,
        # 无控制台：双击后直接出现独立窗口，不再有黑框。
        # 代价是看不到 print，因此 app.py 会把输出重定向到
        # 用户数据目录的 startup.log，排错时看那个文件。
        "--windowed",
        # 只读资源打进包
        f"--add-data=templates{sep}templates",
        f"--add-data=static{sep}static",
        f"--add-data=data/lottery.db{sep}data",
        # 这两个是运行时才 import 的（vision.py 里延迟导入 / Flask 间接引用），
        # 显式声明避免漏收
        "--hidden-import=lunardate",
        "--hidden-import=openai",
        # ⚠️ 不要用 --collect-submodules=pandas/numpy：
        #    会把 pandas.tests.* 整个测试套件拖进来（上千个模块），
        #    体积暴涨且拖慢打包几分钟。这两个包 PyInstaller 自带 hook，无需手动收集。
        "--collect-submodules=flask",
        # 排除本机装了但本项目完全用不到的大包。
        # 注意：这台机器上装了 torch / transformers / playwright 等，
        #      不排除的话 PyInstaller 会顺着依赖图把它们全打进去（体积翻十几倍）。
        "--exclude-module=torch",
        "--exclude-module=transformers",
        "--exclude-module=playwright",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=sklearn",
        "--exclude-module=bokeh",
        "--exclude-module=panel",
        "--exclude-module=nbformat",
        "--exclude-module=nbconvert",
        "--exclude-module=jupyter",
        "--exclude-module=IPython",
        "--exclude-module=notebook",
        "--exclude-module=pytest",
        "--exclude-module=openpyxl",
        "--exclude-module=lxml",
        "--exclude-module=PIL",
        "--exclude-module=PyQt5",
        "--exclude-module=PySide6",
        "--exclude-module=tkinter",
        # 连测试包一起排掉（numpy/pandas 的 tests 子包）
        "--exclude-module=numpy.tests",
        "--exclude-module=numpy.f2py",
        "--exclude-module=numpy.testing.tests",
        "--exclude-module=pandas.tests",
        "--exclude-module=pandas.conftest",
        "app.py",
    ]

    print("=" * 62)
    print("  正在打包（首次约需 1-3 分钟）...")
    print("=" * 62)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("\n[失败] PyInstaller 返回非零退出码")
        return 1

    # ---- 补充可写数据目录 ----
    # 数据库与配置不放在 _internal 里，而是 exe 同级 data/，
    # 首次运行时由 paths.ensure_user_data() 复制到 %APPDATA%。
    out_data = os.path.join(DIST_DIR, "data")
    os.makedirs(out_data, exist_ok=True)

    src_db = os.path.join(ROOT, "data", "lottery.db")
    if os.path.exists(src_db):
        shutil.copy2(src_db, os.path.join(out_data, "lottery.db"))
        print(f"[OK] 已放入初始数据 lottery.db ({os.path.getsize(src_db)/1024:.0f} KB)")
    else:
        print("[警告] 未找到 data/lottery.db，包里将没有初始数据")

    settings = _read_current_settings()
    if not include_key:
        settings["api_key"] = ""
        print("[OK] 按 --no-key 要求，已清空 API Key（安全版）")

    if settings:
        with open(os.path.join(out_data, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        has_key = bool(settings.get("api_key"))
        print(f"[OK] 已写入预置配置 settings.json（含 Key：{'是' if has_key else '否'}）")

        if has_key:
            # 标记文件：设置页据此提示"这是分享者的 Key"
            with open(os.path.join(out_data, "SHARED_BUILD"), "w", encoding="utf-8") as f:
                f.write("此包的 API Key 由分享者提供。\n")
            print("[OK] 已写入 SHARED_BUILD 标记（使用者打开设置页会看到提醒）")

    # ---- 随包分发独立 Chromium ----
    # 放在 exe 同级 browser/（不是 _internal/），这样用户看得见、
    # 也能自行替换成别的 Chromium 版本。
    # window.find_bundled_chromium() 按 exe 同级 → 包内 的顺序查找。
    src_browser = os.path.join(ROOT, "browser")
    out_browser = os.path.join(DIST_DIR, "browser")
    if os.path.isdir(src_browser) and os.path.exists(
            os.path.join(src_browser, "chrome.exe")):
        if os.path.isdir(out_browser):
            shutil.rmtree(out_browser)
        shutil.copytree(src_browser, out_browser)
        bsize = sum(
            os.path.getsize(os.path.join(dp, fn))
            for dp, _, fns in os.walk(out_browser) for fn in fns
        )
        print(f"[OK] 已放入独立浏览器 browser/ ({bsize/1024/1024:.0f} MB)")
    else:
        print("[警告] 未找到 browser/chrome.exe，将回退到系统 Edge/Chrome"
              "（会弹登录引导，有账号风险）")

    total = sum(
        os.path.getsize(os.path.join(dp, fn))
        for dp, _, fns in os.walk(DIST_DIR) for fn in fns
    )
    print()
    print("=" * 62)
    print(f"  打包完成：{DIST_DIR}")
    print(f"  总体积  ：{total/1024/1024:.0f} MB")
    print()
    print("  分享方式：把整个「六合彩分析工具」文件夹压缩成 zip 发给对方，")
    print("           对方解压后双击「六合彩分析工具.exe」即可。")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="打包六合彩分析工具为 Windows 可执行程序")
    ap.add_argument("--no-key", action="store_true",
                    help="打包时清空 API Key（安全版，对方需自己填）")
    args = ap.parse_args()
    sys.exit(build(include_key=not args.no_key))
