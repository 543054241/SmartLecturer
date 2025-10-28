#!/usr/bin/env python3
"""
集成测试：测试PDF处理器是否能正确显示中文字体
"""

import sys
import os

def test_pdf_composition():
    print("=== PDF合成集成测试 ===\n")

    try:
        # 导入必要的模块
        from app.services import pdf_processor
        import fitz

        # 创建一个简单的测试PDF（作为源文档）
        print("创建测试PDF作为源文档...")
        src_doc = fitz.open()
        test_page = src_doc.new_page()
        test_page.insert_text((50, 100), "这一页是测试内容", fontsize=12)
        src_bytes = src_doc.tobytes()
        src_doc.close()

        # 测试讲解内容（包含中文）
        explanations = {
            0: "这是一个测试页面的讲解。演示中文字符是否能正确显示：测试、中文、字符、显示！\n\n主要要点：\n1. 确保中文字体正确嵌入\n2. 验证问号问题已解决\n3. 测试宋体黑体在PDF中的显示效果"
        }

        # 测试compose_pdf函数
        print("合成PDF，嵌入中文字体...")
        font_path = "assets/fonts/SIMHEI.TTF"
        result_bytes = pdf_processor.compose_pdf(
            src_bytes=src_bytes,
            explanations=explanations,
            right_ratio=0.4,
            font_size=11,
            font_path=font_path
        )

        # 保存结果PDF
        with open("test_result_font.pdf", "wb") as f:
            f.write(result_bytes)

        print("✅ PDF合成成功，已保存为 test_result_font.pdf")

        # 验证PDF中的字体信息
        print("\n验证PDF中的字体...")
        result_doc = fitz.open(stream=result_bytes)
        # 在PyMuPDF中，字体信息通过FontInfos属性获取
        fonts = result_doc.FontInfos

        print(f"PDF中的字体数量: {len(fonts)}")
        for i, font in enumerate(fonts):
            print(f"字体 {i}: {font}")

        # 检查是否包含中文字体
        has_cjk_font = any("SimHei" in str(font) or "Hei" in str(font) for font in fonts)
        if has_cjk_font:
            print("✅ PDF中包含中文字体")
        else:
            print("❓ PDF中未找到中文字体")

        result_doc.close()

        print("\n👉 请打开 test_result_font.pdf 检查中文显示是否正常")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pdf_composition()
