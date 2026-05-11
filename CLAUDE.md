# 答题卡小题分匹配系统

## 项目概述

一个基于 Flask + PIL 的桌面 Web 应用，将学生的**小题得分**叠加打印到扫描的**答题卡图片**上，生成带分数的答题卡图片，方便教师进行试卷分析。

**核心流程：** 上传成绩文件(CSV/XLSX) → 上传答题卡扫描件(PDF/JPG) → 条码/文件名匹配学生 → 在答题卡上标记小题分数打印位置 → 批量生成带分数的答题卡图片 → 导出到本地文件夹。

**技术栈：** Python 3 + Flask + Pillow + PyMuPDF(fitz) + pyzbar(条码识别) + PyInstaller(打包为exe)

**打包方式：** `pyinstaller --onefile --add-data "templates;templates" --hidden-import pypinyin --hidden-import openpyxl app.py`

---

## 文件结构

```
learn_cc/
├── app.py              # Flask 后端：API 路由 + 图像处理 + PDF转换 + 条码识别
├── templates/
│   └── index.html      # 前端单页应用：7步向导式UI
├── data/               # 运行时缓存目录（程序启动时自动清理重建）
├── templates_pos/      # 位置模板保存目录（*.json）
├── build/              # PyInstaller 构建产物
├── publish/            # 发布相关
└── CLAUDE.md           # 本文件
```

---

## app.py 详细说明

### 初始化和环境 (第1-142行)

- **第1-28行** — 导入依赖。注意 `pyzbar`、`fitz`(PyMuPDF)、`openpyxl`、`xlrd`、`pypinyin` 均为可选依赖，通过 `HAS_*` 标志控制。
- **第37-48行** — `_check_pyzbar_functional()`: 仅 `import pyzbar` 成功不代表可用，Windows 上还需要 VC++ 运行时。此函数用空图片测试实际解码能力。
- **第75-93行** — Flask 应用初始化。兼容 PyInstaller 打包后的路径（`sys._MEIPASS` 或 `exe/_internal/`）。最大上传限制 1GB。
- **第100-104行** — `jobs` 字典在内存中存储所有任务配置，无持久化。`_shutdown_event` 线程事件用于通知后台线程停止。
- **第107-115行** — `cleanup_data()`: 删除 `data/` 目录并重建。在启动、退出、保存结果后调用。
- **第119-134行** — 信号处理器和 atexit 处理器：先设置 `_shutdown_event` 通知后台线程停止，再执行 `cleanup_data()`。
- **第137-140行** — 仅在主进程中注册信号和清理（避免 multiprocessing spawn 子进程重复执行）。

### 工具函数 (第147-493行)

| 函数 | 行号 | 功能 |
|------|------|------|
| `get_job_dir()` | 147 | 获取任务的数据目录 `data/<job_id>/` |
| `_set_progress()` | 156 | 更新 `jobs[job_id]['progress']` 字典 |
| `_start_async_task()` | 163 | 在 daemon 线程中运行后台任务，自动将结果/错误写入 progress |
| `find_chinese_font()` | 210 | 按优先级遍历系统中文字体路径（Windows/Mac/Linux） |
| `get_xlsx_sheet_names()` | 236 | 获取 xlsx 所有工作表名称 |
| `parse_score_file()` | 258 | 解析成绩文件，自动检测编码（CSV）或使用 openpyxl/xlrd（Excel） |
| `read_barcodes_from_image()` | 307 | 使用 pyzbar 读取条码，支持百分比坐标的裁切区域 |
| `extract_digits_from_filename()` | 341 | 从文件名提取最长连续数字串作为考号 |
| `convert_pdf_to_images()` | 349 | 将 PDF 每页转为 300dpi JPG（旧版函数，现被 `_do_pdf_convert` 替代） |
| `add_scores_to_image()` | 371 | **核心渲染函数**：在图片百分比坐标处绘制分数文本。满分=蓝色，扣分=红色。使用 `anchor='mm'` 居中对齐 |
| `_build_student_output_names()` | 428 | 构建去重后的输出文件名(基于姓名，同班重名加 a/b/c 后缀) |
| `_get_pinyin()` | 466 | 中文姓名转拼音首字母和全拼（供前端模糊搜索用） |
| `_enrich_student_list()` | 478 | 为学生列表添加 `py_initials` 和 `py_full` 搜索字段 |

### 后台任务 Worker (第637-705行)

- **`_render_single_page_worker()`**（模块顶层）：ProcessPoolExecutor 的 worker，渲染 PDF 的**单页**。必须是顶层函数才能被 pickle。每页一个 future，进度按页粒度更新（不能访问父进程的 `_shutdown_event`/`jobs` 等模块状态）。

- **`_do_pdf_convert()`**：PDF 转 JPG 的后台任务。
  - **真正的多进程并行**：用持久化 `ProcessPoolExecutor`（`_get_pdf_executor()` 懒初始化，跨上传共用）。**每页一个 future** 提交到进程池，n 个 worker 进程并行渲染，绕过 GIL。
  - 多个 PDF 顺序处理（前端按 PDF 逐个 POST 上传，每个 PDF 来一个就并行渲它的页）。
  - 小 PDF（< `MP_MIN_PAGES=2` 页）走单进程降级路径，避免无谓的进程间通信开销。
  - **进度更新粒度**：每个页面 future 完成就调用一次 `progress_cb`，避免"图片已经在转换、进度条还在准备中"的假进度。派发前/派发完都更新一次消息（"派发 N 页到 K 进程..." / "worker 进程启动中..."）。
  - **输出命名**：`{全局序号:05d}_{原 PDF stem}.jpg`，全局序号 = 转换开始前 images/ 已有图片数 + 累计已转换页 + 当前页序 + 1。多次上传 / 同名 PDF 重复上传都不会覆盖；自然按上传顺序排序。
  - 单 PDF 错误被隔离记入 `errors`，**不抛异常**。返回 `{converted_pages, pdf_count, errors}`。

- **`_get_pdf_executor()` / `_shutdown_pdf_executor()`**：持久化进程池的生命周期管理。
  - 仅在 `MainProcess` 中创建（避免 spawn 子进程内递归 spawn）。
  - 在 `_signal_handler` 和 `_atexit_cleanup` 中调用 `_shutdown_pdf_executor()` 确保程序退出时释放 worker 进程。
  - `__main__` 入口必须先调用 `multiprocessing.freeze_support()`，PyInstaller 打包后才能正确启动子进程。

- **`_do_barcode_scan()`** (第687行): 扫描所有图片的条码，支持双面模式。
  - 先检查人工匹配记录 → 再用 pyzbar 扫描 → 回退到文件名数字提取。
  - 返回 matched / unmatched / unmatched_students / dup_barcodes 四组结果。

- **`_do_process()`** (第834行): **核心处理函数**。将分数叠加到答题卡图片上。
  - 双面模式：每对学生有 `*1.jpg`(正面) 和 `*2.jpg`(背面) 两张输出。
  - 支持按班级分文件夹输出。
  - 未匹配的图片拷贝到 `unmatched/` 目录。

### API 路由 (第498-1699行)

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 渲染主页面 |
| `/api/init-job` | POST | 创建新的 job_id，初始化目录结构 |
| `/api/upload-scores` | POST | 上传成绩文件，返回预览数据。支持 `sheet_name` 参数切换 xlsx 工作表 |
| `/api/upload-images` | POST | 上传答题卡图片/PDF。PDF 触发 `_do_pdf_convert` 后台任务 |
| `/api/config-scores` | POST | 配置成绩解析参数（跳过行、考号列、姓名列、满分行等） |
| `/api/scan-barcodes` | POST | 扫描条码，支持 `async=true` 后台执行 |
| `/api/manual-match` | POST | 保存人工匹配记录 |
| `/api/save-positions` | POST | 保存分数打印位置坐标（含 x/y 偏移） |
| `/api/process` | POST | 执行匹配和分数叠加，支持 `async=true` 后台执行 |
| `/api/preview-result` | POST | 生成预览图（第一个学生的效果） |
| `/api/save-to-folder` | POST | 将处理结果拷贝到用户指定文件夹，**随后清理所有缓存** |
| `/api/output-file-list/<job_id>` | GET | 列出输出文件 |
| `/api/output-file/<job_id>/path` | GET | 下载单个输出文件 |
| `/api/cleanup/<job_id>` | POST | 手动清理指定 job |
| `/api/preview-image/<job_id>/filename` | GET | 提供图片预览（用于前端 `<img>` 标签） |
| `/api/image-list/<job_id>` | GET | 获取已上传图片列表 |
| `/api/progress/<job_id>` | GET | **轮询进度**：返回 `{task, current, total, message, result/error}` |
| `/api/position-templates/save` | POST | 保存位置模板（JSON 文件到 `templates_pos/`） |
| `/api/position-templates/list` | GET | 列出所有模板 |
| `/api/position-templates/delete/<name>` | POST | 删除指定模板 |
| `/api/position-templates/clear-all` | POST | 清除全部模板 |
| `/api/dependencies` | GET | 返回各依赖库的可用状态 |

### 进度追踪机制

- `_set_progress(job_id, task, current, total, message)` 更新进度字典
- `_start_async_task(job_id, task_name, total, target_fn, *args)` 在后台线程中运行 target_fn，自动管理进度状态
- target_fn 接收 `(job_id, progress_cb, *args)`，通过 `progress_cb(current, message)` 报告进度
- 前端通过轮询 `/api/progress/<job_id>` 获取实时进度并更新进度条
- 任务完成后 progress 的 task 变为 `'done'`（带 result）或 `'error'`（带 error 信息）

---

## index.html 详细说明

单页应用，使用原生 JavaScript（无框架依赖），7 步向导式操作。

### 全局状态变量 (第540-553行)

```javascript
jobId            // 由 /api/init-job 返回的任务 ID
currentStep      // 当前步骤 (1-7)
scoreRows        // 成绩文件数据（原始行）
allImages        // 已上传图片文件名列表
marksFront/Back  // 正/背面标记点数组 [{x, y}]
fullScores       // 满分数组
doubleSided      // 是否双面模式
barcodeRegion    // 条码区域 {x1, y1, x2, y2} 百分比
scanResults      // 条码扫描结果
studentListData  // 学生列表（含拼音字段）
```

### 步骤1：上传成绩文件 (第196-254行)

- 拖拽上传 CSV/XLSX/XLS
- 如果有多个工作表，显示工作表选择器，切换时重新解析
- 数据预览表格（前20行）
- 配置面板：跳过行数、考号列、姓名列、满分行、班级列、小题分起止列
- 点击"确认配置"调用 `/api/config-scores`，成功后跳转步骤2

### 步骤2：上传答题卡 (第257-297行)

- 选择单面/双面模式
- 上传 JPG/PNG/PDF（可多选）。**前端按文件逐个 POST 上传**，每个 PDF 一到后端就触发 `_do_pdf_convert`，后端用持久化 `ProcessPoolExecutor` 把该 PDF 的页面分到多进程并行渲染
- PDF 文件上传后，前端通过 `pollUntilDone()` 轮询本 PDF 的转换进度，完成后再上传下一个
- **转换完成后验证**：对比前后图片数量，若无新增则报错；任务返回值中的 `errors` 列表也展示给用户
- 缩略图网格预览（最多显示20张）
- 可选：框选条码区域（减少误识别）

### 步骤3：人工匹配 (第300-325行)

- 进入步骤3时自动调用 `/api/scan-barcodes`（async 模式，轮询进度）
- 显示匹配汇总：成功数、重复条码数、未匹配学生数
- **重复条码警告**：同一考号被多张答题卡读到，列出冲突
- **未识别试卷列表**：每张试卷显示图片+搜索输入框
- 搜索支持模糊匹配：考号、姓名、拼音首字母、拼音全拼、班级
- 下拉建议列表，点击选择，支持"忽略此试卷"（设为 IGNORE）
- 点击"下一步"提交人工匹配记录

### 步骤4：标记分数位置 (第328-403行)

- 显示正/背面样例图片选择器（双面模式显示两个）
- 位置模板管理：保存/加载/清除（自动保存为时间戳命名）
- X/Y 轴偏移滑块（±10%）
- **点击图片添加标记点**，每个标记显示小题号和"得分/满分"
- **拖拽可移动**标记点
- **Alt 键取消磁吸**（默认磁吸阈值 1.0% 对齐其他标记点）
- 右键撤销最后一个标记点
- 标记列表表格：显示原始坐标和偏移后坐标
- 标记数量达到满分数量时弹窗提醒
- 保存位置时自动保存模板

### 步骤5：处理设置 (第406-442行)

- 匹配方式：条码识别 / 文件名数字匹配
- 字号大小（默认基于模板图片宽度自动计算）
- 是否按班级分文件夹
- 依赖检查：pyzbar 不可用时自动切换为文件名匹配并提示

### 步骤6：成品预览 (第445-465行)

- 进入时自动调用 `/api/preview-result` 生成第一名学生的效果图
- 显示正/背面预览图
- 可返回步骤5调整字号后重新生成

### 步骤7：处理与下载 (第468-501行)

- 进入时自动启动 `startProcess()`（async 模式，轮询进度）
- 处理完成后显示匹配成功数、未匹配学生数、无条码图片数
- **保存到文件夹**：优先使用 File System Access API（`showDirectoryPicker`），fallback 为手动输入路径
- 保存完成后**自动清理服务器缓存**（`/api/cleanup` 或 `/api/save-to-folder`）

### 关键前端函数

| 函数 | 功能 |
|------|------|
| `pollUntilDone(label, total)` | 轮询 `/api/progress/<jobId>`，更新全局进度条，resolve 结果或 reject 错误 |
| `updateProgressUI(progress)` | 更新进度条 UI（百分比 + 文字） |
| `onMatchInput(input, event)` | 人工匹配搜索：在学生列表中模糊匹配并显示下拉建议 |
| `selectMatchStudent()` | 选择一个匹配的学生，填入输入框 |
| `setupMarkImageClick(side)` | 绑定标记图片的点击/右键事件 |
| `snapPosition(x, y, excludeDot, side)` | 磁吸对齐：将标记点吸附到同侧其他标记点的同行/同列 |
| `addMarkDot(x, y, index, side)` | 在图片上创建可拖拽的标记点 DOM 元素 |
| `openZoom(imgSrc)` | 打开全屏图片查看器（支持滚轮缩放 + 拖拽平移） |
| `openBarcodeRegionModal()` | 打开条码区域框选模态框（canvas 绘制矩形） |
| `renderDupBarcodes(dupBarcodes)` | 渲染重复条码警告面板 |

### CSS 关键类

- `.mark-area` — 标记图片容器，子元素 `.mark-dot` 为绝对定位的标记点
- `.img-zoom-overlay` — 全屏图片放大查看器
- `.region-modal-overlay` — 条码区域框选模态框
- `.student-suggestions` — 人工匹配下拉建议列表
- `.progress-wrap` — 全局进度条（固定在页面顶部）
- `.match-grid` / `.match-item` — 人工匹配网格布局

---

## 关键设计决策

1. **内存存储**：jobs 存于内存字典，重启丢失。单用户场景无需持久化。
2. **文件命名**：输出文件名优先使用学生姓名，同班重名加 a/b/c 后缀。
3. **进度轮询**：后台任务通过 `_start_async_task` 在 daemon 线程中运行，前端每 500ms 轮询。
4. **PDF 转换**：用持久化 `ProcessPoolExecutor`（多进程）将单个 PDF 的页面并行渲染，绕过 GIL 实现真正的 CPU 并行。多个 PDF 顺序处理（前端按文件逐个 POST，每来一个就立即在进程池里并行渲它的页面）。输出文件名用全局递增序号 `{seq:05d}_{prefix}.jpg`，多次上传不会覆盖，且按上传顺序自然排序。PyInstaller 打包必须在 `__main__` 开头调用 `multiprocessing.freeze_support()`。
5. **条码识别**：pyzbar 不可用时自动回退为文件名数字提取。支持条码区域裁剪提高准确率。
6. **分数颜色**：满分（得分=满分）显示蓝色，扣分显示红色。
7. **坐标系统**：使用百分比坐标（0-100%），适配不同分辨率的答题卡扫描件。

---

## 常见问题排查

### PDF 转换失败
- 检查 PyMuPDF 是否安装：`pip install pymupdf`
- 检查 PDF 是否损坏或加密
- 查看后台输出的 `traceback.print_exc()` 日志

### 条码无法识别
- 检查 pyzbar 是否安装且可用：访问 `/api/dependencies` 查看 `pyzbar_functional`
- Windows 上 pyzbar 需要 Visual C++ 运行时库
- 尝试框选条码区域提高识别率

### 打包后 exe 无法关闭
- `_shutdown_event` 会通知后台线程停止
- `atexit` 和信号处理器都会触发 `cleanup_data()`
- 如果仍有问题，检查是否有 PyMuPDF 的文件句柄未释放

---

## 维护说明

**⚠️ 任何修改 `app.py` 或 `index.html` 的功能后，必须同步更新本文件的对应章节。** 包括：
- 新增/删除/修改 API 路由时 → 更新 API 路由表
- 新增/修改工具函数时 → 更新工具函数表
- 修改前端步骤逻辑时 → 更新 index.html 各步骤说明
- 新增 JavaScript 函数时 → 更新前端函数表
- 修改 CSS 样式时 → 更新 CSS 关键类说明
- 新增或修改设计决策时 → 更新设计决策章节

本文件供 Claude Code 等 AI 工具在后续对话中快速理解项目全貌，请保持其准确和完整。
