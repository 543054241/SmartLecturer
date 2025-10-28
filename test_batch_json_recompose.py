#!/usr/bin/env python3
"""
测试批量根据JSON重新生成PDF功能
"""

import os
import sys
import json
import tempfile
from io import BytesIO

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_existing_pdf(filename):
    """加载现有的PDF文件"""
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        print(f"警告: 找不到文件 {filename}，将使用空字节")
        return b""

def create_mock_json():
    """创建一个模拟的讲解JSON文件"""
    explanations = {
        "0": "这是第一页的测试讲解内容。包含了一些基本信息和说明。",
        "1": "这是第二页的测试讲解内容。演示了多页PDF的处理能力。"
    }
    return json.dumps(explanations, ensure_ascii=False, indent=2).encode('utf-8')

def test_batch_json_recompose():
    """测试批量JSON重新生成PDF功能"""
    print("🧪 测试批量根据JSON重新生成PDF功能...")

    # 导入必要的模块
    from app.services import pdf_processor

    # 使用现有的PDF文件进行测试，只用一个有效的PDF文件
    pdf_files = [
        ("document1.pdf", load_existing_pdf("test_3column_layout.pdf")),
    ]

    json_files = [
        ("document1.json", create_mock_json()),
        ("document2.json", create_mock_json()),
        # 注意：test.pdf 没有对应的JSON文件，用于测试匹配失败的情况
    ]

    print(f"📁 创建了 {len(pdf_files)} 个PDF文件和 {len(json_files)} 个JSON文件")

    # 测试文件匹配
    pdf_names = [name for name, _ in pdf_files]
    json_names = [name for name, _ in json_files]

    matches = pdf_processor.match_pdf_json_files(pdf_names, json_names)
    print("🔗 文件匹配结果:")
    for pdf, json_match in matches.items():
        status = f"匹配到 {json_match}" if json_match else "未匹配"
        print(f"  {pdf} -> {status}")

    # 执行批量重新合成
    print("🚀 开始批量重新合成...")
    results = pdf_processor.batch_recompose_from_json(
        pdf_files,
        json_files,
        right_ratio=0.4,
        font_size=12,
        font_path="assets/fonts/SIMHEI.TTF",  # 提供字体文件路径
        render_mode="text",
        line_spacing=1.2
    )

    # 分析结果
    total_files = len(results)
    completed_files = sum(1 for r in results.values() if r["status"] == "completed")
    failed_files = sum(1 for r in results.values() if r["status"] == "failed")

    print("📊 处理结果统计:")
    print(f"  总文件数: {total_files}")
    print(f"  成功处理: {completed_files}")
    print(f"  处理失败: {failed_files}")

    # 详细结果
    print("📋 详细处理结果:")
    for filename, result in results.items():
        if result["status"] == "completed":
            pdf_size = len(result["pdf_bytes"]) if result["pdf_bytes"] else 0
            print(f"  ✅ {filename} - 成功 (PDF大小: {pdf_size} bytes)")
        else:
            print(f"  ❌ {filename} - 失败: {result.get('error', '未知错误')}")

    # 验证成功处理的文件
    if completed_files > 0:
        print("🔍 验证成功处理的文件...")

        # 保存一个测试文件到临时目录
        for filename, result in results.items():
            if result["status"] == "completed" and result["pdf_bytes"]:
                temp_dir = tempfile.gettempdir()
                test_file = os.path.join(temp_dir, f"test_batch_{filename}")
                with open(test_file, 'wb') as f:
                    f.write(result["pdf_bytes"])
                print(f"  💾 已保存测试文件: {test_file}")
                break

    print("🎉 批量JSON重新生成PDF功能测试完成！")

    # 返回测试结果
    return {
        "total": total_files,
        "completed": completed_files,
        "failed": failed_files,
        "results": results
    }

if __name__ == "__main__":
    test_batch_json_recompose()
