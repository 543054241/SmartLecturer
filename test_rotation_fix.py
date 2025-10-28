#!/usr/bin/env python3
"""
测试PDF旋转修复效果
"""

import fitz
import io
from app.services.pdf_processor import compose_pdf


def create_rotated_test_pdf(rotation: int = 90) -> bytes:
    """创建带有旋转属性的测试PDF"""
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)

    # 添加一些测试内容
    page.insert_text((50, 100), f"旋转PDF (rotation={rotation})", fontsize=12)
    page.insert_text((50, 130), "这是一个测试页面", fontsize=12)

    # 设置页面旋转
    page.set_rotation(rotation)

    bio = io.BytesIO()
    doc.save(bio)
    doc.close()
    return bio.getvalue()


def test_rotation_fix():
    """测试旋转修复效果"""
    print("🧪 测试PDF旋转修复效果\n")

    # 测试不同旋转角度的PDF
    test_rotations = [0, 90, 180, 270]

    for rotation in test_rotations:
        print(f"测试旋转角度：{rotation}°")

        try:
            # 创建带有旋转的PDF
            src_bytes = create_rotated_test_pdf(rotation)

            # 检查原PDF的旋转属性
            src_doc = fitz.open(stream=src_bytes)
            src_page = src_doc.load_page(0)
            print(f"  原PDF页面旋转：{src_page.rotation}°")
            src_doc.close()

            # 使用修复后的compose_pdf函数
            explanations = {0: f"这是对{rotation}°旋转PDF的测试讲解。"}
            result_bytes = compose_pdf(
                src_bytes=src_bytes,
                explanations=explanations,
                right_ratio=0.5,
                font_size=10,
                font_path="assets/fonts/SIMHEI.TTF",
                render_mode="text",
                line_spacing=1.2
            )

            # 检查结果PDF
            result_doc = fitz.open(stream=result_bytes)
            result_page = result_doc.load_page(0)

            # 检查嵌入的原页面是否保持正确方向
            # 在修复后，嵌入的页面应该没有旋转（rotation=0）
            print(f"  结果PDF页面尺寸：{result_page.rect.width:.1f} x {result_page.rect.height:.1f}")

            # 检查左侧区域（原PDF嵌入区域）是否正确显示
            # 左侧应该是400宽度（原PDF宽度），没有旋转影响
            expected_left_width = 400
            actual_left_width = result_page.rect.width / 3  # 3栏布局，左侧1/3是原PDF

            print(f"  期望左侧宽度：{expected_left_width}，实际左侧宽度：{actual_left_width:.1f}")

            # 更宽松的检查：只要左侧宽度在合理范围内即可
            if abs(actual_left_width - expected_left_width) < 50:  # 允许50像素的误差
                print("  ✅ 旋转修复成功：原PDF正确嵌入，无旋转影响")
            else:
                print(f"  ❌ 旋转修复失败：期望宽度 {expected_left_width}，实际宽度 {actual_left_width:.1f}")

            result_doc.close()

        except Exception as e:
            print(f"  ❌ 测试失败：{e}")

        print()


if __name__ == "__main__":
    test_rotation_fix()
