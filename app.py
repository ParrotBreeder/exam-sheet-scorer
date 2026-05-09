"""
答题卡小题分匹配系统 - 主程序
将学生小题分叠加到扫描答题卡上，生成分析用图片
"""
import os
import re
import csv
import json
import sys
import uuid
import atexit
import signal
import shutil
import zipfile
import traceback
from io import BytesIO
from pathlib import Path
from collections import defaultdict

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import numpy as np

# ---- 可选依赖 ----
try:
    from pyzbar import pyzbar
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    import xlrd
    HAS_XLRD = True
except ImportError:
    HAS_XLRD = False

# ---- Flask 初始化 ----
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB

# 兼容 PyInstaller 打包后的路径
if getattr(sys, 'frozen', False):
    if hasattr(sys, '_MEIPASS'):
        # --onefile 或新版 --onedir: 数据在 _MEIPASS / _internal 中
        BASE_DIR = Path(sys._MEIPASS)
    else:
        # 旧版 --onedir: 数据在 exe 同级目录
        exe_dir = Path(sys.executable).parent
        internal_dir = exe_dir / '_internal'
        BASE_DIR = internal_dir if internal_dir.exists() else exe_dir
else:
    BASE_DIR = Path(__file__).parent

DATA_DIR = BASE_DIR / 'data'

# 告诉 Flask 模板和静态文件的位置
app.template_folder = str(BASE_DIR / 'templates')

# 内存中存储 job 配置
jobs = {}


_cleaned = False  # 防止重复清理


def cleanup_data():
    """清理 data 缓存目录（先删后建，保证干净）"""
    data_dir = BASE_DIR / 'data'
    try:
        if data_dir.exists():
            shutil.rmtree(str(data_dir), ignore_errors=True)
        data_dir.mkdir(exist_ok=True)
        print(f'[init] 缓存目录已就绪: {data_dir}')
    except Exception as e:
        print(f'[init] 缓存目录初始化失败: {e}')


def _signal_handler(signum, frame):
    """捕获 Ctrl+C / kill 信号，先清理再退出"""
    global _cleaned
    print(f'\n[signal] 收到信号 {signum}，正在退出...')
    if not _cleaned:
        _cleaned = True
        cleanup_data()
    sys.exit(0)


def _atexit_cleanup():
    """atexit 钩子：仅在未被 signal handler 清理过时才执行"""
    global _cleaned
    if not _cleaned:
        _cleaned = True
        cleanup_data()


# 启动时清理旧缓存（最可靠：即使上次非正常退出也能清掉残留）
cleanup_data()

# 退出时清理（Ctrl+C / 正常退出）
atexit.register(_atexit_cleanup)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ============================================================
#  工具函数
# ============================================================

def get_job_dir(job_id: str) -> Path:
    """获取或创建 job 目录"""
    d = DATA_DIR / job_id
    d.mkdir(exist_ok=True)
    return d


def find_chinese_font(font_size: int) -> ImageFont.FreeTypeFont | None:
    """查找支持中文的字体"""
    font_paths = [
        # Windows 中文字体
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/msyhbd.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simkai.ttf",
        # 通用英文字体
        "C:/Windows/Fonts/arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, font_size)
        except (IOError, OSError):
            continue
    # 最终回退
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def parse_score_file(filepath: str) -> list[list[str]]:
    """
    解析成绩文件 (CSV / XLSX / XLS)
    返回二维列表，每个子列表是一行的各列字符串值
    """
    ext = Path(filepath).suffix.lower()
    rows = []

    if ext == '.csv':
        # 尝试多种编码
        for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'latin-1']:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    reader = csv.reader(f)
                    rows = [list(row) for row in reader]
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

    elif ext in ('.xlsx', '.xls'):
        if ext == '.xlsx' and HAS_OPENPYXL:
            wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            ws = wb.active
            rows = []
            for row in ws.iter_rows():
                rows.append([str(cell.value) if cell.value is not None else '' for cell in row])
            wb.close()
        elif ext == '.xls' and HAS_XLRD:
            wb = xlrd.open_workbook(filepath)
            ws = wb.sheet_by_index(0)
            rows = []
            for r in range(ws.nrows):
                rows.append([str(ws.cell_value(r, c)) if ws.cell_value(r, c) != '' else '' for c in range(ws.ncols)])
        else:
            # 回退：尝试用 csv 读取（某些 xls 其实是 csv）
            for enc in ['utf-8-sig', 'utf-8', 'gbk', 'gb18030']:
                try:
                    with open(filepath, 'r', encoding=enc) as f:
                        reader = csv.reader(f)
                        rows = [list(row) for row in reader]
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue

    # 清理空白
    rows = [[c.strip() for c in row] for row in rows]
    return rows


def read_barcodes_from_image(image: Image.Image) -> list[dict]:
    """读取图片中的条码，返回条码数据列表"""
    if not HAS_PYZBAR:
        return []
    try:
        gray = image.convert('L')
        barcodes = pyzbar.decode(gray)
        results = []
        for bc in barcodes:
            results.append({
                'type': bc.type,
                'data': bc.data.decode('utf-8', errors='ignore'),
                'rect': {
                    'left': bc.rect.left,
                    'top': bc.rect.top,
                    'width': bc.rect.width,
                    'height': bc.rect.height,
                }
            })
        return results
    except Exception:
        return []


def extract_digits_from_filename(filename: str) -> str:
    """从文件名提取连续数字作为可能的考号"""
    digits = re.findall(r'\d+', filename)
    if digits:
        # 返回最长的数字串（通常就是考号）
        return max(digits, key=len)
    return ''


def convert_pdf_to_images(pdf_path: str, output_dir: str) -> list[str]:
    """将 PDF 的每一页转为 JPG 图片，返回图片路径列表"""
    if not HAS_PYMUPDF:
        raise RuntimeError("需要安装 PyMuPDF 来处理 PDF 文件: pip install pymupdf")
    doc = fitz.open(pdf_path)
    image_paths = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        # 300 DPI 渲染
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_path = os.path.join(output_dir, f'pdf_page_{page_num + 1:04d}.jpg')
        pix.save(img_path)
        image_paths.append(img_path)
    doc.close()
    return image_paths


def add_scores_to_image(
    image_path: str,
    x_percentages: list[float],
    y_percentages: list[float],
    texts: list[str],
    font_size: int,
    save_path: str,
    font: ImageFont.FreeTypeFont | None = None,
):
    """在图片指定百分比位置添加小题分文字"""
    if len({len(x_percentages), len(y_percentages), len(texts)}) != 1:
        raise ValueError("坐标列表与文字列表长度必须一致")

    image = Image.open(image_path).convert('RGB')
    width, height = image.size
    draw = ImageDraw.Draw(image)

    if font is None:
        font = find_chinese_font(font_size)
    if font is None:
        raise RuntimeError("无法加载字体")

    for x_pct, y_pct, text in zip(x_percentages, y_percentages, texts):
        x = int(width * x_pct / 100)
        y = int(height * y_pct / 100)

        # 根据得分情况选择颜色
        try:
            parts = text.split('/')
            stu_score = parts[0].strip()
            full_score = parts[1].strip()
            if stu_score == full_score:
                color = (104, 151, 187)  # 蓝色-满分
            else:
                color = (255, 0, 0)      # 红色-扣分
        except Exception:
            color = (255, 0, 0)

        draw.text((x, y), text, font=font, fill=color, anchor='mm')

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    image.save(save_path, 'JPEG', quality=95)


def image_info(image_path: str) -> dict:
    """获取图片基本信息"""
    try:
        img = Image.open(image_path)
        w, h = img.size
        return {'width': w, 'height': h, 'format': img.format, 'mode': img.mode}
    except Exception:
        return {'width': 0, 'height': 0, 'format': '', 'mode': ''}


# ============================================================
#  API 路由
# ============================================================

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/api/init-job', methods=['POST'])
def init_job():
    """初始化新的处理任务"""
    job_id = uuid.uuid4().hex[:12]
    job_dir = get_job_dir(job_id)
    (job_dir / 'scores').mkdir(exist_ok=True)
    (job_dir / 'images').mkdir(exist_ok=True)
    (job_dir / 'output').mkdir(exist_ok=True)
    (job_dir / 'unmatched').mkdir(exist_ok=True)

    jobs[job_id] = {
        'id': job_id,
        'score_file': None,
        'score_rows': [],
        'score_config': None,
        'image_count': 0,
        'positions_front': [],
        'positions_back': [],
        'processed': 0,
        'matched': 0,
        'unmatched_students': [],
        'unmatched_images': [],
        'output_files': [],
        'status': 'init',
    }
    return jsonify({'job_id': job_id})


@app.route('/api/upload-scores', methods=['POST'])
def upload_scores():
    """上传成绩文件并返回预览"""
    job_id = request.form.get('job_id', '')
    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    file = request.files.get('file')
    if not file:
        return jsonify({'error': '未选择文件'}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in ('.csv', '.xls', '.xlsx'):
        return jsonify({'error': f'不支持的文件格式: {ext}，仅支持 CSV / XLS / XLSX'}), 400

    job_dir = get_job_dir(job_id)
    save_path = job_dir / 'scores' / f'score{ext}'
    file.save(str(save_path))

    try:
        rows = parse_score_file(str(save_path))
    except Exception as e:
        return jsonify({'error': f'文件解析失败: {str(e)}'}), 400

    if not rows:
        return jsonify({'error': '文件中未找到任何数据'}), 400

    jobs[job_id]['score_file'] = str(save_path)
    jobs[job_id]['score_rows'] = rows
    jobs[job_id]['score_config'] = None

    # 截取前 20 行作为预览
    preview = rows[:20]
    max_cols = max(len(r) for r in preview) if preview else 0

    return jsonify({
        'total_rows': len(rows),
        'preview_rows': len(preview),
        'max_cols': max_cols,
        'preview': preview,
        'headers': [f'第{i+1}列' for i in range(max_cols)],
    })


@app.route('/api/upload-images', methods=['POST'])
def upload_images():
    """上传答题卡图片"""
    job_id = request.form.get('job_id', '')
    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': '未选择文件'}), 400

    job_dir = get_job_dir(job_id)
    img_dir = job_dir / 'images'
    supported_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.pdf'}

    saved = []
    errors = []

    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in supported_exts:
            errors.append(f'{f.filename}: 不支持的格式')
            continue

        safe_name = secure_filename(f.filename)
        save_path = img_dir / safe_name
        # 避免覆盖
        counter = 1
        while save_path.exists():
            stem = Path(safe_name).stem
            save_path = img_dir / f'{stem}_{counter}{ext}'
            counter += 1
        f.save(str(save_path))
        saved.append(save_path.name)

        # PDF 转图片
        if ext == '.pdf':
            try:
                pdf_images = convert_pdf_to_images(str(save_path), str(img_dir))
                saved.extend([Path(p).name for p in pdf_images])
            except Exception as e:
                errors.append(f'{f.filename}: PDF转换失败 - {str(e)}')

    # 更新 job 状态
    all_images = sorted([
        p.name for p in img_dir.iterdir()
        if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    ])
    jobs[job_id]['image_count'] = len(all_images)

    return jsonify({
        'saved': saved,
        'total_images': len(all_images),
        'images': all_images[:50],   # 前 50 张预览
        'errors': errors,
    })


@app.route('/api/config-scores', methods=['POST'])
def config_scores():
    """配置成绩文件的解析参数"""
    job_id = request.json.get('job_id', '')
    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    config = {
        'skip_rows': request.json.get('skip_rows', 0),
        'id_column': request.json.get('id_column', 0),
        'full_score_row': request.json.get('full_score_row', 0),
        'score_start_column': request.json.get('score_start_column', 5),
        'score_end_column': request.json.get('score_end_column', -1),
        'class_column': request.json.get('class_column', -1),
    }

    rows = jobs[job_id]['score_rows']
    if not rows:
        return jsonify({'error': '请先上传成绩文件'}), 400

    # 应用配置进行解析验证
    try:
        parsed = _parse_scores_with_config(rows, config)
    except Exception as e:
        return jsonify({'error': f'配置验证失败: {str(e)}'}), 400

    jobs[job_id]['score_config'] = config

    return jsonify({
        'student_count': len(parsed['students']),
        'question_count': len(parsed['full_scores']),
        'full_scores': parsed['full_scores'],
        'sample_students': parsed['students'][:5],
    })


def _parse_scores_with_config(rows: list[list[str]], config: dict) -> dict:
    """根据配置解析成绩数据"""
    skip = config['skip_rows']
    id_col = config['id_column']
    full_row = config['full_score_row']
    score_start = config['score_start_column']
    score_end = config['score_end_column']
    class_col = config['class_column']

    if score_end == -1 or score_end is None:
        score_end = max(len(r) for r in rows)

    # 获取满分行
    if full_row < len(rows):
        full_scores = rows[full_row][score_start:score_end]
    else:
        full_scores = []

    # 解析学生数据
    students = []
    for i, row in enumerate(rows):
        if i < skip or i == full_row:
            continue
        if id_col >= len(row) or not row[id_col].strip():
            continue

        student = {
            'row_index': i,
            'student_id': row[id_col].strip(),
            'scores': row[score_start:score_end] if score_start < len(row) else [],
        }
        if class_col >= 0 and class_col < len(row):
            student['class_name'] = row[class_col].strip()
        students.append(student)

    return {
        'full_scores': full_scores,
        'students': students,
    }


@app.route('/api/save-positions', methods=['POST'])
def save_positions():
    """保存分数打印位置坐标"""
    job_id = request.json.get('job_id', '')
    side = request.json.get('side', 'front')  # 'front' 或 'back'
    positions = request.json.get('positions', [])  # [{x: %, y: %}, ...]
    y_offset = request.json.get('y_offset', 0)
    x_offset = request.json.get('x_offset', 0)

    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    # 应用 X / Y 偏移
    adjusted = []
    for p in positions:
        adjusted.append({
            'x': round(p['x'] + x_offset, 2),
            'y': round(p['y'] + y_offset, 2),
        })

    if side == 'front':
        jobs[job_id]['positions_front'] = adjusted
    else:
        jobs[job_id]['positions_back'] = adjusted

    return jsonify({
        'count': len(adjusted),
        'positions': adjusted,
    })


@app.route('/api/process', methods=['POST'])
def process():
    """执行匹配和分数叠加处理"""
    job_id = request.json.get('job_id', '')
    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    job = jobs[job_id]
    config = job.get('score_config')
    if not config:
        return jsonify({'error': '请先配置成绩文件'}), 400

    positions_front = job.get('positions_front', [])
    if not positions_front:
        return jsonify({'error': '请先标记分数打印位置'}), 400

    double_sided = request.json.get('double_sided', False)
    use_barcode = request.json.get('use_barcode', True)
    font_size = request.json.get('font_size', 80)
    create_class_folders = request.json.get('create_class_folders', True)

    positions_back = job.get('positions_back', [])
    if double_sided and not positions_back:
        return jsonify({'error': '双面模式需要标记背面的分数位置'}), 400

    # 解析成绩数据
    rows = job['score_rows']
    parsed = _parse_scores_with_config(rows, config)
    full_scores = parsed['full_scores']
    students = parsed['students']

    job_dir = get_job_dir(job_id)
    img_dir = job_dir / 'images'
    output_dir = job_dir / 'output'
    unmatched_dir = job_dir / 'unmatched'
    output_dir.mkdir(exist_ok=True)
    unmatched_dir.mkdir(exist_ok=True)

    # 获取所有图片
    image_files = sorted([
        p for p in img_dir.iterdir()
        if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    ])

    # 建立图片索引
    # 有条码模式
    image_map = {}  # student_id -> [image_paths]
    unmatched_images = []

    if use_barcode and HAS_PYZBAR:
        for img_file in image_files:
            try:
                img = Image.open(img_file)
                barcodes = read_barcodes_from_image(img)
                if barcodes:
                    sid = barcodes[0]['data'].strip()
                    if sid not in image_map:
                        image_map[sid] = []
                    image_map[sid].append(str(img_file))
                else:
                    unmatched_images.append(img_file.name)
            except Exception:
                unmatched_images.append(img_file.name)
    else:
        # 文件名模式：提取数字作为考号
        for img_file in image_files:
            sid = extract_digits_from_filename(img_file.stem)
            if sid:
                if sid not in image_map:
                    image_map[sid] = []
                image_map[sid].append(str(img_file))
            else:
                unmatched_images.append(img_file.name)

    # 加载字体
    font = find_chinese_font(font_size)
    if font is None:
        return jsonify({'error': '无法加载字体文件，请确认系统中存在中文字体'}), 500

    # 处理每个学生
    output_files = []
    matched_count = 0
    unmatched_students = []

    # 构建考号 -> 学生映射
    student_map = {s['student_id']: s for s in students}

    for sid, img_paths in image_map.items():
        student = student_map.get(sid)
        if student is None:
            # 图片有但成绩没有 -> 拷入无条码
            for p in img_paths:
                shutil.copy(p, unmatched_dir / Path(p).name)
            continue

        student_scores = student['scores']
        class_name = student.get('class_name', 'unknown')

        if double_sided:
            # 双面：每两张图片组成一个学生的正反面
            img_paths_sorted = sorted(img_paths)
            for pair_idx in range(0, len(img_paths_sorted), 2):
                front_img = img_paths_sorted[pair_idx]
                back_img = img_paths_sorted[pair_idx + 1] if pair_idx + 1 < len(img_paths_sorted) else None

                n_front = len(positions_front)
                front_scores = student_scores[:n_front]
                front_texts = []
                for j, s in enumerate(front_scores):
                    fs = full_scores[j] if j < len(full_scores) else '?'
                    front_texts.append(f'{s}/{fs}')

                if create_class_folders:
                    save_dir = output_dir / class_name
                else:
                    save_dir = output_dir
                save_dir.mkdir(exist_ok=True)

                out_front = save_dir / f'{sid}_{matched_count + 1}_front.jpg'
                add_scores_to_image(
                    front_img,
                    [p['x'] for p in positions_front],
                    [p['y'] for p in positions_front],
                    front_texts,
                    font_size,
                    str(out_front),
                    font,
                )
                output_files.append(str(out_front))
                matched_count += 1

                if back_img and positions_back:
                    n_back = len(positions_back)
                    back_scores = student_scores[n_front:n_front + n_back]
                    back_texts = []
                    for j, s in enumerate(back_scores):
                        fs_idx = n_front + j
                        fs = full_scores[fs_idx] if fs_idx < len(full_scores) else '?'
                        back_texts.append(f'{s}/{fs}')

                    out_back = save_dir / f'{sid}_{matched_count}_back.jpg'
                    add_scores_to_image(
                        back_img,
                        [p['x'] for p in positions_back],
                        [p['y'] for p in positions_back],
                        back_texts,
                        font_size,
                        str(out_back),
                        font,
                    )
                    output_files.append(str(out_back))
        else:
            # 单面
            texts = []
            for j, s in enumerate(student_scores):
                if j >= len(positions_front):
                    break
                fs = full_scores[j] if j < len(full_scores) else '?'
                texts.append(f'{s}/{fs}')

            if create_class_folders:
                save_dir = output_dir / class_name
            else:
                save_dir = output_dir
            save_dir.mkdir(exist_ok=True)

            for img_path in img_paths:
                out_path = save_dir / f'{sid}_{matched_count + 1}.jpg'
                pos_x = [p['x'] for p in positions_front]
                pos_y = [p['y'] for p in positions_front]
                add_scores_to_image(
                    img_path, pos_x, pos_y,
                    texts[:len(positions_front)],
                    font_size, str(out_path), font,
                )
                output_files.append(str(out_path))
                matched_count += 1

    # 找出有成绩但没有图片的学生
    for sid, student in student_map.items():
        if sid not in image_map:
            unmatched_students.append({
                'student_id': sid,
                'class_name': student.get('class_name', ''),
            })

    # 更新 job 状态
    job['matched'] = matched_count
    job['unmatched_students'] = unmatched_students
    job['unmatched_images'] = unmatched_images
    job['output_files'] = output_files
    job['status'] = 'done'

    return jsonify({
        'matched': matched_count,
        'unmatched_students': len(unmatched_students),
        'unmatched_images': len(unmatched_images),
        'output_files': [str(Path(f).relative_to(output_dir)) for f in output_files[:100]],
    })


@app.route('/api/preview-result', methods=['POST'])
def preview_result():
    """生成一张预览图，用于检查位置和字号效果"""
    job_id = request.json.get('job_id', '')
    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    job = jobs[job_id]
    config = job.get('score_config')
    if not config:
        return jsonify({'error': '请先配置成绩文件'}), 400

    positions_front = job.get('positions_front', [])
    if not positions_front:
        return jsonify({'error': '请先在步骤3标记分数位置'}), 400

    font_size = request.json.get('font_size', 80)
    double_sided = request.json.get('double_sided', False)
    positions_back = job.get('positions_back', [])

    # 解析成绩获取第一名学生的小题分
    rows = job['score_rows']
    parsed = _parse_scores_with_config(rows, config)
    if not parsed['students']:
        return jsonify({'error': '无学生数据'}), 400

    student = parsed['students'][0]
    full_scores = parsed['full_scores']
    student_scores = student['scores']

    # 取第一张图片作为背景
    img_dir = get_job_dir(job_id) / 'images'
    image_files = sorted([
        p for p in img_dir.iterdir()
        if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    ])
    if not image_files:
        return jsonify({'error': '请先上传答题卡图片'}), 400

    # 选择预览图片（可通过参数指定）
    preview_img_name = request.json.get('image_name', '')
    if preview_img_name:
        preview_path = img_dir / preview_img_name
        if not preview_path.exists():
            preview_path = image_files[0]
    else:
        preview_path = image_files[0]

    font = find_chinese_font(font_size)
    if font is None:
        return jsonify({'error': '无法加载字体'}), 500

    # 构建正面文字（得分/满分）
    n_front = len(positions_front)
    front_texts = []
    for j in range(n_front):
        s = student_scores[j] if j < len(student_scores) else '?'
        fs = full_scores[j] if j < len(full_scores) else '?'
        front_texts.append(f'{s}/{fs}')

    job_dir = get_job_dir(job_id)
    out_path = str(job_dir / 'preview_front.jpg')
    add_scores_to_image(
        str(preview_path),
        [p['x'] for p in positions_front],
        [p['y'] for p in positions_front],
        front_texts,
        font_size,
        out_path,
        font,
    )

    # 如果是双面，生成背面预览
    back_path = None
    if double_sided and positions_back:
        back_texts = []
        for j in range(len(positions_back)):
            idx = n_front + j
            s = student_scores[idx] if idx < len(student_scores) else '?'
            fs = full_scores[idx] if idx < len(full_scores) else '?'
            back_texts.append(f'{s}/{fs}')

        # 尝试找第二张图片
        back_img = image_files[1] if len(image_files) > 1 else image_files[0]
        back_out = str(job_dir / 'preview_back.jpg')
        add_scores_to_image(
            str(back_img),
            [p['x'] for p in positions_back],
            [p['y'] for p in positions_back],
            back_texts,
            font_size,
            back_out,
            font,
        )
        back_path = '/api/preview-image/' + job_id + '/preview_back.jpg'

    return jsonify({
        'front_preview_url': '/api/preview-image/' + job_id + '/preview_front.jpg',
        'back_preview_url': back_path,
    })


@app.route('/api/save-to-folder', methods=['POST'])
def save_to_folder():
    """将处理结果拷贝到用户指定文件夹，然后清理所有缓存"""
    job_id = request.json.get('job_id', '')
    target_path = (request.json.get('target_path') or '').strip()

    if not job_id or job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400
    if not target_path:
        return jsonify({'error': '请指定保存路径'}), 400

    job = jobs[job_id]
    output_dir = get_job_dir(job_id) / 'output'
    unmatched_dir = get_job_dir(job_id) / 'unmatched'

    if not output_dir.exists() or not any(output_dir.iterdir()):
        return jsonify({'error': '没有可保存的结果'}), 400

    # 确保目标目录存在
    target = Path(target_path)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return jsonify({'error': f'无法创建目标目录: {str(e)}'}), 400

    copied_files = 0
    errors = []

    # 拷贝已匹配的图片
    match_dir = target / '已匹配'
    try:
        match_dir.mkdir(exist_ok=True)
        for root, dirs, files in os.walk(str(output_dir)):
            for fn in files:
                src = Path(root) / fn
                rel = Path(root).relative_to(str(output_dir))
                dst_dir = match_dir / rel
                dst_dir.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), str(dst_dir / fn))
                    copied_files += 1
                except Exception as e:
                    errors.append(f'拷贝失败 {fn}: {str(e)}')
    except Exception as e:
        errors.append(f'创建"已匹配"目录失败: {str(e)}')

    # 拷贝无条码图片
    if unmatched_dir.exists():
        unmatched_target = target / '无条码'
        try:
            for fn in os.listdir(str(unmatched_dir)):
                src = unmatched_dir / fn
                if src.is_file():
                    unmatched_target.mkdir(exist_ok=True)
                    try:
                        shutil.copy2(str(src), str(unmatched_target / fn))
                        copied_files += 1
                    except Exception as e:
                        errors.append(f'拷贝失败 {fn}: {str(e)}')
        except Exception as e:
            errors.append(f'拷贝"无条码"失败: {str(e)}')

    # 清理所有缓存
    cleanup_data()
    jobs.pop(job_id, None)

    return jsonify({
        'copied_files': copied_files,
        'target_path': str(target),
        'errors': errors,
    })


@app.route('/api/output-file-list/<job_id>')
def output_file_list(job_id):
    """列出所有输出文件，供前端下载"""
    if job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    job_dir = get_job_dir(job_id)
    output_dir = job_dir / 'output'
    unmatched_dir = job_dir / 'unmatched'

    files = []

    if output_dir.exists():
        for root, dirs, fnames in os.walk(str(output_dir)):
            for fn in fnames:
                src = Path(root) / fn
                rel = str(src.relative_to(output_dir)).replace('\\', '/')
                files.append({
                    'path': '已匹配/' + rel,
                    'size': src.stat().st_size,
                    'type': 'matched',
                })

    if unmatched_dir.exists():
        for fn in os.listdir(str(unmatched_dir)):
            src = unmatched_dir / fn
            if src.is_file():
                files.append({
                    'path': '无条码/' + fn,
                    'size': src.stat().st_size,
                    'type': 'unmatched',
                })

    return jsonify({'files': files})


@app.route('/api/output-file/<job_id>/<path:filepath>')
def output_file_download(job_id, filepath):
    """下载单个输出文件"""
    if job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    job_dir = get_job_dir(job_id)

    parts = filepath.replace('\\', '/').split('/', 1)
    if len(parts) != 2:
        return jsonify({'error': '无效的文件路径'}), 400

    prefix, rest = parts
    if prefix == '已匹配':
        full_path = (job_dir / 'output' / rest).resolve()
    elif prefix == '无条码':
        full_path = (job_dir / 'unmatched' / rest).resolve()
    else:
        return jsonify({'error': '无效的文件路径'}), 400

    # 安全校验：确保路径在 job_dir 内
    if not str(full_path).startswith(str(job_dir.resolve())):
        return jsonify({'error': '路径越界'}), 403

    if not full_path.exists() or not full_path.is_file():
        return jsonify({'error': '文件不存在'}), 404

    return send_file(str(full_path))


@app.route('/api/cleanup/<job_id>', methods=['POST'])
def cleanup_job(job_id):
    """清理指定 job 的缓存数据"""
    if job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    jobs.pop(job_id, None)
    cleanup_data()

    return jsonify({'ok': True})


@app.route('/api/preview-image/<job_id>/<filename>')
def preview_image(job_id, filename):
    """提供图片预览（用于位置标记和成品预览）"""
    if job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    job_dir = get_job_dir(job_id)
    # 先在 images 子目录查找，再在 job 根目录查找
    img_path = job_dir / 'images' / secure_filename(filename)
    if not img_path.exists():
        img_path = job_dir / secure_filename(filename)
    if not img_path.exists():
        return jsonify({'error': '图片不存在'}), 404

    return send_file(str(img_path))


@app.route('/api/image-list/<job_id>')
def image_list(job_id):
    """获取已上传的图片列表"""
    if job_id not in jobs:
        return jsonify({'error': '无效的任务ID'}), 400

    img_dir = get_job_dir(job_id) / 'images'
    images = sorted([
        p.name for p in img_dir.iterdir()
        if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')
    ])
    return jsonify({'images': images})


@app.route('/api/position-templates/save', methods=['POST'])
def save_position_template():
    """保存位置模板供以后复用"""
    name = (request.json.get('name') or 'default').strip()
    positions_front = request.json.get('positions_front', [])
    positions_back = request.json.get('positions_back', [])
    y_offset = request.json.get('y_offset', 0)
    x_offset = request.json.get('x_offset', 0)

    if not positions_front:
        return jsonify({'error': '没有正面位置数据可保存'}), 400

    template_dir = BASE_DIR / 'templates_pos'
    template_dir.mkdir(exist_ok=True)

    safe_name = re.sub(r'[^\w\-]', '_', name)
    data = {
        'name': name,
        'positions_front': positions_front,
        'positions_back': positions_back,
        'y_offset': y_offset,
        'x_offset': x_offset,
    }
    with open(template_dir / f'{safe_name}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({'ok': True, 'name': name})


@app.route('/api/position-templates/list')
def list_position_templates():
    """列出已保存的位置模板"""
    template_dir = BASE_DIR / 'templates_pos'
    if not template_dir.exists():
        return jsonify({'templates': []})

    templates = []
    for p in sorted(template_dir.glob('*.json')):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            templates.append({
                'filename': p.stem,
                'name': data.get('name', p.stem),
                'front_count': len(data.get('positions_front', [])),
                'back_count': len(data.get('positions_back', [])),
                'y_offset': data.get('y_offset', 0),
                'x_offset': data.get('x_offset', 0),
                'positions_front': data.get('positions_front', []),
                'positions_back': data.get('positions_back', []),
            })
        except Exception:
            continue
    return jsonify({'templates': templates})


@app.route('/api/position-templates/delete/<name>', methods=['POST'])
def delete_position_template(name):
    """删除位置模板"""
    template_dir = BASE_DIR / 'templates_pos'
    safe_name = re.sub(r'[^\w\-]', '_', name)
    path = template_dir / f'{safe_name}.json'
    if path.exists():
        path.unlink()
        return jsonify({'ok': True})
    return jsonify({'error': '模板不存在'}), 404


@app.route('/api/position-templates/clear-all', methods=['POST'])
def clear_all_position_templates():
    """清除所有位置模板"""
    template_dir = BASE_DIR / 'templates_pos'
    if template_dir.exists():
        count = 0
        for p in template_dir.glob('*.json'):
            p.unlink()
            count += 1
        return jsonify({'ok': True, 'deleted': count})
    return jsonify({'ok': True, 'deleted': 0})


@app.route('/api/dependencies')
def check_dependencies():
    """检查依赖库状态"""
    return jsonify({
        'pyzbar': HAS_PYZBAR,
        'pymupdf': HAS_PYMUPDF,
        'openpyxl': HAS_OPENPYXL,
        'xlrd': HAS_XLRD,
        'pillow': True,
    })


# ============================================================
#  启动入口
# ============================================================

if __name__ == '__main__':
    import sys
    port = 5000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    print('=' * 50)
    print('  答题卡小题分匹配系统')
    print(f'  打开浏览器访问: http://localhost:{port}')
    print('=' * 50)

    app.run(host='0.0.0.0', port=port, debug=False)
