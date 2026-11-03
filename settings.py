"""
六合彩数据分析工具 - AI 配置管理

把 AI 接口配置（Base URL / API Key / 模型名）交给用户自己填，
不再依赖本机任何外部脚本或写死的模型名。

配置存放位置由 paths.py 决定：
  - 源码运行：项目 data/settings.json（已 gitignore）
  - 打包运行：%APPDATA%\\LotteryAnalyzer\\settings.json（exe 目录只读，写不进去）

API Key 只写不读：接口返回时一律脱敏，仅显示末 4 位。
"""
import json
import os

from paths import user_data_path, ensure_user_data

SETTINGS_DIR = os.path.dirname(user_data_path("settings.json"))
SETTINGS_PATH = user_data_path("settings.json")

# 分享版标记：打包时在包内放一个 data/SHARED_BUILD 文件，
# 表示"这份配置里的 Key 是分享者提供的，不是使用者自己的"。
# 用户自己保存过一次配置后，标记文件被删除，提示不再出现。
_SHARED_MARKER = "SHARED_BUILD"

# 常见服务商的 OpenAI 兼容接口预设，供前端一键填充
PROVIDER_PRESETS = [
    {
        "id": "deepseek",
        "name": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "note": "国内可直连，需在 platform.deepseek.com 充值",
    },
    {
        "id": "dashscope",
        "name": "阿里云百炼（通义千问）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-vl-plus",
        "note": "qwen3-vl-plus 支持看图；官方价 3 元/M 输入、30 元/M 输出，新用户有免费 token 额度",
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM（免费视觉）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.6v-flash",
        "note": "glm-4.6v-flash 输入/输出/缓存全免费，且支持 image_url 图片输入",
    },
    {
        "id": "moonshot",
        "name": "Moonshot Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
        "note": "kimi-k2.6 支持视觉；输入 6.5 元/M、输出 27 元/M，较贵；K2 系列 12 月底下线",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-VL-72B-Instruct",
        "note": "聚合多家开源模型，有免费额度",
    },
    {
        "id": "openai",
        "name": "OpenAI 官方",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "note": "国内需自备网络条件",
    },
    {
        "id": "ollama",
        "name": "本地 Ollama",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5vl:7b",
        "note": "本机运行，无需联网与 Key（Key 随便填）",
    },
]

DEFAULT_SETTINGS = {
    "base_url": "",
    "api_key": "",
    "model": "",
    "timeout": 60,
    "max_tokens": 1024,
}


def load_settings():
    """读取配置；文件不存在或损坏时返回默认值"""
    if not os.path.exists(SETTINGS_PATH):
        # 打包运行时，包内可能带了一份预置配置（打包者填好的地址/模型/Key），
        # 首次运行复制到用户目录，之后用户改的就是自己这份。
        # SHARED_BUILD 标记一并带过来，用于提示"这是分享者的 Key"。
        ensure_user_data("settings.json", _SHARED_MARKER)
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        if isinstance(data, dict):
            merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        return merged
    except (json.JSONDecodeError, OSError):
        # 配置损坏不应让整个应用起不来
        return dict(DEFAULT_SETTINGS)


def save_settings(patch):
    """
    保存配置。只接受已知字段，避免写入任意内容。
    api_key 为空字符串时表示"保持原值不变"（前端不回显 Key，留空即不改）。
    """
    current = load_settings()
    for key in DEFAULT_SETTINGS:
        if key not in patch:
            continue
        value = patch[key]
        if key == "api_key" and (value is None or str(value).strip() == ""):
            continue  # 留空 = 不修改已存的 Key
        if key in ("timeout", "max_tokens"):
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        current[key] = str(value).strip() if isinstance(value, str) else value

    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    clear_shared_marker()
    return current


def mask_key(key):
    """API Key 脱敏：只保留末 4 位"""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


# 分享版标记：打包时在包内放一个 data/SHARED_BUILD 文件，
# 表示"这份配置里的 Key 是分享者提供的，不是使用者自己的"。
# 用户自己保存过一次配置后，标记文件被删除，提示不再出现。
# （常量定义在文件顶部，见 _SHARED_MARKER）


def _shared_marker_path():
    return os.path.join(SETTINGS_DIR, _SHARED_MARKER)


def is_borrowed_key():
    """
    当前 Key 是否来自分享者预置（而非使用者自己填写）。

    判定：用户目录存在标记文件 且 配置里确实有 Key。
    用户点「保存」后标记被清除（见 save_settings）。
    """
    return os.path.exists(_shared_marker_path()) and bool(load_settings()["api_key"])


def clear_shared_marker():
    """使用者保存过自己的配置后调用，避免每次打开都提示"""
    try:
        os.remove(_shared_marker_path())
    except OSError:
        pass


def public_settings():
    """给前端用的安全视图：绝不返回明文 Key"""
    s = load_settings()
    return {
        "base_url": s["base_url"],
        "model": s["model"],
        "timeout": s["timeout"],
        "max_tokens": s["max_tokens"],
        "api_key_masked": mask_key(s["api_key"]),
        "has_api_key": bool(s["api_key"]),
        "configured": is_configured(s),
        "presets": PROVIDER_PRESETS,
        "borrowed_key": is_borrowed_key(),
    }


def is_configured(settings=None):
    """判断 AI 是否已可用：Base URL 与模型名必填，Key 允许为空（本地 Ollama）"""
    s = settings or load_settings()
    return bool(s["base_url"] and s["model"])


def get_ai_config():
    """供 vision 模块使用的完整配置（含明文 Key）"""
    return load_settings()
