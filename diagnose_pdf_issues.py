#!/usr/bin/env python3
"""
PDF生成问题诊断脚本
用于检查LLM生成内容在PDF中的页面限制和文字消失问题
"""

import fitz
import io
import json
import os
from typing import Dict, List, Tuple
from app.services import pdf_processor


def create_test_pdf(width: int = 400, height: int = 600) -> bytes:
    """创建测试PDF"""
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)

    # 添加一些测试内容
    page.insert_text((50, 100), "测试原PDF内容", fontsize=12)
    page.insert_text((50, 130), "这是用于诊断的测试页面", fontsize=12)

    bio = io.BytesIO()
    doc.save(bio)
    doc.close()
    return bio.getvalue()


def test_text_overflow():
    """测试文本溢出问题"""
    print("=== 测试文本溢出问题 ===\n")

    # 创建测试PDF
    src_bytes = create_test_pdf(400, 600)

    # 测试不同长度的文本
    test_cases = [
        ("短文本", "这是一个简短的测试文本。"),
        ("中等文本", "这是一个中等长度的测试文本，用于验证3栏布局是否能正确处理中等长度的内容。文本应该能够均匀分布在3个栏位中。"),
        ("长文本", """
这是一个非常长的测试文本，用于验证当文本内容超过单个页面容量时，系统是否能够正确创建续页。
长文本应该被正确分割到多个栏位中，如果内容过多，应该自动创建续页来容纳所有内容。
这样的长文本通常来自LLM的详细讲解，可能包含多个段落和复杂的说明。
我们需要确保即使是这样的长文本也能被正确渲染，而不会出现文字截断或消失的问题。
续页应该保持与主页面相同的布局风格，包括3栏分布和适当的边距设置。
""" * 3),  # 重复3次使文本更长
    ]

    for test_name, test_text in test_cases:
        print(f"测试：{test_name}")
        print(f"文本长度：{len(test_text)} 字符")

        try:
            explanations = {0: test_text}
            result_bytes = pdf_processor.compose_pdf(
                src_bytes=src_bytes,
                explanations=explanations,
                right_ratio=0.5,
                font_size=10,
                font_path="assets/fonts/SIMHEI.TTF",
                render_mode="text",
                line_spacing=1.2
            )

            # 分析结果PDF
            result_doc = fitz.open(stream=result_bytes)
            print(f"生成PDF页数：{result_doc.page_count}")

            for page_idx in range(result_doc.page_count):
                page = result_doc.load_page(page_idx)
                w, h = page.rect.width, page.rect.height
                print(f"  第{page_idx+1}页尺寸：{w:.1f} x {h:.1f}")

                # 提取文本内容进行验证
                text = page.get_text()
                # 移除PDF元数据，只检查实际内容
                clean_text = text.replace("···PDF··", "").replace("···········", "").strip()

                # 检查是否有足够的内容（非空且长度合理）
                has_content = len(clean_text) > 10
                if has_content:
                    print("  ✅ 文本内容存在")
                else:
                    print("  ❌ 文本内容丢失")
                    print(f"  页面文本：{text[:200]}...")

            result_doc.close()
            print("  ✅ 测试通过\n")

        except Exception as e:
            print(f"  ❌ 测试失败：{e}\n")


def test_font_issues():
    """测试字体相关问题"""
    print("=== 测试字体问题 ===\n")

    src_bytes = create_test_pdf(400, 600)
    test_text = "测试中文：你好世界！Hello World! 123456"

    # 测试不同的字体配置
    font_configs = [
        ("无字体", None),
        ("正确字体路径", "assets/fonts/SIMHEI.TTF"),
        ("错误字体路径", "assets/fonts/nonexistent.ttf"),
        ("系统字体", "C:/Windows/Fonts/simhei.ttf"),
    ]

    for config_name, font_path in font_configs:
        print(f"测试配置：{config_name}")
        if font_path and not os.path.exists(font_path):
            print(f"  ⚠️ 字体文件不存在：{font_path}")

        try:
            explanations = {0: test_text}
            result_bytes = pdf_processor.compose_pdf(
                src_bytes=src_bytes,
                explanations=explanations,
                right_ratio=0.5,
                font_size=12,
                font_path=font_path,
                render_mode="text",
                line_spacing=1.2
            )

            # 检查生成的PDF
            result_doc = fitz.open(stream=result_bytes)
            page = result_doc.load_page(0)
            text = page.get_text()

            # 检查中文字符是否正确显示
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
            print(f"  中文字符检测：{'✅' if has_chinese else '❌'}")
            print(f"  提取的文本：{text.strip()}")

            result_doc.close()
            print("  ✅ 字体测试完成\n")

        except Exception as e:
            print(f"  ❌ 字体测试失败：{e}\n")


def test_layout_issues():
    """测试布局相关问题"""
    print("=== 测试布局问题 ===\n")

    # 测试不同的PDF尺寸
    test_sizes = [
        (400, 600, "A6"),
        (600, 800, "自定义小"),
        (800, 1200, "自定义大"),
    ]

    test_text = "这是一个布局测试文本，用于验证不同页面尺寸下的3栏布局是否正常工作。"

    for width, height, size_name in test_sizes:
        print(f"测试尺寸：{size_name} ({width}x{height})")

        src_bytes = create_test_pdf(width, height)
        explanations = {0: test_text}

        try:
            result_bytes = pdf_processor.compose_pdf(
                src_bytes=src_bytes,
                explanations=explanations,
                right_ratio=0.5,
                font_size=10,
                font_path="assets/fonts/SIMHEI.TTF",
                render_mode="text",
                line_spacing=1.2
            )

            result_doc = fitz.open(stream=result_bytes)
            page = result_doc.load_page(0)
            w, h = page.rect.width, page.rect.height

            expected_width = width * 3  # 3栏布局
            width_match = abs(w - expected_width) < 1
            height_match = abs(h - height) < 1

            print(f"  实际尺寸：{w:.1f} x {h:.1f}")
            print(f"  宽度验证：{'✅' if width_match else '❌'} (期望: {expected_width})")
            print(f"  高度验证：{'✅' if height_match else '❌'} (期望: {height})")

            result_doc.close()
            print("  ✅ 布局测试完成\n")

        except Exception as e:
            print(f"  ❌ 布局测试失败：{e}\n")


def test_markdown_rendering():
    """测试markdown渲染问题"""
    print("=== 测试Markdown渲染 ===\n")

    src_bytes = create_test_pdf(400, 600)

    # 测试markdown内容
    markdown_text = """
# 测试标题

这是一个 **粗体** 和 *斜体* 的测试。

## 列表测试
- 项目1
- 项目2
  - 子项目2.1
  - 子项目2.2

## 代码测试
```python
def hello():
    print("Hello, World!")
```

## 表格测试
| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 数据1 | 数据2 | 数据3 |
| 数据4 | 数据5 | 数据6 |

> 这是一个引用块测试。
"""

    explanations = {0: markdown_text}

    try:
        result_bytes = pdf_processor.compose_pdf(
            src_bytes=src_bytes,
            explanations=explanations,
            right_ratio=0.5,
            font_size=10,
            font_path="assets/fonts/SIMHEI.TTF",
            render_mode="markdown",
            line_spacing=1.2
        )

        result_doc = fitz.open(stream=result_bytes)
        page = result_doc.load_page(0)
        text = page.get_text()

        # 检查markdown元素是否被渲染
        has_bold = '**' in markdown_text  # 原始markdown
        has_rendered_text = len(text.strip()) > 50  # 有足够的内容

        print(f"  文本长度：{len(text)} 字符")
        print(f"  内容渲染：{'✅' if has_rendered_text else '❌'}")
        print(f"  页面数量：{result_doc.page_count}")

        result_doc.close()
        print("  ✅ Markdown测试完成\n")

    except Exception as e:
        print(f"  ❌ Markdown测试失败：{e}\n")


def main():
    """主诊断函数"""
    print("🚀 开始PDF生成问题诊断\n")

    try:
        test_text_overflow()
        test_font_issues()
        test_layout_issues()
        test_markdown_rendering()

        print("🎉 诊断完成！请检查上述测试结果。")

    except Exception as e:
        print(f"❌ 诊断过程中发生错误：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
