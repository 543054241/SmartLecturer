import os
import io
import time
import json
import zipfile
import hashlib
import tempfile
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


# 创建临时目录用于存储处理结果
TEMP_DIR = os.path.join(tempfile.gettempdir(), "pdf_processor_cache")
os.makedirs(TEMP_DIR, exist_ok=True)


def get_file_hash(file_bytes: bytes, params: dict) -> str:
	"""生成基于文件内容和参数的哈希值"""
	content = file_bytes + json.dumps(params, sort_keys=True).encode('utf-8')
	return hashlib.md5(content).hexdigest()


def save_result_to_file(file_hash: str, result: dict) -> str:
	"""将处理结果保存到临时文件"""
	filepath = os.path.join(TEMP_DIR, f"{file_hash}.json")
	with open(filepath, 'w', encoding='utf-8') as f:
		# 不保存pdf_bytes到文件，只保存其他信息
		result_copy = result.copy()
		result_copy.pop('pdf_bytes', None)
		json.dump(result_copy, f, ensure_ascii=False, indent=2)
	return filepath


def load_result_from_file(file_hash: str) -> Optional[dict]:
	"""从临时文件加载处理结果"""
	filepath = os.path.join(TEMP_DIR, f"{file_hash}.json")
	if os.path.exists(filepath):
		try:
			with open(filepath, 'r', encoding='utf-8') as f:
				return json.load(f)
		except:
			return None
	return None


@st.cache_data
def cached_process_pdf(src_bytes: bytes, params: dict) -> dict:
	"""缓存的PDF处理函数"""
	from app.services import pdf_processor

	file_hash = get_file_hash(src_bytes, params)
	column_padding = params.get("column_padding", 10)

	# 尝试从缓存文件加载
	cached_result = load_result_from_file(file_hash)
	if cached_result and cached_result.get("status") == "completed":
		# 如果有缓存，需要重新生成PDF bytes（因为bytes不能序列化到JSON）
		try:
			result_bytes = pdf_processor.compose_pdf(
				src_bytes,
				cached_result["explanations"],
				params["right_ratio"],
				params["font_size"],
				font_path=(params.get("cjk_font_path") or None),
				render_mode=params.get("render_mode", "markdown"),
				line_spacing=params["line_spacing"],
				column_padding=column_padding
			)
			cached_result["pdf_bytes"] = result_bytes
			return cached_result
		except Exception as e:
			# 从缓存重新合成PDF失败，返回错误结果
			return {
				"status": "failed",
				"pdf_bytes": None,
				"explanations": {},
				"failed_pages": [],
				"error": f"从缓存重新合成PDF失败: {str(e)}"
			}

	# 没有缓存或缓存无效，重新处理
	try:
		explanations, preview_images, failed_pages = pdf_processor.generate_explanations(
			src_bytes=src_bytes,
			api_key=params["api_key"],
			model_name=params["model_name"],
			user_prompt=params["user_prompt"],
			temperature=params["temperature"],
			max_tokens=params["max_tokens"],
			dpi=params["dpi"],
			concurrency=min(params["concurrency"], 10),
			rpm_limit=params["rpm_limit"],
			tpm_budget=params["tpm_budget"],
			rpd_limit=params["rpd_limit"],
		)

		result_bytes = pdf_processor.compose_pdf(
			src_bytes,
			explanations,
			params["right_ratio"],
			params["font_size"],
			font_path=(params.get("cjk_font_path") or None),
			render_mode=params.get("render_mode", "markdown"),
			line_spacing=params["line_spacing"],
			column_padding=column_padding
		)

		result = {
			"status": "completed",
			"pdf_bytes": result_bytes,
			"explanations": explanations,
			"failed_pages": failed_pages
		}

		# 保存到缓存文件
		save_result_to_file(file_hash, result)

		return result

	except Exception as e:
		result = {
			"status": "failed",
			"pdf_bytes": None,
			"explanations": {},
			"failed_pages": [],
			"error": str(e)
		}
		return result


def setup_page():
	st.set_page_config(page_title="PDF 讲解流 · Gemini 2.5 Pro", layout="wide")
	st.title("PDF 讲解流 · Gemini 2.5 Pro")
	st.caption("逐页生成讲解，右侧留白排版，保持原PDF向量内容")


def sidebar_form():
	with st.sidebar:
		st.header("参数配置")
		api_key = st.text_input("GEMINI_API_KEY", value=os.getenv('GEMINI_API_KEY'),type="password")
		model_name = st.text_input("模型名", value="gemini-2.5-pro")
		temperature = st.slider("温度", 0.0, 1.0, 0.4, 0.1)
		max_tokens = st.number_input("最大输出 tokens", min_value=256, max_value=8192, value=4096, step=256)
		dpi = st.number_input("渲染DPI(仅供LLM)", min_value=96, max_value=300, value=180, step=12)
		right_ratio = st.slider("右侧留白比例", 0.2, 0.6, 0.48, 0.01)
		font_size = st.number_input("右栏字体大小", min_value=8, max_value=20, value=20, step=1)
		line_spacing = st.slider("讲解文本行距", 0.6, 2.0, 1.2, 0.1)
		column_padding = st.slider("栏内边距(像素)", 2, 16, 10, 1, help="控制每一栏左右内边距，防止文字被切边")
		concurrency = st.slider("并发页数", 1, 50, 50, 1)
		rpm_limit = st.number_input("RPM 上限(请求/分钟)", min_value=10, max_value=5000, value=150, step=10)
		tpm_budget = st.number_input("TPM 预算(令牌/分钟)", min_value=100000, max_value=20000000, value=2000000, step=100000)
		rpd_limit = st.number_input("RPD 上限(请求/天)", min_value=100, max_value=100000, value=10000, step=100)
		user_prompt = st.text_area("讲解风格/要求(系统提示)", value="请用中文讲解本页pdf，关键词给出英文，讲解详尽，语言简洁易懂。讲解让人一看就懂，便于快速学习。请避免不必要的换行，使页面保持紧凑。")
		cjk_font_path = st.text_input("CJK 字体文件路径(可选)", value="assets/fonts/SIMHEI.TTF")
		render_mode = st.selectbox("右栏渲染方式", ["text", "markdown"], index=1)
		return {
			"api_key": api_key,
			"model_name": model_name,
			"temperature": float(temperature),
			"max_tokens": int(max_tokens),
			"dpi": int(dpi),
			"right_ratio": float(right_ratio),
			"font_size": int(font_size),
			"line_spacing": float(line_spacing),
			"column_padding": int(column_padding),
			"concurrency": int(concurrency),
			"rpm_limit": int(rpm_limit),
			"tpm_budget": int(tpm_budget),
			"rpd_limit": int(rpd_limit),
			"user_prompt": user_prompt.strip(),
			"cjk_font_path": cjk_font_path.strip(),
			"render_mode": render_mode,
		}


def main():
	setup_page()
	params = sidebar_form()
	column_padding_value = params.get("column_padding", 10)

	# 显示当前处理状态
	batch_results = st.session_state.get("batch_results", {})
	if batch_results:
		total_files = len(batch_results)
		completed_files = sum(1 for r in batch_results.values() if r["status"] == "completed")
		failed_files = sum(1 for r in batch_results.values() if r["status"] == "failed")
		processing_files = sum(1 for r in batch_results.values() if r["status"] == "processing")

		if processing_files > 0:
			st.info(f"🔄 正在处理中... 已完成: {completed_files}/{total_files} 个文件")
		elif completed_files > 0:
			st.success(f"✅ 处理完成！成功: {completed_files} 个文件，失败: {failed_files} 个文件")
		elif failed_files > 0:
			st.error(f"❌ 处理失败！失败: {failed_files} 个文件")

	# 批量上传模式
	uploaded_files = st.file_uploader("上传 PDF 文件 (最多20个)", type=["pdf"], accept_multiple_files=True)
	if len(uploaded_files) > 20:
		st.error("最多只能上传20个文件")
		uploaded_files = uploaded_files[:20]
		st.warning("已自动截取前20个文件")

	col_run, col_save = st.columns([2, 1])

	# 下载选项
	with col_save:
		st.subheader("下载选项")
		download_mode = st.radio(
			"下载方式",
			["分别下载", "打包下载"],
			help="分别下载：为每个PDF生成单独下载按钮\n打包下载：将所有PDF打包成ZIP文件"
		)
		if download_mode == "打包下载":
			zip_filename = st.text_input("ZIP文件名", value="批量讲解PDF.zip")

	# 初始化session_state
	if "batch_results" not in st.session_state:
		st.session_state["batch_results"] = {}  # {filename: {"pdf_bytes": bytes, "explanations": dict, "status": str, "failed_pages": list}}
	if "batch_processing" not in st.session_state:
		st.session_state["batch_processing"] = False
	if "batch_zip_bytes" not in st.session_state:
		st.session_state["batch_zip_bytes"] = None
	if "batch_json_results" not in st.session_state:
		st.session_state["batch_json_results"] = {}
	if "batch_json_processing" not in st.session_state:
		st.session_state["batch_json_processing"] = False
	if "batch_json_zip_bytes" not in st.session_state:
		st.session_state["batch_json_zip_bytes"] = None

	with col_run:
		if st.button("批量生成讲解与合成", type="primary", use_container_width=True, disabled=st.session_state.get("batch_processing", False)):
			if not uploaded_files:
				st.error("请先上传 PDF 文件")
				st.stop()
			if not params["api_key"]:
				st.error("请在侧边栏填写 GEMINI_API_KEY")
				st.stop()

			st.session_state["batch_processing"] = True
			st.session_state["batch_results"] = {}
			st.session_state["batch_zip_bytes"] = None

			total_files = len(uploaded_files)
			st.info(f"开始批量处理 {total_files} 个文件：逐页渲染→生成讲解→合成新PDF（保持向量）")

			# 延后导入以加快首屏
			from app.services import pdf_processor

			# 整体进度
			overall_progress = st.progress(0)
			overall_status = st.empty()

			# 限制同时处理的PDF数量，避免API过载
			max_concurrent_pdfs = min(5, total_files)  # 最多同时处理5个PDF

			for i, uploaded_file in enumerate(uploaded_files):
				filename = uploaded_file.name
				st.session_state["batch_results"][filename] = {"status": "processing", "pdf_bytes": None, "explanations": {}, "failed_pages": [], "json_bytes": None}

				# 更新整体进度
				overall_progress.progress(int((i / total_files) * 100))
				overall_status.write(f"正在处理文件 {i+1}/{total_files}: {filename}")

				try:
					# 读取源PDF bytes
					src_bytes = uploaded_file.read()

					# 验证PDF文件有效性
					is_valid, validation_error = pdf_processor.validate_pdf_file(src_bytes)
					if not is_valid:
						st.session_state["batch_results"][filename] = {
							"status": "failed",
							"pdf_bytes": None,
							"explanations": {},
							"failed_pages": [],
							"error": f"PDF文件验证失败: {validation_error}"
						}
						st.error(f"❌ {filename} PDF文件无效: {validation_error}")
						continue

					# 检查是否有缓存
					file_hash = get_file_hash(src_bytes, params)
					cached_result = load_result_from_file(file_hash)

					if cached_result and cached_result.get("status") == "completed":
						st.info(f"📋 {filename} 使用缓存结果")
						# 从缓存加载，需要重新合成PDF
						try:
							result_bytes = pdf_processor.compose_pdf(
								src_bytes,
								cached_result["explanations"],
								params["right_ratio"],
								params["font_size"],
								font_path=(params.get("cjk_font_path") or None),
								render_mode=params.get("render_mode", "markdown"),
								line_spacing=params["line_spacing"],
								column_padding=column_padding_value
							)
							st.session_state["batch_results"][filename] = {
								"status": "completed",
								"pdf_bytes": result_bytes,
								"explanations": cached_result["explanations"],
								"failed_pages": cached_result["failed_pages"],
								"json_bytes": None
							}
						except Exception as e:
							# 缓存重新合成失败，标记为失败并尝试重新处理
							st.warning(f"缓存重新合成失败，尝试重新处理: {str(e)}")
							st.session_state["batch_results"][filename] = {"status": "processing", "pdf_bytes": None, "explanations": {}, "failed_pages": []}
							# 继续到下面的重新处理逻辑
							cached_result = None
					else:
						# 需要重新处理
						with st.spinner(f"处理 {filename} 中..."):
							result = cached_process_pdf(src_bytes, params)
							st.session_state["batch_results"][filename] = result

					result = st.session_state["batch_results"][filename]
					if result["status"] == "completed":
						st.success(f"✅ {filename} 处理完成！")
					if result["failed_pages"]:
						st.warning(f"⚠️ {filename} 中 {len(result['failed_pages'])} 页生成讲解失败")
					else:
						st.error(f"❌ {filename} 处理失败: {result.get('error', '未知错误')}")

				except Exception as e:
					st.session_state["batch_results"][filename] = {
						"status": "failed",
						"pdf_bytes": None,
						"explanations": {},
						"failed_pages": [],
						"error": str(e)
					}
					st.error(f"❌ {filename} 处理失败: {str(e)}")

			# 完成处理
			overall_progress.progress(100)
			overall_status.write("批量处理完成！")

			# 统计结果
			completed = sum(1 for r in st.session_state["batch_results"].values() if r["status"] == "completed")
			failed = sum(1 for r in st.session_state["batch_results"].values() if r["status"] == "failed")

			if completed > 0:
				st.success(f"🎉 批量处理完成！成功: {completed} 个文件，失败: {failed} 个文件")
			else:
				st.error("❌ 所有文件处理失败")

			# 预生成每个文件的 json_bytes，并构建ZIP缓存
			for fname, res in st.session_state["batch_results"].items():
				if res.get("status") == "completed" and res.get("explanations"):
					try:
						res["json_bytes"] = json.dumps(res["explanations"], ensure_ascii=False, indent=2).encode("utf-8")
					except Exception:
						res["json_bytes"] = None
			# 仅当存在成功项时构建ZIP
			completed_any = any(r.get("status") == "completed" and r.get("pdf_bytes") for r in st.session_state["batch_results"].values())
			if completed_any:
				zip_buffer = io.BytesIO()
				with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
					for fname, res in st.session_state["batch_results"].items():
						if res.get("status") == "completed" and res.get("pdf_bytes"):
							base_name = os.path.splitext(fname)[0]
							new_filename = f"{base_name}讲解版.pdf"
							zip_file.writestr(new_filename, res["pdf_bytes"])
							if res.get("json_bytes"):
								json_filename = f"{base_name}.json"
								zip_file.writestr(json_filename, res["json_bytes"])
				zip_buffer.seek(0)
				st.session_state["batch_zip_bytes"] = zip_buffer.getvalue()
			else:
				st.session_state["batch_zip_bytes"] = None

			st.session_state["batch_processing"] = False

	with col_save:
		# 显示批量处理结果
		batch_results = st.session_state.get("batch_results", {})
		if batch_results:
			st.subheader("📋 处理结果汇总")

			# 统计信息
			total_files = len(batch_results)
			completed_files = sum(1 for r in batch_results.values() if r["status"] == "completed")
			failed_files = sum(1 for r in batch_results.values() if r["status"] == "failed")

			col_stat1, col_stat2, col_stat3 = st.columns(3)
			with col_stat1:
				st.metric("总文件数", total_files)
			with col_stat2:
				st.metric("成功处理", completed_files)
			with col_stat3:
				st.metric("处理失败", failed_files)

			# 详细结果列表
			with st.expander("查看详细结果", expanded=False):
				for filename, result in batch_results.items():
					if result["status"] == "completed":
						st.success(f"✅ {filename} - 处理成功")
						if result["failed_pages"]:
							st.warning(f"  ⚠️ {len(result['failed_pages'])} 页生成讲解失败")
					else:
						st.error(f"❌ {filename} - 处理失败: {result.get('error', '未知错误')}")

			# 重试失败的文件
			failed_files_list = [f for f, r in batch_results.items() if r["status"] == "failed"]
			if failed_files_list and not st.session_state.get("batch_processing", False):
				st.subheader("🔄 重试失败的文件")
				if st.button(f"重试 {len(failed_files_list)} 个失败的文件", use_container_width=True):
					st.info(f"开始重试 {len(failed_files_list)} 个失败的文件...")

					# 找到原始上传的文件
					retry_files = []
					for failed_filename in failed_files_list:
						for uploaded_file in uploaded_files:
							if uploaded_file.name == failed_filename:
								retry_files.append(uploaded_file)
								break

					if retry_files:
						from app.services import pdf_processor

						retry_progress = st.progress(0)
						retry_status = st.empty()

						for i, uploaded_file in enumerate(retry_files):
							filename = uploaded_file.name
							retry_progress.progress(int((i / len(retry_files)) * 100))
							retry_status.write(f"重试文件 {i+1}/{len(retry_files)}: {filename}")

							try:
								src_bytes = uploaded_file.read()

								file_progress = st.progress(0)
								file_status = st.empty()

								def on_file_progress(done: int, total: int):
									pct = int(done * 100 / max(1, total))
									file_progress.progress(pct)
									file_status.write(f"{filename}: 正在生成讲解 {done}/{total}")

								def on_file_log(msg: str):
									file_status.write(f"{filename}: {msg}")

								with st.spinner(f"重试 {filename} 中..."):
									explanations, preview_images, failed_pages = pdf_processor.generate_explanations(
										src_bytes=src_bytes,
										api_key=params["api_key"],
										model_name=params["model_name"],
										user_prompt=params["user_prompt"],
										temperature=params["temperature"],
										max_tokens=params["max_tokens"],
										dpi=params["dpi"],
										concurrency=min(params["concurrency"], 10),
										rpm_limit=params["rpm_limit"],
										tpm_budget=params["tpm_budget"],
										rpd_limit=params["rpd_limit"],
										on_progress=on_file_progress,
										on_log=on_file_log,
									)

									result_bytes = pdf_processor.compose_pdf(
										src_bytes,
										explanations,
										params["right_ratio"],
										params["font_size"],
										font_path=(params.get("cjk_font_path") or None),
										render_mode=params.get("render_mode", "markdown"),
										line_spacing=params["line_spacing"],
										column_padding=column_padding_value
									)

								st.session_state["batch_results"][filename] = {
									"status": "completed",
									"pdf_bytes": result_bytes,
									"explanations": explanations,
									"failed_pages": failed_pages
								}

								st.success(f"✅ {filename} 重试成功！")
								if failed_pages:
									st.warning(f"⚠️ {filename} 中仍有 {len(failed_pages)} 页生成讲解失败")

								file_progress.empty()
								file_status.empty()

							except Exception as e:
								st.error(f"❌ {filename} 重试仍然失败: {str(e)}")

						retry_progress.progress(100)
						retry_status.write("重试完成！")

						# 更新统计
						completed_after_retry = sum(1 for r in st.session_state["batch_results"].values() if r["status"] == "completed")
						failed_after_retry = sum(1 for r in st.session_state["batch_results"].values() if r["status"] == "failed")
						st.success(f"重试后结果：成功 {completed_after_retry} 个，失败 {failed_after_retry} 个")

					else:
						st.error("无法找到需要重试的文件")

		# 下载功能
		if batch_results and any(r["status"] == "completed" for r in batch_results.values()):
			st.subheader("📥 下载结果")

			if download_mode == "打包下载":
				zip_bytes = st.session_state.get("batch_zip_bytes")
				st.download_button(
					label="📦 下载所有PDF和讲解JSON (ZIP)",
					data=zip_bytes,
					file_name=zip_filename,
					mime="application/zip",
					use_container_width=True,
					disabled=st.session_state.get("batch_processing", False) or not bool(zip_bytes),
					key="download_all_zip"
				)

			else:  # 分别下载
				st.write("**分别下载每个文件：**")
				for filename, result in batch_results.items():
					if result["status"] == "completed" and result["pdf_bytes"]:
						base_name = os.path.splitext(filename)[0]
						pdf_filename = f"{base_name}讲解版.pdf"
						json_filename = f"{base_name}.json"

						col_dl1, col_dl2 = st.columns(2)
						with col_dl1:
							st.download_button(
								label=f"📄 {pdf_filename}",
								data=result["pdf_bytes"],
								file_name=pdf_filename,
								mime="application/pdf",
								use_container_width=True,
								disabled=st.session_state.get("batch_processing", False),
								key=f"download_pdf_{filename}"
							)
						with col_dl2:
							if result["explanations"]:
								json_bytes = result.get("json_bytes")
								st.download_button(
									label=f"📝 {json_filename}",
									data=json_bytes,
									file_name=json_filename,
									mime="application/json",
									use_container_width=True,
									disabled=st.session_state.get("batch_processing", False) or not bool(json_bytes),
									key=f"download_json_{filename}"
								)

		# 导入讲解JSON功能（兼容批量和单文件模式）
		st.subheader("📤 导入功能")
		uploaded_expl = st.file_uploader("导入讲解JSON(可选)", type=["json"], key="expl_json")
		if uploaded_expl and st.button("加载讲解JSON到会话", use_container_width=True):
			try:
				data = json.loads(uploaded_expl.read().decode("utf-8"))
				# 键转为 int
				st.session_state["explanations"] = {int(k): str(v) for k, v in data.items()}
				st.success("已加载讲解JSON到会话，可直接重新合成。")

				# 如果当前有上传的PDF文件，提示可以直接合成
				if uploaded_files:
					st.info("💡 检测到已上传PDF文件，您可以点击下方的'仅重新合成'按钮来使用导入的讲解直接生成PDF。")

			except Exception as e:
				st.error(f"加载失败：{e}")

		# 仅重新合成功能（使用导入的讲解JSON）
		if st.session_state.get("explanations") and uploaded_files:
			st.subheader("🔄 重新合成")
			if st.button("仅重新合成（使用导入的讲解）", use_container_width=True):
				st.info("开始使用导入的讲解重新合成PDF...")

				from app.services import pdf_processor

				# 为每个上传的文件生成PDF
				recompose_results = {}
				recompose_progress = st.progress(0)
				recompose_status = st.empty()

				for i, uploaded_file in enumerate(uploaded_files):
					filename = uploaded_file.name
					recompose_progress.progress(int((i / len(uploaded_files)) * 100))
					recompose_status.write(f"重新合成 {i+1}/{len(uploaded_files)}: {filename}")

					try:
						src_bytes = uploaded_file.read()
						result_bytes = pdf_processor.compose_pdf(
							src_bytes,
							st.session_state["explanations"],
							params["right_ratio"],
							params["font_size"],
							font_path=(params.get("cjk_font_path") or None),
							render_mode=params.get("render_mode", "markdown"),
							line_spacing=params["line_spacing"],
							column_padding=column_padding_value
						)

						recompose_results[filename] = {
							"status": "completed",
							"pdf_bytes": result_bytes,
							"explanations": st.session_state["explanations"].copy(),
							"failed_pages": []
						}

						st.success(f"✅ {filename} 重新合成完成！")

					except Exception as e:
						recompose_results[filename] = {
							"status": "failed",
							"pdf_bytes": None,
							"explanations": {},
							"failed_pages": [],
							"error": str(e)
						}
						st.error(f"❌ {filename} 重新合成失败: {str(e)}")

				# 保存重新合成的结果
				st.session_state["batch_results"] = recompose_results

				recompose_progress.progress(100)
				recompose_status.write("重新合成完成！")

				completed_recompose = sum(1 for r in recompose_results.values() if r["status"] == "completed")
				failed_recompose = sum(1 for r in recompose_results.values() if r["status"] == "failed")
				st.success(f"重新合成结果：成功 {completed_recompose} 个文件，失败 {failed_recompose} 个文件")

		# 批量根据JSON重新生成PDF（单框上传 + 智能配对）
		st.subheader("📚 批量根据JSON重新生成PDF（单框上传）")

		# 单一上传框：同时接收 PDF 与 JSON
		uploaded_mixed = st.file_uploader(
			"上传 PDF 与 JSON（可混合拖拽）",
			type=["pdf", "json"],
			accept_multiple_files=True,
			key="mixed_pdf_json"
		)

		MAX_BYTES = 209_715_200  # 200MB
		pdf_files, json_files = [], []
		if uploaded_mixed:
			for f in uploaded_mixed:
				if f.size and f.size > MAX_BYTES:
					st.error(f"{f.name} 超过200MB限制")
					continue
				name = f.name.lower()
				if name.endswith(".pdf"):
					pdf_files.append(f)
				elif name.endswith(".json"):
					json_files.append(f)

		# 特例：恰好 1 PDF + 1 JSON -> 直接成对，无需名称检查
		def _build_and_run_with_pairs(pairs):
			from app.services import pdf_processor
			st.info("开始批量根据JSON重新生成PDF...")
			st.session_state["batch_json_processing"] = True
			st.session_state["batch_json_results"] = {}
			st.session_state["batch_json_zip_bytes"] = None
			# 将确认配对转为现有批处理入口的两个列表，并让 JSON 名与 PDF 同名匹配
			pdf_data, json_data = [], []
			for pdf_obj, json_obj in pairs:
				pdf_name = pdf_obj.name
				json_alias = os.path.splitext(pdf_name)[0] + ".json"
				pdf_data.append((pdf_name, pdf_obj.read()))
				json_data.append((json_alias, json_obj.read()))
			batch_results = pdf_processor.batch_recompose_from_json(
				pdf_data,
				json_data,
				params["right_ratio"],
				params["font_size"],
				font_path=(params.get("cjk_font_path") or None),
				render_mode=params.get("render_mode", "markdown"),
				line_spacing=params["line_spacing"],
				column_padding=column_padding_value
			)
			st.session_state["batch_json_results"] = batch_results
			# 构建ZIP缓存
			completed_count = sum(1 for r in batch_results.values() if r["status"] == "completed" and r.get("pdf_bytes"))
			if completed_count > 0:
				zip_buffer = io.BytesIO()
				with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
					for filename, result in batch_results.items():
						if result["status"] == "completed" and result.get("pdf_bytes"):
							base_name = os.path.splitext(filename)[0]
							new_filename = f"{base_name}讲解版.pdf"
							zip_file.writestr(new_filename, result["pdf_bytes"])
				zip_buffer.seek(0)
				st.session_state["batch_json_zip_bytes"] = zip_buffer.getvalue()
			else:
				st.session_state["batch_json_zip_bytes"] = None
			st.session_state["batch_json_processing"] = False

		if pdf_files and json_files and len(pdf_files) == 1 and len(json_files) == 1:
			col_single_ok, _ = st.columns([2,1])
			with col_single_ok:
				if st.button("🚀 开始（1 对 1 直接配对）", type="primary", use_container_width=True):
					_build_and_run_with_pairs([(pdf_files[0], json_files[0])])

		# 正常：多文件 -> 智能匹配 + 可编辑配对
		import pandas as _pd
		from difflib import SequenceMatcher
		from pathlib import Path as _Path

		def _normalize_basename(name: str) -> str:
			base = _Path(name).stem
			base = base.lower().strip()
			for ch in [" ", "-", ".", "_", "(", ")"]:
				base = base.replace(ch, "")
			return base

		def _best_match_map(pdf_names, json_names, threshold: float = 0.25):
			mapping = {}
			jn_norm = {j: _normalize_basename(j) for j in json_names}
			for p in pdf_names:
				pn = _normalize_basename(p)
				best = None
				best_score = 0.0
				for j, jn in jn_norm.items():
					s = SequenceMatcher(None, pn, jn).ratio()
					if s > best_score:
						best_score = s
						best = j
				mapping[p] = best if best_score >= threshold else None
			return mapping

		if pdf_files or json_files:
			pdf_names = [f.name for f in pdf_files]
			json_names = [f.name for f in json_files]

			st.caption(f"已选择 PDF: {len(pdf_names)}，JSON: {len(json_names)}")

			if pdf_names and json_names and not (len(pdf_names) == 1 and len(json_names) == 1):
				# 生成建议匹配
				suggest = _best_match_map(pdf_names, json_names, 0.25)
				# 构建可编辑表
				options = ["(未选择)"] + json_names
				rows = [{"PDF文件": p, "JSON选择": suggest.get(p) or "(未选择)"} for p in pdf_names]
				df = _pd.DataFrame(rows)
				edited = st.data_editor(
					df,
					use_container_width=True,
					column_config={
						"JSON选择": st.column_config.SelectboxColumn("JSON选择", options=options, required=True)
					},
					hide_index=True,
					key="pair_editor"
				)

				# 校验：禁止重复或未选择
				chosen = [v for v in edited["JSON选择"].tolist() if v != "(未选择)"]
				dup = len(chosen) != len(set(chosen))
				miss = any(v == "(未选择)" for v in edited["JSON选择"].tolist())
				if dup:
					st.error("存在重复选择的 JSON，请调整为一一对应。")
				if miss:
					st.warning("有 PDF 未选择对应的 JSON，将不会被处理。")

				# 运行按钮
				if st.button("🚀 开始批量重新生成PDF", type="primary", use_container_width=True,
							disabled=st.session_state.get("batch_json_processing", False)):
					pairs = []
					json_map = {f.name: f for f in json_files}
					for _, row in edited.iterrows():
						pdf_name = row["PDF文件"]
						json_name = row["JSON选择"]
						if json_name == "(未选择)":
							continue
						pdf_obj = next((f for f in pdf_files if f.name == pdf_name), None)
						json_obj = json_map.get(json_name)
						if pdf_obj and json_obj:
							pairs.append((pdf_obj, json_obj))
					if not pairs:
						st.error("没有有效的配对可处理。")
					else:
						_build_and_run_with_pairs(pairs)

		# 显示批量JSON处理结果
		batch_json_results = st.session_state.get("batch_json_results", {})
		if batch_json_results:
			st.subheader("📥 批量JSON处理结果下载")
			# 统计信息
			total_files = len(batch_json_results)
			completed_files = sum(1 for r in batch_json_results.values() if r["status"] == "completed")
			failed_files = sum(1 for r in batch_json_results.values() if r["status"] == "failed")
			col_stat1, col_stat2, col_stat3 = st.columns(3)
			with col_stat1:
				st.metric("总文件数", total_files)
			with col_stat2:
				st.metric("成功处理", completed_files)
			with col_stat3:
				st.metric("处理失败", failed_files)
			if completed_files > 0:
				zip_filename = f"批量JSON重新生成PDF_{time.strftime('%Y%m%d_%H%M%S')}.zip"
				zip_bytes = st.session_state.get("batch_json_zip_bytes")
				st.download_button(
					label="📦 下载所有成功处理的PDF (ZIP)",
					data=zip_bytes,
					file_name=zip_filename,
					mime="application/zip",
					use_container_width=True,
					key="batch_json_zip_download",
					disabled=st.session_state.get("batch_json_processing", False) or not bool(zip_bytes)
				)
			st.write("**分别下载每个成功处理的文件：**")
			for filename, result in batch_json_results.items():
				if result["status"] == "completed" and result["pdf_bytes"]:
					base_name = os.path.splitext(filename)[0]
					pdf_filename = f"{base_name}讲解版.pdf"
					col_dl1, col_dl2 = st.columns([3, 1])
					with col_dl1:
						st.write(f"📄 {pdf_filename}")
					with col_dl2:
						st.download_button(
							label="下载",
							data=result["pdf_bytes"],
							file_name=pdf_filename,
							mime="application/pdf",
							key=f"batch_json_pdf_{filename}",
							disabled=st.session_state.get("batch_json_processing", False)
						)


if __name__ == "__main__":
	main()
