#!/usr/bin/env python3
"""
测试新的3栏布局和1:2宽度比例
"""

import fitz
import io

def test_3column_layout():
    print("=== 3栏布局和1:2宽度比例测试 ===\n")

    # 创建测试PDF
    src_doc = fitz.open()
    test_page = src_doc.new_page(width=400, height=600)
    test_page.insert_text((50, 100), "测试原PDF内容\n这是原文档的内容", fontsize=12)
    src_bytes = src_doc.tobytes()

    print("创建测试PDF...")
    print(f"原PDF尺寸: 400 x 600 pts")

    # 测试新的3栏布局
    explanations = {
        0: """这是一个详细的测试讲解内容，用来验证3栏布局的效果。

第1栏内容：AI生成的第一部分讲解，应该显示在最左边的栏中。包含详细的技术分析和要点说明。

第2栏内容：这里是第二个栏位的讲解内容，说明了关键概念和技术细节。每个栏位都有自己的内容空间，可以容纳较长的文本。

第3栏内容：第三个栏位放置总结性内容，包括主要结论和建议。3栏布局可以显著增加页面可读性和内容密度，充分利用页面空间。

技术特点：
- 原PDF:空白页面 = 1:2 的比例
- 总宽度扩大到原PDF的3倍
- 右边2倍空间分成3个栏位
- 支持markdown格式和行距调节"""
    }

    print("生成3栏布局PDF...")
    result_bytes = test_compose_3columns(src_bytes, explanations)
    with open("test_3column_layout.pdf", "wb") as f:
        f.write(result_bytes)
    print("✅ 已生成：test_3column_layout.pdf")

    # 验证生成的PDF尺寸
    result_doc = fitz.open(stream=result_bytes)
    for i in range(result_doc.page_count):
        page = result_doc.load_page(i)
        w, h = page.rect.width, page.rect.height
        print(f"\n第{i+1}页尺寸: {w:.1f} x {h:.1f} pts")
        print(f"  宽度验证: {abs(w - 400*3) < 1} (期望: 1200)")
        print(f"  高度保持: {abs(h - 600) < 1}")

    result_doc.close()
    src_doc.close()

    print("\n🎉 3栏布局测试完成！请检查生成的PDF以验证布局效果")
    print("预期效果：")
    print("- 左边1/3: 原PDF内容")
    print("- 右边2/3: 3个等宽栏位显示AI讲解")
    print("- 陈列密度更高，可容纳更多讲解内容")

def test_compose_3columns(src_bytes, explanations):
    """使用新的3栏布局合成PDF"""
    from app.services import pdf_processor

    return pdf_processor.compose_pdf(
        src_bytes=src_bytes,
        explanations=explanations,
        right_ratio=0.5,
        font_size=10,
        line_spacing=1.2,
        render_mode="markdown",
        font_path="assets/fonts/SIMHEI.TTF"
    )

if __name__ == "__main__":
    test_3column_layout()
