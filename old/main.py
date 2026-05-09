import shutil

from pyzbar import pyzbar
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import os
import csv
import re
import numpy as np

def crop_image_by_percentage(image, left_percentage, top_percentage, right_percentage, bottom_percentage):
    try:
        # 打开图片
        width, height = image.size

        # 计算实际的坐标
        left = int(width * left_percentage/100)
        top = int(height * top_percentage/100)
        right = int(width * right_percentage/100)
        bottom = int(height * bottom_percentage/100)

        # 截取图片
        cropped_image = image.crop((left, top, right, bottom))

        # 保存截取后的图片
        return cropped_image
    except:
        pass
def read_barcodes(image_path):
    try:
        # 打开并预处理图像
        img = Image.open(image_path).convert('L')  # 转换为灰度图像
    except Exception as e:
        print(f"无法读取图片: {e}")
        return []

    img = crop_image_by_percentage(img, 20.83, 16.23, 34.80, 30)
    img = ImageEnhance.Contrast(img).enhance(2)
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
num = 0
for i in os.listdir():
    if i.endswith('.jpg'):
        tmp = read_barcodes(os.path.join('.', i))
        if tmp and len(tmp[0]['data']) == 9:
            img[tmp[0]['data']] = i
        else:
            if not os.path.exists('无条码'):
                os.makedirs('无条码')
            shutil.copy(i, os.path.join('无条码', i))
        num += 1
        if num%10 == 0:
            print(num)
    '''if img:
        break'''
print(len(img))
print(img)

with open('小题分.csv', 'r', encoding='utf-8') as f:
    score = csv.reader(f)
    score = list(score)



pos_data = """
坐标百分比: X: 12.67%, Y: 4.34%
坐标百分比: X: 21.24%, Y: 4.34%
坐标百分比: X: 28.69%, Y: 4.34%
坐标百分比: X: 11.11%, Y: 37.82%
坐标百分比: X: 17.33%, Y: 37.82%
坐标百分比: X: 27.61%, Y: 37.82%
坐标百分比: X: 23.28%, Y: 45.98%
坐标百分比: X: 27.95%, Y: 45.98%
坐标百分比: X: 22.40%, Y: 50.36%
坐标百分比: X: 26.53%, Y: 50.36%
坐标百分比: X: 28.69%, Y: 53.96%
坐标百分比: X: 13.55%, Y: 78.96%
坐标百分比: X: 25.31%, Y: 78.96%
坐标百分比: X: 11.52%, Y: 83.1%
坐标百分比: X: 20.04%, Y: 83.1%
坐标百分比: X: 27.54%, Y: 83.1%
坐标百分比: X: 15.98%, Y: 89.85%
坐标百分比: X: 60.06%, Y: 10.76%
坐标百分比: X: 45.19%, Y: 31.00%
坐标百分比: X: 44.85%, Y: 37.22%
坐标百分比: X: 60.00%, Y: 40.53%
坐标百分比: X: 38.90%, Y: 59.85%
坐标百分比: X: 47.89%, Y: 59.85%
坐标百分比: X: 58.64%, Y: 59.85%
坐标百分比: X: 43.16%, Y: 64.75%
坐标百分比: X: 50.67%, Y: 64.75%
坐标百分比: X: 58.04%, Y: 64.75%
坐标百分比: X: 44.58%, Y: 70.30%
坐标百分比: X: 60.06%, Y: 73.80%
坐标百分比: X: 75.61%, Y: 10.96%
坐标百分比: X: 81.70%, Y: 10.96%
坐标百分比: X: 87.58%, Y: 10.96%
坐标百分比: X: 76.02%, Y: 16.99%
坐标百分比: X: 81.16%, Y: 20.30%
坐标百分比: X: 76.97%, Y: 24.58%
坐标百分比: X: 90.76%, Y: 29.05%
坐标百分比: X: 84.61%, Y: 47.54%
坐标百分比: X: 90.76%, Y: 51.72%
坐标百分比: X: 76.02%, Y: 89.27%
"""

pos_x = np.array(list(map(float, re.findall(r"X: (.*?)%", pos_data))))
pos_y = np.array(list(map(float, re.findall(r"Y: (.*?)%", pos_data))))

pos_y -= 1.7

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


