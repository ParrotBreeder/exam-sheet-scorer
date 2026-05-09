from pyzbar import pyzbar
from PIL import Image, ImageDraw, ImageFont
import os
import csv
import re
import numpy as np

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
    if i.endswith('.jpg'):
        tmp = re.findall(r'\d+', i)
        img[tmp[0]] = i

with open('小题分.csv', 'r', encoding='utf-8') as f:
    score = csv.reader(f)
    score = list(score)



pos_data = """
坐标百分比: X: 9.07%, Y: 3.45%
坐标百分比: X: 17.85%, Y: 3.45%
坐标百分比: X: 25.18%, Y: 3.45%
坐标百分比: X: 13.70%, Y: 39.00%
坐标百分比: X: 16.48%, Y: 42.00%
坐标百分比: X: 28.70%, Y: 41.30%
坐标百分比: X: 13.51%, Y: 46.47%
坐标百分比: X: 15.83%, Y: 51.27%
坐标百分比: X: 29.53%, Y: 51.27%
坐标百分比: X: 14.44%, Y: 56.40%
坐标百分比: X: 29.53%, Y: 56.40%
坐标百分比: X: 15.27%, Y: 60.86%
坐标百分比: X: 16.57%, Y: 67.12%
坐标百分比: X: 13.70%, Y: 70.85%
坐标百分比: X: 27.12%, Y: 70.85%
坐标百分比: X: 15.83%, Y: 75.78%
坐标百分比: X: 13.70%, Y: 79.11%
坐标百分比: X: 27.03%, Y: 79.11%
坐标百分比: X: 15.37%, Y: 85.90%
坐标百分比: X: 29.16%, Y: 85.90%
坐标百分比: X: 15.92%, Y: 89.10%
坐标百分比: X: 29.62%, Y: 89.10%
坐标百分比: X: 46.38%, Y: 12.51%
坐标百分比: X: 59.53%, Y: 12.51%
坐标百分比: X: 43.05%, Y: 16.64%
坐标百分比: X: 59.25%, Y: 16.64%
坐标百分比: X: 44.71%, Y: 22.50%
坐标百分比: X: 46.01%, Y: 26.70%
坐标百分比: X: 60.08%, Y: 30.56%
坐标百分比: X: 60.08%, Y: 49.14%
坐标百分比: X: 60.08%, Y: 66.85%
坐标百分比: X: 76.93%, Y: 12.57%
坐标百分比: X: 88.87%, Y: 12.57%
坐标百分比: X: 76.28%, Y: 17.70%
坐标百分比: X: 92.30%, Y: 17.70%
坐标百分比: X: 90.60%, Y: 21.50%
坐标百分比: X: 90.60%, Y: 46.61%
"""

pos_x = np.array(list(map(float, re.findall(r"X: (.*?)%", pos_data))))
pos_y = np.array(list(map(float, re.findall(r"Y: (.*?)%", pos_data))))

pos_y -= 2

for i in range(len(score)):
    if i <= 1:
        continue
    if not img.get(score[i][1]):
        continue
    text = []
    for j in range(5, len(score[i])):
        text.append(f"{score[i][j]}/{score[1][j]}")
    add_text_to_image(
        image_path=img[score[i][1]],
        x_percentages=list(pos_x),
        y_percentages=list(pos_y),
        texts=text,
        font_size=80,
        save_path=f"{str(int(score[i][3][4:6]))}\\{score[i][2]}.jpg",
        text_color=(255, 0, 0),
        font_path="arial.ttf"
    )


