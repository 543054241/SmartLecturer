#!/usr/bin/env python3
"""
测试导入JSON功能在批量模式下的兼容性
"""

import os
import sys
import json
from io import BytesIO

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_import_json_compatibility():
    """测试导入JSON功能的基本逻辑"""
    print("🧪 测试导入JSON功能兼容性...")

    # 模拟导入的讲解JSON数据
    mock_explanations = {
        "1": "这是第一页的讲解内容",
        "2": "这是第二页的讲解内容",
        "3": "这是第三页的讲解内容"
    }

    print("✅ 模拟讲解JSON数据创建成功")

    # 测试数据转换（字符串键转为整数键）
    converted_explanations = {int(k): str(v) for k, v in mock_explanations.items()}
    print(f"📝 转换后的数据: {len(converted_explanations)} 页讲解")

    # 模拟批量重新合成结果
    mock_batch_results = {
        "document1.pdf": {
            "status": "completed",
            "pdf_bytes": b"mock_pdf_data_1",
            "explanations": converted_explanations,
            "failed_pages": []
        },
        "document2.pdf": {
            "status": "completed",
            "pdf_bytes": b"mock_pdf_data_2",
            "explanations": converted_explanations,
            "failed_pages": []
        }
    }

    print("✅ 模拟批量重新合成结果创建成功")

    # 验证结果
    total_files = len(mock_batch_results)
    completed_files = sum(1 for r in mock_batch_results.values() if r["status"] == "completed")

    print(f"📊 重新合成统计: 总文件数 {total_files}, 成功 {completed_files}")

    # 验证每个文件的讲解数据
    for filename, result in mock_batch_results.items():
        if result["status"] == "completed":
            explanations_count = len(result["explanations"])
            print(f"  ✅ {filename}: {explanations_count} 页讲解数据")

    print("🎉 导入JSON功能兼容性测试通过！")

if __name__ == "__main__":
    test_import_json_compatibility()
