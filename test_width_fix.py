#!/usr/bin/env python3
"""
测试页面宽度修复：验证新页面宽度是否正确为原页面宽度的2倍
"""

import fitz
import io

def test_width_fix():
    print("=== 页面宽度修复测试 ===\n")

    # 创建一个测试PDF作为源文档
    print("创建测试PDF作为源文档...")
    src_doc = fitz.open()
    test_page = src_doc.new_page(width=400, height=600)  # A6宽高作为测试
    test_page.insert_text((50, 100), "这一页是测试内容", fontsize=12)
    src_bytes = src_doc.tobytes()

    # 模拟compose_pdf函数的调用
    print("测试页面宽度计算...")
    result_bytes = test_compose_width(src_bytes)

    # 验证结果PDF的页面尺寸
    result_doc = fitz.open(stream=result_bytes)
    for i in range(result_doc.page_count):
        page = result_doc.load_page(i)
        w, h = page.rect.width, page.rect.height
        print(f"第{i+1}页尺寸: {w:.1f} x {h:.1f} pts")
        print(f"  宽度是否为原宽度2倍: {abs(w - 400*2) < 1}")
        print(f"  高度是否保持一致: {abs(h - 600) < 1}")

    result_doc.close()
    src_doc.close()

    print("\n✅ 宽度修复测试完成")

def test_compose_width(src_bytes):
    """简化的compose_pdf函数用于测试"""
    from app.services import pdf_processor

    # 使用固定的讲解内容
    explanations = {0: "测试讲解内容"}

    # 调用compose_pdf函数
    result = pdf_processor.compose_pdf(
        src_bytes=src_bytes,
        explanations=explanations,
        right_ratio=0.5,  # 这个参数现在应该被忽略
        font_size=10,
        font_path="assets/fonts/SIMHEI.TTF"
    )
    return result

if __name__ == "__main__":
    test_width_fix()
