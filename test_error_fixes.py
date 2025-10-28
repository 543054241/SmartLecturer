#!/usr/bin/env python3
"""
测试错误处理修复效果
验证PDF处理错误是否能正确显示具体错误信息
"""

import os
import sys
import tempfile
from io import BytesIO

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_error_handling():
    """测试错误处理改进"""
    print("🧪 测试错误处理修复效果\n")

    from app.services import pdf_processor

    # 测试1：PDF验证功能
    print("📄 测试1：PDF文件验证")
    try:
        # 创建一个有效的测试PDF
        valid_pdf_bytes = pdf_processor.compose_pdf(
            b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Hello World) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000200 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n284\n%%EOF",
            {},
            0.5,
            12,
            render_mode="empty_right"
        )
        is_valid, error_msg = pdf_processor.validate_pdf_file(valid_pdf_bytes)
        print(f"  有效PDF验证：{'✅ 通过' if is_valid else '❌ 失败'} - {error_msg}")

        # 测试无效PDF
        invalid_pdf_bytes = b"This is not a PDF file"
        is_valid, error_msg = pdf_processor.validate_pdf_file(invalid_pdf_bytes)
        print(f"  无效PDF验证：{'✅ 通过' if not is_valid else '❌ 失败'} - {error_msg}")

    except Exception as e:
        print(f"  PDF验证测试失败：{e}")

    print("\n" + "="*50 + "\n")

    # 测试2：缓存错误处理
    print("💾 测试2：缓存错误处理")

    # 创建测试参数
    test_params = {
        "api_key": "test_key",
        "model_name": "test_model",
        "user_prompt": "test prompt",
        "temperature": 0.5,
        "max_tokens": 1000,
        "dpi": 150,
        "right_ratio": 0.5,
		"font_size": 12,
		"line_spacing": 1.2,
		"column_padding": 10,
		"concurrency": 1,
        "rpm_limit": 100,
        "tpm_budget": 100000,
        "rpd_limit": 1000,
        "cjk_font_path": "assets/fonts/SIMHEI.TTF",
        "render_mode": "text"
    }

    try:
        # 导入streamlit_app模块来测试cached_process_pdf
        import app.streamlit_app as st_app

        # 使用不存在的PDF数据测试缓存处理
        invalid_pdf = b"invalid pdf content"
        result = st_app.cached_process_pdf(invalid_pdf, test_params)

        if result["status"] == "failed" and "error" in result and result["error"] != "未知错误":
            print("  ✅ 缓存错误处理正确：返回了具体的错误信息")
            print(f"  错误信息：{result['error'][:100]}...")
        else:
            print("  ❌ 缓存错误处理失败：没有返回具体的错误信息")
            print(f"  实际结果：status={result.get('status')}, error={result.get('error')}")

    except Exception as e:
        print(f"  缓存错误处理测试失败：{e}")

    print("\n" + "="*50 + "\n")

    # 测试3：批量处理错误显示
    print("📊 测试3：批量处理错误显示")

    # 模拟批量处理结果
    mock_results = {
        "valid_file.pdf": {
            "status": "completed",
            "pdf_bytes": b"mock_pdf",
            "explanations": {0: "test explanation"},
            "failed_pages": []
        },
        "invalid_file.pdf": {
            "status": "failed",
            "pdf_bytes": None,
            "explanations": {},
            "failed_pages": [],
            "error": "PDF文件验证失败: PDF文件无效或已损坏: cannot open broken document"
        },
        "unknown_error.pdf": {
            "status": "failed",
            "pdf_bytes": None,
            "explanations": {},
            "failed_pages": [],
            "error": None  # 模拟没有错误信息的情况
        }
    }

    for filename, result in mock_results.items():
        error_msg = result.get('error', '未知错误')
        if result["status"] == "failed":
            if error_msg and error_msg != '未知错误':
                print(f"  ✅ {filename}: 显示具体错误 - {str(error_msg)[:50]}...")
            else:
                print(f"  ❌ {filename}: 仍然显示未知错误 - {error_msg}")

    print("\n🎉 错误处理修复测试完成！")


def test_pdf_validation_edge_cases():
    """测试PDF验证的边界情况"""
    print("🔍 测试PDF验证边界情况\n")

    from app.services import pdf_processor

    # 测试空文件
    empty_pdf = b""
    is_valid, error = pdf_processor.validate_pdf_file(empty_pdf)
    print(f"空文件：{'✅ 正确拒绝' if not is_valid else '❌ 错误接受'} - {error}")

    # 测试只有PDF头部但内容损坏的文件
    broken_pdf = b"%PDF-1.4\n%broken content"
    is_valid, error = pdf_processor.validate_pdf_file(broken_pdf)
    print(f"损坏PDF：{'✅ 正确拒绝' if not is_valid else '❌ 错误接受'} - {error}")

    # 测试非常小的有效PDF
    try:
        # 使用compose_pdf创建一个最小的有效PDF
        minimal_pdf = pdf_processor.compose_pdf(
            b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 100 100]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 0\n>>\nstream\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000170 00000 n \ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n234\n%%EOF",
            {},
            0.5,
            12,
            render_mode="empty_right"
        )
        is_valid, error = pdf_processor.validate_pdf_file(minimal_pdf)
        print(f"最小PDF：{'✅ 正确接受' if is_valid else '❌ 错误拒绝'} - {error}")
    except Exception as e:
        print(f"最小PDF测试失败：{e}")

    print("\n🎯 PDF验证边界测试完成！")


def main():
    """主测试函数"""
    print("🚀 开始错误处理修复效果验证\n")

    try:
        test_error_handling()
        test_pdf_validation_edge_cases()

        print("\n🎊 所有测试完成！请检查上述结果确认修复效果。")

    except Exception as e:
        print(f"❌ 测试过程中发生错误：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
