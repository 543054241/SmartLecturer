#!/usr/bin/env python3
"""
PyMuPDF三栏布局实现测试
"""

import fitz
import io
import time

def create_test_pdf():
    """创建测试PDF"""
    src_doc = fitz.open()
    test_page = src_doc.new_page(width=400, height=600)
    test_page.insert_text((50, 100), "测试原PDF内容\n这是原文档的内容", fontsize=12)
    src_bytes = src_doc.tobytes()
    src_doc.close()
    return src_bytes

def test_pymupdf_implementation(src_bytes, explanations):
    """测试PyMuPDF实现"""
    print("🔶 测试PyMuPDF实现...")
    start_time = time.time()

    try:
        from app.services.pdf_processor import compose_pdf
        result = compose_pdf(
            src_bytes=src_bytes,
            explanations=explanations,
            right_ratio=0.5,
            font_size=10,
            line_spacing=1.2,
            render_mode="text",
            font_path="assets/fonts/SIMHEI.TTF"
        )
        end_time = time.time()
        print(".2f")
        return result
    except Exception as e:
        print(f"❌ PyMuPDF实现失败: {e}")
        return None

def analyze_pdf_quality(pdf_bytes, name):
    """分析PDF质量"""
    try:
        doc = fitz.open(stream=pdf_bytes)
        page = doc.load_page(0)

        width, height = page.rect.width, page.rect.height
        print(f"📊 {name} PDF分析:")
        print(f"   尺寸: {width:.1f} x {height:.1f} pts")
        print(f"   页面数: {doc.page_count}")

        # 检查文本内容
        text = page.get_text()
        text_length = len(text.strip())
        print(f"   文本长度: {text_length} 字符")

        # 检查是否有三栏内容
        has_column_content = "第1栏内容" in text or "第2栏内容" in text or "第3栏内容" in text
        print(f"   包含栏位内容: {'✅' if has_column_content else '❌'}")

        doc.close()
        return True
    except Exception as e:
        print(f"❌ {name} PDF分析失败: {e}")
        return False

def main():
    print("=== PyMuPDF三栏布局实现测试 ===\n")

    # 创建测试数据
    src_bytes = create_test_pdf()
    explanations = {
        0: """这是一个详细的测试讲解内容，用来验证PyMuPDF三栏布局的效果。

第1栏内容：AI生成的第一部分讲解，应该显示在最左边的栏中。包含详细的技术分析和要点说明。

第2栏内容：这里是第二个栏位的讲解内容，说明了关键概念和技术细节。每个栏位都有自己的内容空间，可以容纳较长的文本。

第3栏内容：第三个栏位放置总结性内容，包括主要结论和建议。PyMuPDF实现应该能够正确显示三栏布局。

技术特点：
- PyMuPDF: 手动计算布局，灵活且功能丰富
- 支持Markdown渲染和复杂文本处理
- 保持原始PDF的矢量内容质量"""
    }

    # 测试PyMuPDF实现
    pymupdf_result = test_pymupdf_implementation(src_bytes, explanations)
    print()

    # 分析结果
    print("=== 结果分析 ===\n")

    if pymupdf_result:
        analyze_pdf_quality(pymupdf_result, "PyMuPDF实现")
        with open("test_compare_pymupdf.pdf", "wb") as f:
            f.write(pymupdf_result)
        print("   💾 已保存: test_compare_pymupdf.pdf")
    else:
        print("❌ PyMuPDF实现无输出")

    print("\n🎯 测试完成！请检查生成的PDF文件验证三栏布局效果")

if __name__ == "__main__":
    main()
