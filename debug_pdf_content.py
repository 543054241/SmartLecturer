#!/usr/bin/env python3
"""
调试PDF内容，检查文本是否正确插入
"""

import fitz

def check_pdf_content(pdf_path, name):
    """检查PDF内容"""
    print(f"=== 检查 {name} ===")

    try:
        doc = fitz.open(pdf_path)
        print(f"页面数: {doc.page_count}")

        for i in range(doc.page_count):
            page = doc.load_page(i)
            text = page.get_text()
            print(f"\n第{i+1}页文本内容:")
            print(f"'{text}'")
            print(f"文本长度: {len(text)}")

            # 检查特定内容
            if "第1栏内容" in text:
                print("✅ 找到第1栏内容")
            if "第2栏内容" in text:
                print("✅ 找到第2栏内容")
            if "第3栏内容" in text:
                print("✅ 找到第3栏内容")

        doc.close()

    except Exception as e:
        print(f"❌ 检查失败: {e}")

if __name__ == "__main__":
    check_pdf_content("test_compare_pymupdf.pdf", "PyMuPDF实现")
    print("\n" + "="*50 + "\n")
    check_pdf_content("test_compare_reportlab.pdf", "ReportLab实现")
