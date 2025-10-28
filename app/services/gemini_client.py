from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional, Tuple
import base64

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage


@dataclass
class RateLimiter:
	max_rpm: int
	max_tpm: int
	max_rpd: int
	window_seconds: int = 60

	def __post_init__(self):
		self._req_timestamps: list[float] = []
		self._used_tokens: list[Tuple[float, int]] = []
		self._daily_requests: list[float] = []

	async def wait_for_slot(self, est_tokens: int) -> None:
		# 清理窗口
		now = time.time()
		self._req_timestamps = [t for t in self._req_timestamps if now - t < self.window_seconds]
		self._used_tokens = [(t, n) for (t, n) in self._used_tokens if now - t < self.window_seconds]
		# 清理每日请求（24小时窗口）
		self._daily_requests = [t for t in self._daily_requests if now - t < 86400]

		while True:
			now = time.time()
			self._req_timestamps = [t for t in self._req_timestamps if now - t < self.window_seconds]
			self._used_tokens = [(t, n) for (t, n) in self._used_tokens if now - t < self.window_seconds]
			self._daily_requests = [t for t in self._daily_requests if now - t < 86400]

			req_ok = len(self._req_timestamps) < self.max_rpm
			tokens_used = sum(n for _, n in self._used_tokens)
			tpm_ok = (tokens_used + est_tokens) <= self.max_tpm
			rpd_ok = len(self._daily_requests) < self.max_rpd

			if req_ok and tpm_ok and rpd_ok:
				break
			await asyncio.sleep(0.25)

		self._req_timestamps.append(time.time())
		self._used_tokens.append((time.time(), est_tokens))
		self._daily_requests.append(time.time())


def estimate_tokens(chinese_chars: int) -> int:
	# 粗估：中文约 2 字 ≈ 1 token，叠加指令开销 200
	return max(256, chinese_chars // 2 + 200)


class GeminiClient:
	def __init__(self, api_key: str, model_name: str, temperature: float, max_output_tokens: int,
				rpm_limit: int, tpm_budget: int, rpd_limit: int, logger=None) -> None:
		self.llm = ChatGoogleGenerativeAI(
			model=model_name,
			api_key=api_key,
			temperature=temperature,
			max_output_tokens=max_output_tokens,
		)
		self.ratelimiter = RateLimiter(max_rpm=rpm_limit, max_tpm=tpm_budget, max_rpd=rpd_limit)
		self.logger = logger

	async def explain_page(self, image_bytes: bytes, system_prompt: str) -> str:
		# 估算输出 tokens（目标 800~1200字）
		est = estimate_tokens(1200)
		await self.ratelimiter.wait_for_slot(est)

		# 将图片字节转为 data URL 以适配 image_url 格式
		b64 = base64.b64encode(image_bytes).decode("utf-8")
		data_url = f"data:image/png;base64,{b64}"
		content = [
			{"type": "text", "text": system_prompt},
			{"type": "image_url", "image_url": data_url},
		]

		backoff = 1.5
		delay = 1.0
		for attempt in range(5):
			try:
				resp = await asyncio.to_thread(self.llm.invoke, [HumanMessage(content=content)])
				text = resp.content if isinstance(resp.content, str) else resp.content[0].text
				return text.strip()
			except Exception as e:  # 捕获 429/5xx 等
				if attempt >= 4:
					raise
				if self.logger:
					self.logger(f"LLM 调用失败(第 {attempt+1} 次)：{e}")
				await asyncio.sleep(delay + random.uniform(0, 0.5))
				delay *= backoff
