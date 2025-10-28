#!/usr/bin/env python3
"""
测试行距设置功能
"""

import fitz
import io

def test_line_spacing():
    print("=== 行距功能测试 ===\n")

    # 创建测试PDF
    src_doc = fitz.open()
    test_page = src_doc.new_page(width=400, height=600)
    test_page.insert_text((50, 100), "测试原PDF内容", fontsize=12)
    src_bytes = src_doc.tobytes()

    # 测试不同的行距设置
    line_spacings = [0.6, 0.8, 1.0, 1.4, 2.0]
    explanations = {0: "这是一个测试讲解内容。\n\n行距测试：\n- 行距1.0：紧凑显示\n- 行距1.4：标准间距\n- 行距2.0：宽松间距\n\n用来验证CSS样式是否正确应用行距设置。"}

    for spacing in line_spacings:
        print(f"生成PDF，行距设置为 {spacing}...")
        result_bytes = test_compose_with_spacing(src_bytes, explanations, spacing)
        filename = f"test_line_spacing_{spacing}.pdf"
        with open(filename, "wb") as f:
            f.write(result_bytes)
        print(f"✅ 已生成：{filename}")

    src_doc.close()
    print("\n🎉 行距测试完成！请检查生成的文件验证行距效果")

def test_compose_with_spacing(src_bytes, explanations, line_spacing):
    """使用指定行距合成PDF"""
    from app.services import pdf_processor

    return pdf_processor.compose_pdf(
        src_bytes=src_bytes,
        explanations=explanations,
        right_ratio=0.5,
        font_size=12,
        line_spacing=line_spacing,
        render_mode="markdown",
        font_path="assets/fonts/SIMHEI.TTF"
    )

if __name__ == "__main__":
    test_line_spacing()
