from __future__ import annotations

import io
import asyncio
import json
import os
from typing import Dict, List, Tuple, Optional, Callable
import re

import fitz  # PyMuPDF
from PIL import Image
from markdown import markdown

from .gemini_client import GeminiClient


# 判空：去除空白与标点等装饰字符后长度是否小于阈值
_BLANK_RE = re.compile(r"[\s`~!@#$%^&*()\-_=+\[\]{}|;:'\",.<>/?，。？！、·—【】（）《》“”‘’\\]+")

def is_blank_explanation(text: Optional[str], min_chars: int = 10) -> bool:
	if text is None:
		return True
	s = _BLANK_RE.sub("", str(text))
	return len(s.strip()) < min_chars


def validate_pdf_file(pdf_bytes: bytes) -> Tuple[bool, str]:
	"""
	验证PDF文件是否有效

	Args:
		pdf_bytes: PDF文件字节数据

	Returns:
		(bool, str): (是否有效, 错误信息)
	"""
	try:
		# 尝试打开PDF文件
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")

		# 检查页数
		if doc.page_count == 0:
			doc.close()
			return False, "PDF文件没有页面"

		# 检查第一页是否可以正常访问
		try:
			page = doc.load_page(0)
			if page.rect.width <= 0 or page.rect.height <= 0:
				doc.close()
				return False, "PDF页面尺寸无效"
		except Exception as e:
			doc.close()
			return False, f"无法读取PDF页面: {str(e)}"

		doc.close()
		return True, ""

	except Exception as e:
		return False, f"PDF文件无效或已损坏: {str(e)}"

def pages_with_blank_explanations(explanations: Dict[int, str], min_chars: int = 10) -> List[int]:
	return [p for p, t in explanations.items() if is_blank_explanation(t, min_chars)]


def _smart_text_layout(text: str, column_rects: List[fitz.Rect], font_size: int,
				  fontfile: Optional[str], fontname: str, render_mode: str, line_spacing: float) -> List[str]:
	"""
	智能文本布局：根据栏位实际容量分配文本，避免文字截断

	Args:
		text: 要布局的文本
		column_rects: 3个栏位的矩形区域
		font_size: 字体大小
		fontfile: 字体文件路径
		fontname: 字体名称
		render_mode: 渲染模式

	Returns:
		分配给3个栏位的文本列表
	"""
	if not text.strip():
		return ["", "", ""]

	# 对于短文本，直接放在第一栏
	if len(text) <= 500:
		return [text, "", ""]

	# 创建临时PDF文档来测试文本容量
	temp_doc = fitz.open()
	temp_page = temp_doc.new_page(width=1000, height=1000)  # 临时页面

	def estimate_text_capacity(rect: fitz.Rect) -> int:
		"""估算矩形区域可以容纳的字符数"""
		rect_width = rect.width
		rect_height = rect.height

		# 估算每行字符数（基于字体大小和宽度）
		chars_per_line = int(rect_width / (font_size * 0.6))
		# 估算行数（使用真实行距，保证不低于1.0）
		lines_per_rect = int(rect_height / (font_size * max(1.0, line_spacing)))

		# 增加安全冗余，防止边界裁切
		return int(chars_per_line * lines_per_rect * 0.9)

	# 估算每个栏位的容量
	column_capacities = [estimate_text_capacity(rect) for rect in column_rects]

	# 智能分配文本
	text_parts = ["", "", ""]
	remaining_text = text
	total_capacity = sum(column_capacities)

	# 如果总容量足够放下所有文本，均匀分配
	if len(remaining_text) <= total_capacity:
		# 按容量比例分配
		for i, capacity in enumerate(column_capacities):
			if i == len(column_capacities) - 1:  # 最后一栏
				text_parts[i] = remaining_text
			else:
				# 计算应该分配的字符数
				alloc_chars = int(len(remaining_text) * (capacity / total_capacity))
				if alloc_chars > 0:
					# 尝试在句子或段落边界分割
					alloc_text = remaining_text[:alloc_chars]
					# 寻找合适的分割点（句号、段落等）
					split_pos = alloc_chars
					for sep in ['。', '！', '？', '\n\n', '\n', '；', '：']:
						pos = alloc_text.rfind(sep)
						if pos > alloc_chars * 0.7:  # 分割点不能太靠前
							split_pos = pos + 1
							break

					text_parts[i] = remaining_text[:split_pos]
					remaining_text = remaining_text[split_pos:]
					total_capacity -= capacity
	# 如果文本过长，只填充前两个栏位，第三个栏位留空（会通过续页处理）
	else:
		# 填充前两个栏位
		for i in range(2):
			capacity = column_capacities[i]
			if len(remaining_text) > capacity:
				# 寻找合适的分割点
				alloc_text = remaining_text[:capacity]
				split_pos = capacity
				for sep in ['。', '！', '？', '\n\n', '\n', '；', '：', ' ']:
					pos = alloc_text.rfind(sep)
					if pos > capacity * 0.8:  # 分割点不能太靠前
						split_pos = pos + 1
						break

				text_parts[i] = remaining_text[:split_pos]
				remaining_text = remaining_text[split_pos:]
			else:
				text_parts[i] = remaining_text
				remaining_text = ""

		# 第三个栏位留空，剩余文本将通过续页处理
		text_parts[2] = ""

	temp_doc.close()
	return text_parts


def _page_png_bytes(doc: fitz.Document, pno: int, dpi: int) -> bytes:
	page = doc.load_page(pno)
	mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
	pix = page.get_pixmap(matrix=mat, alpha=False)
	return pix.tobytes("png")


def _compose_vector(dst_doc: fitz.Document, src_doc: fitz.Document, pno: int,
	right_ratio: float, font_size: int, explanation: str,
	font_path: Optional[str] = None,
	render_mode: str = "text", line_spacing: float = 1.4) -> None:
	spage = src_doc.load_page(pno)
	w, h = spage.rect.width, spage.rect.height

	# 处理PDF页面旋转：直接修改页面旋转属性
	rotation = spage.rotation
	if rotation != 0:
		# 临时将页面旋转设为0，避免嵌入时的自动旋转
		original_rotation = rotation
		spage.set_rotation(0)
		# 重新获取页面尺寸（旋转改变后）
		w, h = spage.rect.width, spage.rect.height

	# 新的宽度策略：原PDF:空白区域 = 1:2，3栏布局
	# 总宽度 = 原宽度 × 3
	new_w, new_h = int(w * 3), h
	dpage = dst_doc.new_page(width=new_w, height=new_h)

	# 先始终嵌入原页矢量，保证左侧保留原始内容（0到w位置）
	dpage.show_pdf_page(fitz.Rect(0, 0, w, h), src_doc, pno)

	# 如果修改了旋转，恢复原始旋转
	if rotation != 0:
		spage.set_rotation(original_rotation)
	# 若仅需要右侧留白，不插入任何文本/HTML
	if render_mode == "empty_right":
		return

	# 计算3栏布局参数
	# 右侧区域从w开始到3w结束，减去左右边距后等分3栏
	margin_x, margin_y = 25, 40  # 增大左右边距从15到25像素
	right_start = w + margin_x
	right_end = new_w - margin_x
	available_width = right_end - right_start
	# 使用稳定的间距与宽度计算，防止累计误差导致第2/3栏越界
	column_spacing = 20  # 栏间距（像素）从12增加到20
	total_spacing = column_spacing * 2  # 三栏之间有两处间距
	column_width = max(1, (available_width - total_spacing) / 3)

	# 字体：优先使用提供的 CJK 字体，带错误处理
	fontname = "china"
	fontfile = None
	font_available = False

	if font_path:
		try:
			# 验证字体文件是否存在且可读
			if os.path.exists(font_path) and os.access(font_path, os.R_OK):
				fontfile = font_path
				font_available = True
			else:
				print(f"警告：字体文件不存在或不可读: {font_path}，将使用默认字体")
		except Exception as e:
			print(f"警告：字体文件验证失败: {e}，将使用默认字体")
	else:
		print("信息：未指定字体文件，将使用默认字体")

	# 如果字体不可用，使用系统默认字体
	if not font_available:
		fontname = "helv"  # Helvetica - PyMuPDF默认字体
		fontfile = None

	# 初始放置讲解文本 - 3栏布局
	initial_text = explanation or ""

	# 创建3栏矩形区域，确保右边距正确
	column_rects = []
	# Markdown 渲染在底部增加更大的安全边距，避免 insert_htmlbox 被裁切
	# 自适应紧凑：bottom_safe = clamp(16pt, 1.25×行高, 36pt)
	line_height = font_size * max(1.0, line_spacing)
	bottom_core = int(line_height * 1.25)
	bottom_safe = (min(max(16, bottom_core), 36) if render_mode == "markdown" else 0)
	# 每个栏位内部增加8像素左右边距，避免文字被栏边裁切
	column_internal_margin = 8
	for i in range(3):
		x_left = right_start + i * (column_width + column_spacing)
		x_right = x_left + column_width
		# 增加栏位内部边距，避免文字紧贴边缘被裁切
		rect = fitz.Rect(x_left + column_internal_margin, margin_y,
						min(x_right, right_end) - column_internal_margin,
						new_h - margin_y - bottom_safe - 2)
		column_rects.append(rect)

	# 智能文本布局：根据栏位容量动态分配文本
	text_parts = _smart_text_layout(initial_text, column_rects, font_size, fontfile, fontname, render_mode, line_spacing)

	# 在每一栏中放置文本
	leftovers = []
	for i, (rect, text_part) in enumerate(zip(column_rects, text_parts)):
		if not text_part.strip():  # 空文本跳过
			leftovers.append("")
			continue

		if render_mode == "markdown":
			try:
				import re as _re
				def protect_latex(s: str) -> str:
					s = _re.sub(r"\$\$(.+?)\$\$", r"\n```\n\1\n```\n", s, flags=_re.S)
					s = _re.sub(r"\$(.+?)\$", r"`\1`", s, flags=_re.S)
					return s
				md_text = protect_latex(text_part)
				html = markdown(md_text, extensions=["fenced_code", "tables", "toc", "codehilite"])  # 宽容渲染
				css = f"""
				/* 基本排版 */
				body {{ font-size: {font_size}pt; line-height: {line_spacing}; font-family: 'SimHei','Noto Sans SC','Microsoft YaHei',sans-serif; color: #000000; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word; white-space: normal; }}
				pre, code {{ font-family: 'Consolas','Fira Code',monospace; font-size: {max(8, font_size-1)}pt; color: #000000; }}
				table {{ border-collapse: collapse; width: 100%; }}
				th, td {{ border: 1px solid #ccc; padding: 2pt 4pt; color: #000000; }}
				/* 去除多余的默认外边距，避免底部溢出 */
				body, p, h1, h2, h3, h4, h5, h6, ul, ol, pre, table {{ margin: 0; padding: 0; color: #000000; }}
				ul, ol {{ padding-left: 18pt; }}
				p {{ margin-bottom: 1pt; }}
				"""
				dpage.insert_htmlbox(rect, html, css=css)
				leftovers.append("")  # HTML渲染不支持返回leftover，直接设为空
			except Exception:
				leftover_len = dpage.insert_textbox(rect, text_part, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)
				# insert_textbox返回剩余文本长度，转换为字符串
				if isinstance(leftover_len, (int, float)) and leftover_len > 0:
					# 如果有剩余文本，截取相应长度
					remaining_chars = int(leftover_len / (font_size * 0.6))  # 估算字符数
					leftovers.append(text_part[-remaining_chars:] if remaining_chars < len(text_part) else "")
				else:
					leftovers.append("")
		else:
			leftover_len = dpage.insert_textbox(rect, text_part, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)
			# insert_textbox返回剩余文本长度，转换为字符串
			if isinstance(leftover_len, (int, float)) and leftover_len > 0:
				# 如果有剩余文本，截取相应长度
				remaining_chars = int(leftover_len / (font_size * 0.6))  # 估算字符数
				leftovers.append(text_part[-remaining_chars:] if remaining_chars < len(text_part) else "")
			else:
				leftovers.append("")

	# 检查是否有溢出的文本需要续页
	has_overflow = any(len(leftover) > 0 for leftover in leftovers)
	if has_overflow:
		cpage = dst_doc.new_page(width=new_w, height=new_h)
		header = f"第 {pno + 1} 页讲解 - 续"
		cpage.insert_text(fitz.Point(w + margin_x, margin_y), header, fontsize=font_size, fontname=fontname, fontfile=fontfile)

		# 为续页创建3栏矩形（与主页面保持一致的布局）
		continue_rects = []
		for i in range(3):
			x_left = right_start + i * (column_width + column_spacing)
			x_right = x_left + column_width
			# 续页抬头高度与底部安全边距
			header_h = int(font_size * 1.4)
			rect = fitz.Rect(x_left + column_internal_margin, margin_y + header_h,
							min(x_right, right_end) - column_internal_margin,
							new_h - margin_y - bottom_safe - 2)
			continue_rects.append(rect)

		# 在续页的3栏中放置溢出文本
		for i, (rect, leftover_text) in enumerate(zip(continue_rects, leftovers)):
			if leftover_text:
				cpage.insert_textbox(rect, leftover_text, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)


async def _process_one(pno: int, src_doc: fitz.Document, dpi: int, client: GeminiClient,
					system_prompt: str, right_ratio: float, font_size: int) -> Tuple[int, Optional[str], bytes, Optional[Exception]]:
	img_bytes = _page_png_bytes(src_doc, pno, dpi)
	# 生成预览缩略图（无论是否成功都可展示原页缩略图）
	preview = Image.open(io.BytesIO(img_bytes))
	preview.thumbnail((1024, 1024))
	bio = io.BytesIO()
	preview.save(bio, format="PNG")
	try:
		expl = await client.explain_page(img_bytes, system_prompt)
		return pno, expl, bio.getvalue(), None
	except Exception as e:
		return pno, None, bio.getvalue(), e


def generate_explanations(src_bytes: bytes, api_key: str, model_name: str, user_prompt: str,
				temperature: float, max_tokens: int, dpi: int,
				concurrency: int, rpm_limit: int, tpm_budget: int, rpd_limit: int,
				pages: Optional[List[int]] = None,
				on_progress: Optional[Callable[[int, int], None]] = None,
				on_log: Optional[Callable[[str], None]] = None,
				retry_blank: bool = False,
				blank_min_chars: int = 10,
				blank_retry_times: int = 1) -> Tuple[Dict[int, str], List[bytes], List[int]]:
	# 打开源 PDF
	src_doc = fitz.open(stream=src_bytes, filetype="pdf")
	n_pages = src_doc.page_count

	client = GeminiClient(
		api_key=api_key,
		model_name=model_name,
		temperature=temperature,
		max_output_tokens=max_tokens,
		rpm_limit=rpm_limit,
		tpm_budget=tpm_budget,
		rpd_limit=rpd_limit,
		logger=on_log,
	)

	to_process = pages if pages is not None else list(range(n_pages))

	async def run_all():
		sem = asyncio.Semaphore(concurrency)
		results: List[Tuple[int, Optional[str], bytes, Optional[Exception]]] = []
		total = len(to_process)
		done = 0

		async def worker(i: int):
			nonlocal done
			async with sem:
				return await _process_one(i, src_doc, dpi, client, user_prompt, 0.0, 0)

		pending = [worker(i) for i in to_process]
		for coro in asyncio.as_completed(pending):
			r = await coro
			results.append(r)
			done += 1
			if on_progress:
				on_progress(done, total)
			if on_log:
				ok = (r[1] is not None) and (r[3] is None)
				on_log(f"第 {r[0]+1} 页处理完成：{'成功' if ok else '失败'}")
		return results

	async def run_all_retry(to_retry: List[int]):
		sem = asyncio.Semaphore(concurrency)
		results2: List[Tuple[int, Optional[str], bytes, Optional[Exception]]] = []

		async def worker2(i: int):
			async with sem:
				return await _process_one(i, src_doc, dpi, client, user_prompt, 0.0, 0)

		pending2 = [worker2(i) for i in to_retry]
		for coro in asyncio.as_completed(pending2):
			r = await coro
			results2.append(r)
		return results2

	results = asyncio.run(run_all())
	results.sort(key=lambda x: x[0])

	# 汇总
	explanations: Dict[int, str] = {}
	previews: List[bytes] = []
	failed_pages: List[int] = []
	for pno, expl, preview_png, err in results:
		previews.append(preview_png)
		if err is None and expl is not None:
			explanations[pno] = expl
		else:
			failed_pages.append(pno)

	# 第二阶段：若启用，对空白解释页进行重试（基于当前 explanations 判定）
	if retry_blank and blank_retry_times > 0:
		blank_pages = pages_with_blank_explanations(explanations, min_chars=blank_min_chars)
		if on_log and blank_pages:
			on_log(f"检测到空白解释页，准备重试：{[i+1 for i in blank_pages]}")
		for _ in range(blank_retry_times):
			if not blank_pages:
				break
			retry_results = asyncio.run(run_all_retry(blank_pages))
			# 合并成功项
			for pno, expl, _prev, err in retry_results:
				if err is None and expl:
					explanations[pno] = expl
			# 重新计算仍空白的页
			blank_pages = [pno for (pno, expl, _prev, err) in retry_results
						  if (err is not None) or is_blank_explanation(expl, blank_min_chars)]
			if on_log and blank_pages:
				on_log(f"仍有空白/失败页：{[i+1 for i in blank_pages]}")

	src_doc.close()
	return explanations, previews, failed_pages


def compose_pdf(src_bytes: bytes, explanations: Dict[int, str], right_ratio: float, font_size: int,
                font_path: Optional[str] = None,
                render_mode: str = "text", line_spacing: float = 1.4) -> bytes:
	src_doc = fitz.open(stream=src_bytes, filetype="pdf")
	dst_doc = fitz.open()
	for pno in range(src_doc.page_count):
		expl = explanations.get(pno, "")
		_compose_vector(dst_doc, src_doc, pno, right_ratio, font_size, expl, font_path=font_path, render_mode=render_mode, line_spacing=line_spacing)
	bout = io.BytesIO()
	# 优化PDF保存参数，减小文件大小
	dst_doc.save(bout, deflate=True, clean=True, garbage=4, deflate_images=True, deflate_fonts=True)
	dst_doc.close()
	src_doc.close()
	return bout.getvalue()


def process_pdf(src_bytes: bytes, api_key: str, model_name: str, user_prompt: str,
				temperature: float, max_tokens: int, dpi: int,
				right_ratio: float, font_size: int,
				concurrency: int, rpm_limit: int, tpm_budget: int, rpd_limit: int,
                font_path: Optional[str] = None,
                render_mode: str = "text", line_spacing: float = 1.4) -> Tuple[bytes, Dict[int, str], List[bytes], List[int]]:
	# 先生成讲解
	expl_dict, previews, failed = generate_explanations(
		src_bytes=src_bytes,
		api_key=api_key,
		model_name=model_name,
		user_prompt=user_prompt,
		temperature=temperature,
		max_tokens=max_tokens,
		dpi=dpi,
		concurrency=concurrency,
		rpm_limit=rpm_limit,
		tpm_budget=tpm_budget,
		rpd_limit=rpd_limit,
	)
	# 再合成PDF
	result_pdf = compose_pdf(src_bytes, expl_dict, right_ratio, font_size, font_path=font_path, render_mode=render_mode, line_spacing=line_spacing)
	return result_pdf, expl_dict, previews, failed


def match_pdf_json_files(pdf_files: List[str], json_files: List[str]) -> Dict[str, Optional[str]]:
	"""
	智能匹配PDF文件和JSON文件
	匹配规则：
	1. 移除文件扩展名
	2. 移除常见的序号模式如 (1), (2)等
	3. 完全匹配文件名

	Args:
		pdf_files: PDF文件名列表
		json_files: JSON文件名列表

	Returns:
		字典：PDF文件名 -> 匹配的JSON文件名（如果没有匹配则为None）
	"""
	import re

	def normalize_filename(filename: str) -> str:
		"""标准化文件名用于匹配"""
		# 移除扩展名
		name = filename.rsplit('.', 1)[0] if '.' in filename else filename
		# 移除序号模式如 (1), (2)等
		name = re.sub(r'\s*\(\d+\)\s*$', '', name)
		# 移除多余空格
		name = name.strip()
		return name.lower()

	# 创建标准化名称到原始文件名的映射
	pdf_normalized = {normalize_filename(pdf): pdf for pdf in pdf_files}
	json_normalized = {normalize_filename(json): json for json in json_files}

	# 匹配结果
	matches = {}
	for norm_name, pdf_file in pdf_normalized.items():
		matched_json = json_normalized.get(norm_name)
		matches[pdf_file] = matched_json

	return matches


def batch_recompose_from_json(pdf_files: List[Tuple[str, bytes]], json_files: List[Tuple[str, bytes]],
							right_ratio: float, font_size: int,
							font_path: Optional[str] = None,
							render_mode: str = "text", line_spacing: float = 1.4) -> Dict[str, Dict]:
	"""
	批量根据JSON文件重新合成PDF

	Args:
		pdf_files: [(filename, bytes), ...] PDF文件列表
		json_files: [(filename, bytes), ...] JSON文件列表
		right_ratio: 右侧留白比例
		font_size: 字体大小
		font_path: 字体文件路径
		render_mode: 渲染模式
		line_spacing: 行间距

	Returns:
		处理结果字典
	"""
	# 提取文件名列表用于匹配
	pdf_filenames = [name for name, _ in pdf_files]
	json_filenames = [name for name, _ in json_files]

	# 智能匹配文件
	matches = match_pdf_json_files(pdf_filenames, json_filenames)

	# 创建文件名到内容的映射
	pdf_content_map = {name: content for name, content in pdf_files}
	json_content_map = {name: content for name, content in json_files}

	results = {}

	for pdf_filename, matched_json in matches.items():
		result = {
			"status": "pending",
			"pdf_bytes": None,
			"explanations": {},
			"error": None
		}

		try:
			pdf_bytes = pdf_content_map[pdf_filename]

			if matched_json is None:
				result["status"] = "failed"
				result["error"] = "未找到匹配的JSON文件"
			else:
				json_bytes = json_content_map[matched_json]

				# 解析JSON
				try:
					json_data = json.loads(json_bytes.decode('utf-8'))
					# 转换键为整数
					explanations = {int(k): str(v) for k, v in json_data.items()}

					# 重新合成PDF
					result_pdf = compose_pdf(
						pdf_bytes,
						explanations,
						right_ratio,
						font_size,
						font_path=font_path,
						render_mode=render_mode,
						line_spacing=line_spacing
					)

					result["status"] = "completed"
					result["pdf_bytes"] = result_pdf
					result["explanations"] = explanations

				except json.JSONDecodeError as e:
					result["status"] = "failed"
					result["error"] = f"JSON解析失败: {str(e)}"
				except Exception as e:
					result["status"] = "failed"
					result["error"] = f"PDF合成失败: {str(e)}"

		except Exception as e:
			result["status"] = "failed"
			result["error"] = f"处理失败: {str(e)}"

		results[pdf_filename] = result

	return results
