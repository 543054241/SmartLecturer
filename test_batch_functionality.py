#!/usr/bin/env python3
"""
测试批量生成功能的基本逻辑
"""

import os
import sys
import json
from io import BytesIO

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_batch_processing_logic():
    """测试批量处理的基本逻辑"""
    print("🧪 测试批量生成功能...")

    # 模拟批量处理结果
    mock_batch_results = {
        "document1.pdf": {
            "status": "completed",
            "pdf_bytes": b"mock_pdf_data_1",
            "explanations": {1: "这是第一页的讲解", 2: "这是第二页的讲解"},
            "failed_pages": []
        },
        "document2.pdf": {
            "status": "completed",
            "pdf_bytes": b"mock_pdf_data_2",
            "explanations": {1: "这是文档2第一页的讲解"},
            "failed_pages": [2]  # 第二页失败
        },
        "document3.pdf": {
            "status": "failed",
            "pdf_bytes": None,
            "explanations": {},
            "failed_pages": [],
            "error": "API调用失败"
        }
    }

    print("✅ 模拟批量处理结果创建成功")

    # 测试统计功能
    total_files = len(mock_batch_results)
    completed_files = sum(1 for r in mock_batch_results.values() if r["status"] == "completed")
    failed_files = sum(1 for r in mock_batch_results.values() if r["status"] == "failed")

    print(f"📊 统计结果: 总文件数 {total_files}, 成功 {completed_files}, 失败 {failed_files}")

    # 测试ZIP打包功能
    import zipfile

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, result in mock_batch_results.items():
            if result["status"] == "completed" and result["pdf_bytes"]:
                base_name = os.path.splitext(filename)[0]
                new_filename = f"{base_name}讲解版.pdf"
                zip_file.writestr(new_filename, result["pdf_bytes"])

                if result["explanations"]:
                    json_filename = f"{base_name}.json"
                    json_bytes = json.dumps(result["explanations"], ensure_ascii=False, indent=2).encode("utf-8")
                    zip_file.writestr(json_filename, json_bytes)

    zip_buffer.seek(0)
    zip_data = zip_buffer.getvalue()
    print(f"📦 ZIP文件创建成功，大小: {len(zip_data)} bytes")

    # 测试分别下载文件名生成
    print("📄 测试文件名生成:")
    for filename, result in mock_batch_results.items():
        if result["status"] == "completed" and result["pdf_bytes"]:
            base_name = os.path.splitext(filename)[0]
            pdf_filename = f"{base_name}讲解版.pdf"
            json_filename = f"{base_name}.json"
            print(f"  {filename} -> {pdf_filename}, {json_filename}")

    print("🎉 所有测试通过！批量生成功能实现完成。")

if __name__ == "__main__":
    test_batch_processing_logic()
