import shutil

from pyzbar import pyzbar
from PIL import Image, ImageDraw, ImageFont
import os
import csv
import re
import numpy as np


def read_barcodes(image_path):
    try:
        # 打开并预处理图像
        img = Image.open(image_path).convert('L')  # 转换为灰度图像
    except Exception as e:
        print(f"无法读取图片: {e}")
        return []

    # 解码条码
    barcodes = pyzbar.decode(img)

    results = []
    for barcode in barcodes:
        # 提取条码数据
        data = barcode.data.decode("utf-8")
        barcode_type = barcode.type
        rect = barcode.rect
        polygon = barcode.polygon

        results.append({
            "type": barcode_type,
            "data": data,
            "position": {
                "left": rect.left,
                "top": rect.top,
                "width": rect.width,
                "height": rect.height
            }
        })

    return results




def add_text_to_image(
        image_path: str,
        x_percentages: list,
        y_percentages: list,
        texts: list,
        font_size: int,
        save_path: str,
        font_path: str = None,
        text_color: tuple = (255, 255, 255)
):
    """
    在图片指定位置添加文字并保存

    参数：
    - image_path: 原始图片路径
    - x_percentages: X轴百分比列表（0-100）
    - y_percentages: Y轴百分比列表（0-100）
    - texts: 要添加的文字列表
    - font_size: 字号大小
    - save_path: 输出图片路径
    - font_path: 字体文件路径（默认尝试系统字体）
    - text_color: 文字颜色（默认白色）

    示例：
    add_text_to_image(
        "input.jpg",
        [10, 50],
        [20, 70],
        ["Hello", "World"],
        30,
        "output.jpg",
        text_color=(0, 0, 0)
    )
    """
    # 验证参数有效性
    if len({len(x_percentages), len(y_percentages), len(texts)}) != 1:
        raise ValueError("坐标列表与文字列表长度必须一致")

    try:
        # 打开并转换图片为RGB模式
        image = Image.open(image_path).convert("RGB")
    except Exception as e:
        raise FileNotFoundError(f"图片加载失败: {str(e)}")

    # 获取图片尺寸
    width, height = image.size

    # 创建绘图对象
    draw = ImageDraw.Draw(image)

    # 加载字体
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            raise ValueError(f"字体文件加载失败: {font_path}")
    else:
        # 尝试常见系统字体路径
        system_fonts = [
            "arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf"
        ]
        for f in system_fonts:
            try:
                font = ImageFont.truetype(f, font_size)
                break
            except IOError:
                continue
        if not font:
            raise RuntimeError("无法加载系统字体，请显式指定字体路径")

    # 添加所有文字
    for x_pct, y_pct, text in zip(x_percentages, y_percentages, texts):
        # 计算绝对坐标
        x = int(width * x_pct / 100)
        y = int(height * y_pct / 100)

        # 绘制文字边界（可选）
        bbox = draw.textbbox((x, y), text, font=font)
        #draw.rectangle(bbox, outline=(30, 30, 30))

        # 绘制文字
        stu_score, full_score = text.split('/')
        if stu_score == full_score:
            draw.text((x, y), text, font=font, fill=(104, 151, 187))
        else:
            draw.text((x, y), text, font=font, fill=(255, 0, 0))

    # 确保输出目录存在
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 保存为JPG
    try:
        image.save(save_path, "JPEG", quality=95)
    except Exception as e:
        raise RuntimeError(f"图片保存失败: {str(e)}")


img = {}

for i in os.listdir():
    if i.endswith('a.jpg'):
        tmp = re.findall(r'\d+', i)
        img[tmp[0] + 'a'] = i
        img[tmp[0] + 'b'] = tmp[0] + 'b.jpg'

with open('小题分.csv', 'r', encoding='utf-8') as f:
    score = csv.reader(f)
    score = list(score)



pos_data1 = """
坐标百分比: X: 16.02%, Y: 4.25%
坐标百分比: X: 13.80%, Y: 41.81%
坐标百分比: X: 12.22%, Y: 45.41%
坐标百分比: X: 12.77%, Y: 48.87%
坐标百分比: X: 14.26%, Y: 52.33%
坐标百分比: X: 16.49%, Y: 56.20%
坐标百分比: X: 13.61%, Y: 60.86%
坐标百分比: X: 15.74%, Y: 64.32%
坐标百分比: X: 20.66%, Y: 71.65%
坐标百分比: X: 11.29%, Y: 76.18%
坐标百分比: X: 27.53%, Y: 80.44%
坐标百分比: X: 30.13%, Y: 88.56%
坐标百分比: X: 42.38%, Y: 15.84%
坐标百分比: X: 60.11%, Y: 19.30%
坐标百分比: X: 61.22%, Y: 24.23%
坐标百分比: X: 44.79%, Y: 29.69%
坐标百分比: X: 42.38%, Y: 33.02%
坐标百分比: X: 61.40%, Y: 38.35%
坐标百分比: X: 52.50%, Y: 48.20%
坐标百分比: X: 44.89%, Y: 84.97%
坐标百分比: X: 56.21%, Y: 89.23%
坐标百分比: X: 77.55%, Y: 17.43%
坐标百分比: X: 80.34%, Y: 23.96%
坐标百分比: X: 80.06%, Y: 31.82%
坐标百分比: X: 79.22%, Y: 38.88%
坐标百分比: X: 76.72%, Y: 47.14%
坐标百分比: X: 79.13%, Y: 53.27%
坐标百分比: X: 90.64%, Y: 53.53%
坐标百分比: X: 80.71%, Y: 60.72%
坐标百分比: X: 81.17%, Y: 68.58%
坐标百分比: X: 76.62%, Y: 76.18%
坐标百分比: X: 91.10%, Y: 88.70%
"""

pos_data2 = """
坐标百分比: X: 18.15%, Y: 16.24%
坐标百分比: X: 14.06%, Y: 23.16%
坐标百分比: X: 14.16%, Y: 28.22%
坐标百分比: X: 24.55%, Y: 31.82%
坐标百分比: X: 24.83%, Y: 43.01%
坐标百分比: X: 23.62%, Y: 51.40%
坐标百分比: X: 20.28%, Y: 60.19%
坐标百分比: X: 23.72%, Y: 80.70%
坐标百分比: X: 59.27%, Y: 15.04%
坐标百分比: X: 45.72%, Y: 22.63%
坐标百分比: X: 60.29%, Y: 31.82%
坐标百分比: X: 60.57%, Y: 38.61%
坐标百分比: X: 45.35%, Y: 45.67%
坐标百分比: X: 56.95%, Y: 51.93%
坐标百分比: X: 45.16%, Y: 59.93%
坐标百分比: X: 55.37%, Y: 64.72%
坐标百分比: X: 47.67%, Y: 71.51%
坐标百分比: X: 45.72%, Y: 78.31%
坐标百分比: X: 59.92%, Y: 82.30%
"""

pos_x1 = np.array(list(map(float, re.findall(r"X: (.*?)%", pos_data1))))
pos_y1 = np.array(list(map(float, re.findall(r"Y: (.*?)%", pos_data1))))
pos_x2 = np.array(list(map(float, re.findall(r"X: (.*?)%", pos_data2))))
pos_y2 = np.array(list(map(float, re.findall(r"Y: (.*?)%", pos_data2))))

pos_y1 -= 1
pos_y2 -= 1

for i in range(len(score)):
    if i <= 1:
        continue
    if not img.get(score[i][1] + 'a'):
        continue
    text1 = []
    text2 = []
    for j in range(5, len(pos_x1) + 5):
        text1.append(f"{score[i][j]}/{score[1][j]}")
    for j in range(len(pos_x1) + 5, len(score[i])):
        text2.append(f"{score[i][j]}/{score[1][j]}")
    add_text_to_image(
        image_path=img[score[i][1] + 'a'],
        x_percentages=list(pos_x1),
        y_percentages=list(pos_y1),
        texts=text1,
        font_size=80,
        save_path=f"{str(int(score[i][3][4:6]))}\\{score[i][2]}1.jpg",
        text_color=(255, 0, 0),
        font_path="arial.ttf"
    )
    add_text_to_image(
        image_path=img[score[i][1] + 'b'],
        x_percentages=list(pos_x2),
        y_percentages=list(pos_y2),
        texts=text2,
        font_size=80,
        save_path=f"{str(int(score[i][3][4:6]))}\\{score[i][2]}2.jpg",
        text_color=(255, 0, 0),
        font_path="arial.ttf"
    )


