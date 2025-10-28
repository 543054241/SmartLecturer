from __future__ import annotations

import io
import asyncio
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

def pages_with_blank_explanations(explanations: Dict[int, str], min_chars: int = 10) -> List[int]:
	return [p for p, t in explanations.items() if is_blank_explanation(t, min_chars)]


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
	# 新的宽度策略：原PDF:空白区域 = 1:2，3栏布局
	# 总宽度 = 原宽度 × 3
	new_w, new_h = int(w * 3), h
	dpage = dst_doc.new_page(width=new_w, height=new_h)
	# 先始终嵌入原页矢量，保证左侧保留原始内容（0到w位置）
	dpage.show_pdf_page(fitz.Rect(0, 0, w, h), src_doc, pno)
	# 若仅需要右侧留白，不插入任何文本/HTML
	if render_mode == "empty_right":
		return
	# 计算3栏布局参数
	# 右侧区域从w开始到3w结束，减去左右边距后等分3栏
	margin_x, margin_y = 15, 40
	right_start = w + margin_x
	right_end = new_w - margin_x
	available_width = right_end - right_start
	column_width = available_width / 3
	column_spacing = 10  # 栏间距

	# 字体：优先使用提供的 CJK 字体
	fontname = "china"
	fontfile = font_path if font_path else None

	# 初始放置讲解文本 - 3栏布局
	initial_text = explanation or ""

	# 创建3栏矩形区域，确保右边距正确
	column_rects = []
	for i in range(3):
		x_left = right_start + i * (column_width + column_spacing / 2)
		x_right = x_left + column_width - column_spacing / 2
		# 确保最后一栏不超过右边界
		if i == 2:
			x_right = right_end
		rect = fitz.Rect(x_left, margin_y, x_right, new_h - margin_y)
		column_rects.append(rect)

	# 将文本分成3个大致相等的部分
	text_parts = []
	if len(initial_text) <= 500:  # 短文本不分割
		text_parts = [initial_text] + [""] * 2
	else:
		# 根据字符数分割成3部分
		part_len = len(initial_text) // 3
		text_parts = [
			initial_text[:part_len],
			initial_text[part_len:2*part_len],
			initial_text[2*part_len:]
		]

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
				body {{ font-size: {font_size}pt; line-height: {line_spacing}; word-wrap: break-word; font-family: 'SimHei','Noto Sans SC','Microsoft YaHei',sans-serif; }}
				pre, code {{ font-family: 'Consolas','Fira Code',monospace; font-size: {max(8, font_size-1)}pt; }}
				table {{ border-collapse: collapse; width: 100%; }}
				th, td {{ border: 1px solid #ccc; padding: 2pt 4pt; }}
				"""
				dpage.insert_htmlbox(rect, html, css=css)
				leftovers.append("")
			except Exception:
				leftover = dpage.insert_textbox(rect, text_part, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)
				leftovers.append(leftover or "")
		else:
			leftover = dpage.insert_textbox(rect, text_part, fontsize=font_size, fontname=fontname, fontfile=fontfile, align=0)
			leftovers.append(leftover or "")

	# 检查是否有溢出的文本需要续页
	has_overflow = any(len(leftover) > 0 for leftover in leftovers)
	if has_overflow:
		cpage = dst_doc.new_page(width=new_w, height=new_h)
		header = f"第 {pno + 1} 页讲解 - 续"
		cpage.insert_text(fitz.Point(w + margin_x, margin_y), header, fontsize=font_size, fontname=fontname, fontfile=fontfile)

		# 为续页创建3栏矩形（与主页面保持一致的布局）
		continue_rects = []
		for i in range(3):
			x_left = right_start + i * (column_width + column_spacing / 2)
			x_right = x_left + column_width - column_spacing / 2
			# 确保最后一栏不超过右边界
			if i == 2:
				x_right = right_end
			rect = fitz.Rect(x_left, margin_y + 24, x_right, new_h - margin_y)
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
