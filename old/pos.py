import matplotlib.pyplot as plt
from PIL import Image


def main():
    # 读取图片文件
    image_path = "Image_001_1.jpg"
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"无法读取图片：{e}")
        return

    # 获取图片原始尺寸
    width, height = img.size

    # 创建图形窗口
    fig, ax = plt.subplots()
    ax.set_title("点击图片获取坐标百分比 (ESC退出)")
    ax.imshow(img)

    # 定义点击事件处理函数
    def on_click(event):
        if event.xdata is None or event.ydata is None:
            return

        # 计算百分比坐标（保留两位小数）
        x_percent = (event.xdata / width) * 100
        y_percent = (event.ydata / height) * 100

        # 输出结果（左上角为原点）
        print(f"坐标百分比: X: {x_percent:.2f}%, Y: {y_percent:.2f}%")

    # 绑定事件监听器
    fig.canvas.mpl_connect('button_press_event', on_click)
    plt.show()


if __name__ == "__main__":
    main()