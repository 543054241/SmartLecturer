## PDF 讲解流 · Gemini 2.5 Pro

一个基于 Streamlit 的本地应用：批量读取 PDF，逐页调用 Google Gemini 生成中文讲解，在右侧留白区域采用三栏排版合成新 PDF（保持原始 PDF 的矢量内容）。支持批量下载、讲解 JSON 导出/导入与仅合成模式。

### 功能特性
- **批量处理**：一次上传最多 20 个 PDF，逐页生成讲解并合成讲解版 PDF。
- **三栏右侧讲解排版**：新 PDF 宽度为原始的 3 倍，左侧完整保留原始页面矢量内容，右侧 3 栏展示讲解。
- **保持矢量**：通过 PyMuPDF 将原页以矢量方式嵌入新页，避免栅格化导致的模糊。
- **可选 Markdown 渲染**：讲解可按 text 或 markdown 渲染，支持表格、代码块等。
- **自定义 CJK 字体**：默认使用 `assets/fonts/SIMHEI.TTF`，可自定义字体路径。
- **速率控制**：内置 RPM/TPM/RPD 令牌与请求速率控制，减少 429/限流错误。
- **导出/导入讲解 JSON**：可将每页讲解导出为 JSON，再次导入后对同一 PDF 仅做合成。

### 环境要求
- Python 3.10+
- Windows（PowerShell）
- Google Gemini API Key（环境变量 `GEMINI_API_KEY`）

### 快速开始（Windows PowerShell）
1) 克隆/下载本项目，并在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) 设置环境变量（推荐在本机用户环境变量中设置，或使用 `.env` 文件）：

```powershell
$env:GEMINI_API_KEY = "你的_GEMINI_API_KEY"
```

可选：使用 `.env` 文件（注意用支持 UTF-8 无 BOM 的编辑器保存）：

```text
GEMINI_API_KEY=你的_GEMINI_API_KEY
```

3) 启动应用：

```powershell
streamlit run app/streamlit_app.py
```

浏览器将自动打开本地页面。若未自动打开，请访问 `http://localhost:8501`。

### 使用说明
1) 在左侧侧边栏填写或确认参数：
   - **GEMINI_API_KEY**：你的 API Key。
   - **模型名**：默认 `gemini-2.5-pro`。
   - **温度**：默认 0.4。
   - **最大输出 tokens**：默认 4096。
   - **渲染 DPI（仅供 LLM）**：默认 180。用于渲染页面 PNG 输入给模型。
   - **右侧留白比例**：界面参数（当前核心排版采用三栏新宽度=3×原宽度；该参数保留用于后续拓展）。
   - **右栏字体大小**：讲解文本字号（pt）。
   - **讲解文本行距**：行高倍数，默认 1.2。
   - **并发页数**：同时处理页数上限（过大可能触发限流）。
   - **RPM/TPM/RPD**：请求/令牌/日请求限额，防止 429。
   - **讲解风格/要求**：系统提示词，中文讲解&英文关键词。
   - **CJK 字体路径**：默认 `assets/fonts/SIMHEI.TTF`，可换为系统或自定义字体。
   - **右栏渲染方式**：`text` 或 `markdown`。

2) 在主区域上传 1~20 个 PDF。

3) 点击“批量生成讲解与合成”，应用将：
   - 逐页渲染为 PNG（仅供模型识别，不写入结果 PDF）；
   - 调用 Gemini 生成中文讲解；
   - 生成新 PDF：左侧保留原页矢量，右侧三栏布局写入讲解。

4) 下载：
   - 选择“分别下载”将为每个文件提供单独的 PDF 与 JSON 下载；
   - 选择“打包下载”可一次性下载 ZIP（内含讲解版 PDF 与同名 JSON）。

5) 导入讲解 JSON 与仅重新合成：
   - 右侧“导入功能”上传 `.json` 后，点击“仅重新合成（使用导入的讲解）”，可在不调用 LLM 的情况下直接生成讲解版 PDF。

### 目录结构
```text
app/
  services/
    gemini_client.py      # LLM 封装与限流
    pdf_processor.py      # PDF 渲染/合成/讲解生成
  streamlit_app.py        # UI 与批量流程
assets/fonts/SIMHEI.TTF   # 默认中文字体
requirements.txt
```

### 关键实现说明
- `pdf_processor.compose_pdf(...)`：
  - 新页宽度 = 原宽度 × 3；
  - 左侧通过 `show_pdf_page` 嵌入原始矢量内容；
  - 右侧按三栏矩形区域写入讲解；
  - `render_mode=markdown` 时使用 `insert_htmlbox` 渲染（宽容渲染，支持表格/代码）；
  - 文本溢出会自动创建“续页”。
- `gemini_client.GeminiClient`：
  - 使用 `langchain-google-genai` 调用 Gemini；
  - 内置 RPM/TPM/RPD 多维度限流；
  - 失败自动重试（指数回退）。

### 字体与中文显示
- 默认使用 `assets/fonts/SIMHEI.TTF`。如需更换：
  - 在侧边栏将“CJK 字体文件路径”改为你的字体，例如 `C:\Windows\Fonts\msyh.ttc`。
  - 确保路径存在且字体许可允许嵌入。

### 常见问题
- 运行时报缺少包/版本冲突：
  - 建议使用独立虚拟环境，执行 `pip install -r requirements.txt`。
- `streamlit` 无法启动或端口被占用：
  - 尝试 `streamlit run app/streamlit_app.py --server.port 8502`。
- 出现 429 或速率限制：
  - 下调“并发页数”，或提高 `RPM/TPM/RPD` 预算（确保与账号配额一致）。
- 讲解区乱码或中文不成字：
  - 指定可用的 CJK 字体文件路径；或确认导入字体许可及文件存在。
- Markdown 数学公式渲染：
  - 内置对 `$...$`/`$$...$$` 进行简单保护并转义为代码块，防止解析异常；如需严格公式渲染，可改造为更完善的 Math 渲染流程。

### 运行示例（PowerShell）
```powershell
cd C:\Users\Kong\project\lecturer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GEMINI_API_KEY = "你的_GEMINI_API_KEY"
streamlit run app/streamlit_app.py
```

### 辅助脚本
- `check_api.py`：打印并尝试 PyMuPDF 的字体相关 API，便于排查字体嵌入问题：

```powershell
python check_api.py
```

### 测试文件
项目包含若干用于观察渲染与排版效果的脚本与 PDF 示例（如 `test_*.py`、`test_*.pdf`）。你可以逐一运行以验证字体、行距、三栏布局等行为。

### 安全与隐私
- 本地应用，上传的 PDF 仅在本机处理；
- 讲解文本由 Gemini 生成，请遵循你的 API 使用条款与合规要求。

### 许可证
本项目代码仅供学习与研究用途。字体文件请遵循其各自的许可证与使用条款。


