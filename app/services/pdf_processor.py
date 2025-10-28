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
	基于栅位容量将解释内容分拣到对应栅位。

	Args:
		text: 请求展示的解释文本
		column_rects: 相应的栅位区域
		font_size: 字体大小
		fontfile: 字体文件路径
		fontname: 字体名
		render_mode: 渲染模式

	Returns:
		按栅位分配弃的文本列表
	"""
	if not text.strip():
		return [""] * len(column_rects)

	if not column_rects:
		return []

	if len(text) <= 500:
		parts = ["" for _ in column_rects]
		parts[0] = text
		return parts

	def estimate_text_capacity(rect: fitz.Rect) -> int:
		rect_width = rect.width
		rect_height = rect.height
		chars_per_line = max(int(rect_width / (font_size * 0.6)), 1)
		lines_per_rect = max(int(rect_height / (font_size * max(1.0, line_spacing))), 1)
		return int(chars_per_line * lines_per_rect * 0.9)

	column_capacities = [estimate_text_capacity(rect) for rect in column_rects]
	text_parts = ["" for _ in column_rects]
	remaining_text = text
	total_capacity = max(sum(column_capacities), 1)

	for idx, capacity in enumerate(column_capacities):
		if not remaining_text:
			break

		if idx == len(column_capacities) - 1:
			text_parts[idx] = remaining_text
			remaining_text = ""
			break

		proportional = max(int(len(remaining_text) * (capacity / total_capacity)), 1)
		alloc_chars = min(max(capacity, proportional), len(remaining_text))
		alloc_text = remaining_text[:alloc_chars]
		split_pos = alloc_chars
		for sep in ['，', '。', '；', '：', ',', '.', ';', ':', '\n\n', '\n', ' ']:
			pos = alloc_text.rfind(sep)
			if pos > alloc_chars * 0.7:
				split_pos = pos + 1
				break

		text_parts[idx] = remaining_text[:split_pos]
		remaining_text = remaining_text[split_pos:]
		total_capacity = max(total_capacity - capacity, 1)

	if remaining_text:
		text_parts[-1] += remaining_text

	return text_parts

def _page_png_bytes(doc: fitz.Document, pno: int, dpi: int) -> bytes:
	page = doc.load_page(pno)
	mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
	pix = page.get_pixmap(matrix=mat, alpha=False)
	return pix.tobytes("png")


def _compose_vector(dst_doc: fitz.Document, src_doc: fitz.Document, pno: int,
    right_ratio: float, font_size: int, explanation: str,
    font_path: Optional[str] = None,
    render_mode: str = "text", line_spacing: float = 1.4, column_padding: int = 10) -> None:
    spage = src_doc.load_page(pno)
    w, h = spage.rect.width, spage.rect.height

    # Normalize rotation so layout calculation always works in page coordinates
    rotation = spage.rotation
    if rotation != 0:
        original_rotation = rotation
        spage.set_rotation(0)
        w, h = spage.rect.width, spage.rect.height

    new_w, new_h = int(w * 3), h
    dpage = dst_doc.new_page(width=new_w, height=new_h)
    dpage.show_pdf_page(fitz.Rect(0, 0, w, h), src_doc, pno)

    if rotation != 0:
        spage.set_rotation(original_rotation)

    if render_mode == "empty_right":
        return

    margin_x, margin_y = 25, 40
    right_start = w + margin_x
    right_end = new_w - margin_x
    available_width = max(right_end - right_start, 1)
    column_spacing = 20
    max_columns = 3

    fontname = "china"
    fontfile = None
    font_available = False

    if font_path:
        try:
            if os.path.exists(font_path) and os.access(font_path, os.R_OK):
                fontfile = font_path
                font_available = True
            else:
                print(f"警告: 字体文件不存在或不可读: {font_path}，将使用默认字体")
        except Exception as e:
            print(f"警告: 字体文件验证失败: {e}，将使用默认字体")
    else:
        print("信息: 未指定字体文件，将使用默认字体")

    if not font_available:
        fontname = "helv"
        fontfile = None

    initial_text = explanation or ""
    line_height = font_size * max(1.0, line_spacing)
    bottom_core = int(line_height * 1.25)
    bottom_safe = (min(max(16, bottom_core), 36) if render_mode == "markdown" else 0)
    column_internal_margin = max(column_padding, int(font_size * 1.05))
    total_spacing = column_spacing * (max_columns - 1)
    column_width = max(1.0, (available_width - total_spacing) / max(max_columns, 1))

    def build_rects(count: int, top_offset: float = 0.0):
        if count <= 0:
            return []
        top = margin_y + top_offset
        bottom = new_h - margin_y - bottom_safe - 2
        if bottom <= top:
            bottom = top + max(line_height, font_size)
        rects = []
        for idx in range(count):
            x_left = right_start + idx * (column_width + column_spacing)
            x_right = x_left + column_width
            x0 = x_left + column_internal_margin
            x1 = min(x_right, right_end) - column_internal_margin
            if x1 <= x0:
                x1 = x0 + max(font_size * 0.5, 1)
            rects.append(fitz.Rect(x0, top, x1, bottom))
        return rects

    def estimated_capacity(rects):
        total = 0
        for rect in rects:
            rect_width = max(rect.width, 1)
            rect_height = max(rect.height, 1)
            chars_per_line = max(int(rect_width / (font_size * 0.6)), 1)
            lines = max(int(rect_height / (font_size * max(1.0, line_spacing))), 1)
            total += int(chars_per_line * lines * 0.9)
        return total

    effective_length = len(initial_text.strip()) or len(initial_text)
    column_count = max_columns
    all_rects = build_rects(max_columns)
    for num_columns in range(1, max_columns + 1):
        capacity = estimated_capacity(all_rects[:num_columns])
        fudge = 0.85 if render_mode == "markdown" else 1.0
        if effective_length <= capacity * fudge:
            column_count = num_columns
            break

    column_rects = all_rects[:column_count]

    text_parts = _smart_text_layout(initial_text, column_rects, font_size, fontfile, fontname, render_mode, line_spacing)

    leftovers = []
    for rect, text_part in zip(column_rects, text_parts):
        if not text_part.strip():
            leftovers.append("")
            continue

        if render_mode == "markdown":
            try:
                import re as _re

                def protect_latex(s: str) -> str:
                    s = _re.sub(r"\$\$(.+?)\$\$", r"\n```\n\\1\n```\n", s, flags=_re.S)
                    s = _re.sub(r"\$(.+?)\$", r"`\\1`", s, flags=_re.S)
                    return s

                md_text = protect_latex(text_part)
                html = markdown(md_text, extensions=["fenced_code", "tables", "toc", "codehilite"])
                css = f"""
                /* base reset */
                body {{ font-size: {font_size}pt; line-height: {line_spacing}; font-family: 'SimHei','Noto Sans SC','Microsoft YaHei',sans-serif; color: #000000; word-wrap: break-word; overflow-wrap: break-word; word-break: break-word; white-space: normal; }}
                pre, code {{ font-family: 'Consolas','Fira Code',monospace; font-size: {max(8, font_size-1)}pt; color: #000000; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ccc; padding: 2pt 4pt; color: #000000; }}
                body, p, h1, h2, h3, h4, h5, h6, ul, ol, pre, table {{ margin: 0; padding: 0; color: #000000; }}
                ul, ol {{ padding-left: 18pt; list-style-position: inside; }}
                p {{ margin-bottom: 1pt; }}
                """
                dpage.insert_htmlbox(rect, html, css=css)
                leftovers.append("")
            except Exception:
                leftover_len = dpage.insert_textbox(rect, text_part, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)
                if isinstance(leftover_len, (int, float)) and leftover_len > 0:
                    remaining_chars = int(leftover_len / (font_size * 0.6))
                    leftovers.append(text_part[-remaining_chars:] if remaining_chars < len(text_part) else "")
                else:
                    leftovers.append("")
        else:
            leftover_len = dpage.insert_textbox(rect, text_part, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)
            if isinstance(leftover_len, (int, float)) and leftover_len > 0:
                remaining_chars = int(leftover_len / (font_size * 0.6))
                leftovers.append(text_part[-remaining_chars:] if remaining_chars < len(text_part) else "")
            else:
                leftovers.append("")

    has_overflow = any(len(leftover) > 0 for leftover in leftovers)
    if has_overflow:
        cpage = dst_doc.new_page(width=new_w, height=new_h)
        header = f"第 {pno + 1} 页讲解 - 续"
        cpage.insert_text(fitz.Point(w + margin_x, margin_y), header, fontsize=font_size, fontname=fontname, fontfile=fontfile)

        header_h = int(font_size * 1.4)
        continue_rects = build_rects(column_count, top_offset=header_h)
        for rect, leftover_text in zip(continue_rects, leftovers):
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
                render_mode: str = "text", line_spacing: float = 1.4, column_padding: int = 10) -> bytes:
	src_doc = fitz.open(stream=src_bytes, filetype="pdf")
	dst_doc = fitz.open()
	for pno in range(src_doc.page_count):
		expl = explanations.get(pno, "")
		_compose_vector(dst_doc, src_doc, pno, right_ratio, font_size, expl, font_path=font_path, render_mode=render_mode, line_spacing=line_spacing, column_padding=column_padding)
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
				render_mode: str = "text", line_spacing: float = 1.4, column_padding: int = 10) -> Tuple[bytes, Dict[int, str], List[bytes], List[int]]:
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
	result_pdf = compose_pdf(src_bytes, expl_dict, right_ratio, font_size, font_path=font_path, render_mode=render_mode, line_spacing=line_spacing, column_padding=column_padding)
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
							render_mode: str = "text", line_spacing: float = 1.4, column_padding: int = 10) -> Dict[str, Dict]:
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
						line_spacing=line_spacing,
						column_padding=column_padding
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
