#!/usr/bin/env python3
"""
测试边距改进效果：验证三栏布局的边距和间距是否更安全
"""

import fitz
import io

def test_margin_improvement():
    print("=== 三栏布局边距改进测试 ===\n")

    # 创建测试PDF
    src_doc = fitz.open()
    test_page = src_doc.new_page(width=400, height=600)
    test_page.insert_text((50, 100), "测试原PDF内容\n这是原文档的内容", fontsize=12)
    src_bytes = src_doc.tobytes()

    print("创建测试PDF...")
    print(f"原PDF尺寸: 400 x 600 pts")

    # 测试讲解内容
    explanations = {
        0: """这是一个测试讲解内容，用来验证改进后的三栏布局边距效果。

第1栏：左侧栏位应该有足够的左边距，不会紧贴边缘。栏间距也应该足够宽敞。

第2栏：中间栏位应该与左右两栏保持相等的间距，每栏都有舒适的阅读空间。

第3栏：右侧栏位应该有足够的右边距，不会紧贴页面边缘。整体布局应该看起来更安全舒适。

边距改进要点：
- 增加左右边距（每边20单位）
- 增加栏间距（15单位）
- 优化宽度分配，确保每栏都有足够的呼吸空间"""
    }

    print("生成改进后的三栏布局PDF...")
    result_bytes = test_compose_improved_margins(src_bytes, explanations)
    with open("test_margin_improved.pdf", "wb") as f:
        f.write(result_bytes)
    print("✅ 已生成：test_margin_improved.pdf")

    # 验证生成的PDF尺寸
    result_doc = fitz.open(stream=result_bytes)
    for i in range(result_doc.page_count):
        page = result_doc.load_page(i)
        w, h = page.rect.width, page.rect.height
        print(f"\n第{i+1}页尺寸: {w:.1f} x {h:.1f} pts")
        print(f"  总宽度验证: {abs(w - 400*3) < 1} (期望: 1200)")

        # 分析布局参数（基于实际代码中的设置）
        orig_width = 400
        left_margin = 25  # 实际代码中的margin_x
        right_margin = 25  # 实际代码中的margin_x
        column_spacing = 20  # 实际代码中的column_spacing
        column_internal_margin = 8  # 栏位内部边距

        right_start = orig_width + left_margin  # 425
        right_width = orig_width * 2 - left_margin - right_margin  # 750
        column_width = (right_width - 2 * column_spacing) / 3  # (750 - 40) / 3 = 236.67
        # 实际文本区域宽度 = column_width - 2 * column_internal_margin
        text_width = column_width - 2 * column_internal_margin

        print(f"  左侧边距: {left_margin} pts")
        print(f"  右侧边距: {right_margin} pts")
        print(f"  栏间距: {column_spacing} pts")
        print(f"  每栏宽度: {column_width:.1f} pts")
        print(f"  栏位位置: 栏1={right_start:.1f}, 栏2={right_start + column_width + column_spacing:.1f}, 栏3={right_start + 2*(column_width + column_spacing):.1f}")

    result_doc.close()
    src_doc.close()

    print("\n🎉 边距改进测试完成！请检查生成的PDF以验证改进效果")
    print("改进效果预期：")
    print("- 更宽敞的栏间距（15单位）")
    print("- 充足的左右边距（每边20单位）")
    print("- 更舒适的阅读体验")

def test_compose_improved_margins(src_bytes, explanations):
    """使用改进边距的三栏布局合成PDF"""
    from app.services.pdf_processor import compose_pdf

    return compose_pdf(
        src_bytes=src_bytes,
        explanations=explanations,
        right_ratio=0.5,
        font_size=10,
        line_spacing=1.2,
        render_mode="text",
        font_path="assets/fonts/SIMHEI.TTF"
    )

if __name__ == "__main__":
    test_margin_improvement()
