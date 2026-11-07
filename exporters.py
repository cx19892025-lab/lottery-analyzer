"""
解码记录导出 —— 生成 Word（.docx）与 Excel（.xlsx），含图片。

背景（V1.9.1）：
    用户希望能把解码历史导出成 Word / Excel，且**要带图**。
    前端把选中的记录 POST 过来（含 800px 的 JPEG dataURL），
    这里用 python-docx / openpyxl 组装成文件流返回。

为什么放在后端做：
    浏览器端要生成带图的 docx/xlsx 得引入几百 KB 的第三方库，
    而后端 python-docx / openpyxl 本就随包分发（零额外成本），
    生成的文件也更规范（Word 表格、Excel 内嵌图片都原生支持）。

输入格式（items 为数组，每项）：
    {
      "time": "2026-11-07T09:20:00.000Z",   # ISO 时间
      "source": "AI 识图" | "手动选元素",
      "main": [3, 15, 27, 39],              # 正码
      "special": 29 | null,                 # 特码
      "candidate_count": 8,
      "is_complete": true,
      "description": "画面描述",
      "vision": {...},                      # AI 识别明细（各维度数组）
      "selections": {...},                  # 实际用于解码的元素
      "image": "data:image/jpeg;base64,..." # 可选，800px 存档图
    }
"""
import base64
import io
import re
from datetime import datetime, timezone, timedelta

# 各维度在导出时的中文标签（与前端 vision 字段对应）
_VISION_LABELS = [
    ("animals", "动物"),
    ("colors", "颜色"),
    ("elements", "五行元素"),
    ("directions", "方位"),
    ("objects", "物件"),
    ("numbers", "数字"),
    ("characters", "汉字"),
    ("counts", "数量"),
]

_SEL_LABELS = [
    ("zodiac", "生肖"),
    ("wuxing", "五行"),
    ("color", "色波"),
    ("direction", "方位"),
    ("numbers", "数字"),
    ("count_numbers", "数量"),
    ("keywords", "关键词"),
]


def _local_time(iso_text):
    """ISO 时间 → 本地可读字符串。前端给的是 UTC（带 Z），转成 +08:00 显示。"""
    if not iso_text:
        return ""
    try:
        s = str(iso_text).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # 本工具面向中文用户，固定按东八区显示，避免依赖服务器时区
        dt = dt.astimezone(timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso_text)


def _decode_data_url(data_url):
    """
    'data:image/jpeg;base64,xxxx' → bytes；不是合法 dataURL 时返回 None。

    注意：前端的 canvas.toDataURL 可能因图片跨域而抛异常并传 null，
    所以这里必须容忍 None / 空串 / 格式不对的情况，不能让导出整体失败。
    """
    if not data_url or not isinstance(data_url, str):
        return None
    m = re.match(r"^data:image/[a-zA-Z+]+;base64,(.+)$", data_url, re.S)
    if not m:
        return None
    try:
        return base64.b64decode(m.group(1))
    except (ValueError, TypeError):
        return None


def _numbers_text(item):
    """正码 + 特码 → '3 15 27 39 + 29'；特码缺失时明确标注。"""
    main = item.get("main") or []
    body = "  ".join(f"{int(n):02d}" for n in main)
    sp = item.get("special")
    if sp is None:
        return f"{body}    （候选不足 7 个，无特码）"
    return f"{body}    + {int(sp):02d}"


def _vision_lines(item):
    """把 vision 各维度拼成 '动物：马、羊' 这样的行列表"""
    v = item.get("vision") or {}
    out = []
    for key, label in _VISION_LABELS:
        vals = v.get(key)
        if isinstance(vals, list) and vals:
            out.append(f"{label}：{'、'.join(str(x) for x in vals)}")
    return out


def _selection_lines(item):
    """实际参与解码的元素（手动解码时 vision 为空，靠这个体现用了什么）"""
    s = item.get("selections") or {}
    out = []
    for key, label in _SEL_LABELS:
        vals = s.get(key)
        if isinstance(vals, list) and vals:
            out.append(f"{label}：{'、'.join(str(x) for x in vals)}")
    return out


# ==================== Word ====================

def build_word(items):
    """
    生成 Word 文档：每条记录一张表（左图右信息），适合打印或存档。
    返回 BytesIO。
    """
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # 标题
    h = doc.add_heading("六合彩 · 解码记录", level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta = doc.add_paragraph(
        f"导出时间：{_local_time(datetime.now(timezone.utc).isoformat())}　"
        f"共 {len(items)} 条"
    )
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.runs[0].font.size = Pt(9)
    meta.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    for idx, item in enumerate(items, 1):
        doc.add_paragraph()

        # 小标题：序号 + 时间 + 来源
        title = doc.add_paragraph()
        run = title.add_run(f"{idx}. {_local_time(item.get('time'))}　{item.get('source', '')}")
        run.bold = True
        run.font.size = Pt(11)

        # 号码（醒目）
        nums = doc.add_paragraph()
        r = nums.add_run(_numbers_text(item))
        r.bold = True
        r.font.size = Pt(14)
        r.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)

        # 左图右文
        img_bytes = _decode_data_url(item.get("image"))
        info_lines = []
        if item.get("description"):
            info_lines.append(f"画面描述：{item['description']}")
        info_lines += _vision_lines(item)
        info_lines += _selection_lines(item)
        if not item.get("is_complete"):
            info_lines.append(f"⚠️ 候选仅 {item.get('candidate_count', 0)} 个，未凑满 7 个")

        if img_bytes:
            table = doc.add_table(rows=1, cols=2)
            table.autofit = False
            cell_img, cell_txt = table.rows[0].cells
            try:
                cell_img.paragraphs[0].add_run().add_picture(
                    io.BytesIO(img_bytes), width=Inches(2.6))
            except Exception:
                # 图片损坏不该让整份文档失败
                cell_img.text = "（图片无法嵌入）"
            for line in info_lines:
                p = cell_txt.add_paragraph(line)
                p.runs[0].font.size = Pt(9)
        else:
            for line in info_lines:
                p = doc.add_paragraph(line)
                p.runs[0].font.size = Pt(9)

        # 分隔线
        sep = doc.add_paragraph("─" * 40)
        sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if sep.runs:
            sep.runs[0].font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ==================== Excel ====================

def build_excel(items):
    """
    生成 Excel：一行一条记录，图片嵌入在「图片」列。
    返回 BytesIO。
    """
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "解码记录"

    headers = ["序号", "时间", "来源", "正码", "特码", "候选数", "是否完整",
               "画面描述", "AI 识别元素", "手动选择元素", "图片"]
    ws.append(headers)

    head_fill = PatternFill("solid", fgColor="1F4E79")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    widths = [6, 17, 12, 22, 7, 8, 10, 34, 40, 26, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for idx, item in enumerate(items, 1):
        main = item.get("main") or []
        sp = item.get("special")
        vision_txt = "\n".join(_vision_lines(item))
        sel_txt = "\n".join(_selection_lines(item))

        ws.append([
            idx,
            _local_time(item.get("time")),
            item.get("source", ""),
            " ".join(f"{int(n):02d}" for n in main),
            "" if sp is None else int(sp),
            item.get("candidate_count", 0),
            "是" if item.get("is_complete") else "否（未凑满）",
            item.get("description", ""),
            vision_txt,
            sel_txt,
            "",   # 图片列，下面单独插入
        ])

        row = ws.max_row
        ws.cell(row=row, column=11).alignment = Alignment(horizontal="center")

        # 多行文本要允许换行
        for col in (8, 9, 10):
            ws.cell(row=row, column=col).alignment = Alignment(
                wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 78

        img_bytes = _decode_data_url(item.get("image"))
        if img_bytes:
            try:
                xi = XLImage(io.BytesIO(img_bytes))
                # 等比缩放到高度约 96px（行高 78pt ≈ 104px，略小以免溢出）。
                #
                # 踩过的坑：先读原尺寸算比例，再赋值。若先写 xi.height 再用
                # xi.width * target / xi.height 计算，分母已经是被改过的值，
                # 结果比例算错（实测 800x600 会算成 800x96，横向溢出）。
                orig_w, orig_h = xi.width, xi.height
                if orig_w and orig_h:
                    xi.width, xi.height = int(orig_w * 96 / orig_h), 96
                ws.add_image(xi, f"K{row}")
            except Exception:
                # 图片异常不影响表格数据
                ws.cell(row=row, column=11).value = "（图片无法嵌入）"

    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
