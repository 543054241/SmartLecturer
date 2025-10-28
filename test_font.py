#!/usr/bin/env python3
"""
字体加载测试脚本
用于验证PyMuPDF是否能正确加载中文字体
"""

import fitz
import os

def test_font_loading():
    print("=== 字体加载测试 ===\n")

    # 字体文件路径
    font_paths = [
        "assets/fonts/SIMHEI.TTF",
        "assets/fonts/simhei.ttf",  # 小写，应该失败
        os.path.abspath("assets/fonts/SIMHEI.TTF"),  # 绝对路径
        "C:/Windows/Fonts/simhei.ttf",  # 系统字体路径
    ]

    # 测试不同路径的字体加载
    for font_path in font_paths:
        print(f"测试字体路径: {font_path}")
        try:
            # 创建一个新的PDF文档
            doc = fitz.open()

            # 在PyMuPDF 1.24.11中，使用内部方法 _insert_font，参数名为fontfile
            fontinfo = doc._insert_font(fontfile=font_path)
            print(f"✅ 成功加载字体: {fontinfo}")

            # fontinfo 是 [font_id, font_dict] 格式，使用字体ID
            font_id = fontinfo[0]
            fontname = font_id

            # 测试插入一些中文文本
            page = doc.new_page()
            test_text = "测试中文：你好世界！"
            page.insert_text((50, 100), test_text, fontname=fontname, fontsize=12)
            print(f"✅ 成功插入中文文本")

            # 保存测试PDF
            test_output = f"test_output_{os.path.basename(font_path).replace('.', '_')}.pdf"
            doc.save(test_output)
            print(f"✅ 成功保存测试PDF: {test_output}")
            doc.close()
            print()

        except Exception as e:
            print(f"❌ 加载失败: {e}\n")

    # 测试默认字体
    print("测试默认Helvetica字体:")
    try:
        doc = fitz.open()
        page = doc.new_page()
        test_text = "测试中文：你好世界！"  # 这应该显示为乱码
        page.insert_text((50, 100), test_text, fontsize=12)  # 使用默认字体
        doc.save("test_output_default.pdf")
        doc.close()
        print("✅ 默认字体保存成功（预期显示为问号）\n")
    except Exception as e:
        print(f"❌ 默认字体测试失败: {e}\n")

if __name__ == "__main__":
    test_font_loading()
