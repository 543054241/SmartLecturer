#!/usr/bin/env python3
"""
测试PyMuPDF字体名格式
找出正确的fontname参数格式
"""

import fitz

def test_font_formats():
    print("=== 测试PyMuPDF字体名格式 ===\n")

    try:
        doc = fitz.open()
        fontinfo = doc._insert_font(fontfile='assets/fonts/SIMHEI.TTF')
        print(f"字体插入结果: {fontinfo}")
        print(f"字体ID: {fontinfo[0]}")
        print(f"字体信息: {fontinfo[1]}")

        # 测试不同的fontname格式
        test_formats = [
            fontinfo[0],  # 字体ID（数字）
            str(fontinfo[0]),  # 字体ID转为字符串
            fontinfo[1]['name'],  # 字体名称
            f"/F{fontinfo[0]}",  # PDF字体引用格式
            f"({fontinfo[0]})",  # 另一种可能格式
        ]

        print("\n测试不同的fontname格式:")
        page = doc.new_page()

        for i, fontname in enumerate(test_formats):
            print(f"测试格式 {i+1}: {fontname} ({type(fontname).__name__})")
            try:
                test_text = f"测试{i+1}：您好世界中文字体"
                rect = fitz.Rect(50, 50 + i*25, 400, 70 + i*25)
                page.insert_textbox(rect, test_text, fontsize=10, fontname=fontname, align=0)
                print(f"  ✅ 成功")
            except Exception as e:
                print(f"  ❌ 失败: {e}")

        # 保存测试结果
        doc.save("test_font_format.pdf")
        print("\n✅ 测试PDF保存为 test_font_format.pdf")
        doc.close()

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_font_formats()
