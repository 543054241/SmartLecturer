#!/usr/bin/env python3
"""
检查PyMuPDF API的字体相关方法
"""

import fitz

def check_font_methods():
    print("=== 检查PyMuPDF字体相关API ===")
    doc = fitz.open()

    # 检查Document对象的所有字体方法
    font_methods = [attr for attr in dir(doc) if 'font' in attr.lower()]
    print("\n文档字体相关方法:")
    for method in font_methods:
        print(f"  - {method}")

    # 检查常用方法
    methods_to_check = ['insert_font', '_insert_font', 'add_font', 'embed_font', 'FontInfos', 'get_page_fonts']
    for method in methods_to_check:
        if hasattr(doc, method):
            print(f"✅ 方法存在: {method}")

            # 尝试获取签名或docstring
            try:
                if method == 'insert_font':
                    # PyMuPDF 1.24.9+ API - 新增字体
                    print(f"  尝试 API: insert_font(external=True, filename='font.ttf')")
                elif method == '_insert_font':
                    sig = getattr(doc, method).__code__.co_varnames
                    print(f"  参数: {sig}")
                elif method == 'FontInfos':
                    fonts = getattr(doc, method)
                    print(f"  FontInfos: {fonts}")
            except Exception as e:
                print(f"  获取信息失败: {e}")

    # 检查PyMuPDF版本
    print(f"\nPyMuPDF版本: {fitz.__version__}")

    # 尝试新版本API
    print("\n=== 尝试新版本字体API ===")
    try:
        # 新版本PyMuPDF字体嵌入方法
        fontname = doc.insert_font(external=True, filename='assets/fonts/SIMHEI.TTF')
        print(f"✅ insert_font(external=True) 成功: {fontname}")
    except Exception as e:
        print(f"❌ insert_font(external=True) 失败: {e}")

    doc.close()

if __name__ == "__main__":
    check_font_methods()
