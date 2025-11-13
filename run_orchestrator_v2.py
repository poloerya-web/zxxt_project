#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 2: 基于 plan.json 生成通用的 Manim 可视化代码
(通用版本 - 适配所有数学题目类型)
"""
import json
import os
import sys
import asyncio
import httpx
import textwrap

# --- 常量配置 ---
PLAN_FILENAME = "plan.json"
AUDIO_DIR = "media/sounds"
MANIM_SCRIPT_FILENAME = "final_video_script.py"
RUN_SCRIPT_FILENAME = "run_manim.sh"
CN_FONT = "Heiti SC"  # macOS 默认中文字体

# --- Qwen API 配置 ---
QWEN_API_KEY = "sk-ffbdc6a6150442ad974d33561ecf6953"
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen3-max"


def mock_call_tts_and_get_duration(text, segment_id, plan):
    """模拟 TTS - 从 plan.json 读取预设时长"""
    print(f"🎵 [MOCK-TTS] 正在为 {segment_id} 测量音频时长...")
    try:
        narration_segment = next(item for item in plan["narration"] if item["to"] == segment_id)
        suggested_duration = narration_segment["seconds"]
    except (StopIteration, KeyError):
        print(f"⚠️ 警告：在 plan.json 中未找到 {segment_id} 的建议时长，使用默认值 5s")
        suggested_duration = 5.0

    actual_duration = float(suggested_duration)

    return {
        "id": segment_id,
        "file": f"{segment_id}.mp3",
        "duration": actual_duration
    }


def build_universal_manim_prompt(board_segment, narration_segment, duration):
    """
    构建通用的 Manim 可视化代码生成 Prompt

    这个 Prompt 不包含任何特定题目的硬编码逻辑，
    而是引导 AI 根据板书和讲稿内容自主设计可视化
    """

    board_title = board_segment.get("title", "")
    board_lines = board_segment.get("lines", [])
    board_lines_str = "\n".join(board_lines)
    narration_text = narration_segment.get("text", "")
    segment_id = board_segment.get("id", "unknown")

    system_prompt = f"""你是一名顶级的 Manim 动画设计师和数学可视化专家。你的任务是为 Manim 场景的 `construct(self)` 方法生成一个 Python 代码片段。

# 核心目标

你需要创建一个**既有板书又有图形可视化**的数学教学动画。

1. **板书展示**: 在屏幕右侧展示给定的板书内容（公式、推导步骤等）
2. **图形可视化**: 根据讲稿和板书内容，在屏幕左侧创建相关的数学图形和动画
3. **精确同步**: 动画总时长必须严格等于 {duration:.2f} 秒

# 严格约束

## 1. 时长同步
- 所有 `self.play(...)` 的 `run_time` 和 `self.wait(...)` 的总和 **必须严格等于** {duration:.2f} 秒
- 代码片段的第一行必须是: `self.add_sound("{os.path.join(AUDIO_DIR, segment_id + '.mp3')}")`

## 2. 布局规则（防止重叠）
- **右侧板书区**: 所有文本（Tex, Text）放在屏幕右侧
  - 使用: `board_group = VGroup(...).to_edge(RIGHT, buff=0.5).scale(0.7)`
- **左侧可视化区**: 所有图形（Axes, Circle, Polygon, Dot, Line等）放在屏幕左侧
  - 使用: `visual_group = VGroup(...).to_edge(LEFT, buff=0.5).scale(0.9)`
- **严禁重叠**: 确保左右两侧内容不相互覆盖

## 3. 状态管理（跨段落持久化）
- 使用 `mobjects_on_screen` 字典来保存需要在后续段落中使用的 Mobject
- 例如:
  ```python
  mobjects_on_screen['axes'] = axes
  mobjects_on_screen['main_curve'] = curve
  mobjects_on_screen['current_board'] = board_group
  ```
- 在新段落开始时，通过 `mobjects_on_screen.get('key')` 获取之前的对象

## 4. 板书更新策略
- 每个段落开始时，清除旧板书:
  ```python
  self.play(FadeOut(mobjects_on_screen.get('current_board', VGroup())), run_time=0.5)
  ```
- 新板书写完后保存:
  ```python
  mobjects_on_screen['current_board'] = board_group
  ```
- **不要清除左侧的图形对象**，它们应该持续显示

## 5. 文本渲染规则
- **纯中文标题**: 使用 `Text(r"...", font=CN_FONT, weight=BOLD)`
- **包含数学内容**: **必须**使用 `Tex(r"...", tex_template=XELATEX_TEMPLATE, font_size=36)`
- **数学内容必须用 $ 包围**: 例如 `Tex(r"$\\frac{{x^2}}{{a^2}} = 1$", ...)`
- **严禁使用 MathTex**
- **严禁使用 "SimHei" 字体**

## 6. 动态对象规则
- 对于使用 `always_redraw` 的对象，**必须**用 `self.add(mobject)` 添加到场景
- **严禁**对 `always_redraw` 对象使用 `self.play(Create(...))`

## 7. 时长计算
- 你必须自己计算所有动画的总时长 `total_anim_time`
- 然后用 `wait_time = {duration:.2f} - total_anim_time` 来补足剩余时间
- 最后 `self.wait(wait_time)` 确保总时长准确

# 可视化设计指南

根据讲稿和板书内容，**自主判断**应该创建什么样的图形：

## 常见数学概念的可视化建议

### 几何问题
- **解析几何**: 创建坐标系 (Axes)，绘制曲线 (圆、椭圆、抛物线、双曲线)
- **点、线**: 使用 Dot, Line, DashedLine
- **面积、图形**: 使用 Polygon, Circle, Rectangle 填充颜色
- **动态演示**: 使用 ValueTracker + always_redraw 展示参数变化

### 代数问题
- **函数图像**: 绘制函数曲线 (axes.plot)
- **方程求解**: 高亮交点、零点
- **不等式**: 用颜色区分区域

### 微积分问题
- **导数**: 切线、法线动画
- **积分**: 矩形逼近、面积累加
- **极限**: 动态逼近过程

### 向量/矩阵
- **向量**: Arrow, Vector
- **变换**: Transform, ApplyMatrix

### 概率统计
- **分布**: BarChart, 曲线图
- **样本**: 散点动画

## 设计原则

1. **先思考本段的数学核心**: 是在引入概念？推导公式？还是展示结论？
2. **选择合适的图形**: 不要强行添加无关的可视化，但也不要只写板书
3. **动画要有意义**: 例如：
   - 引入椭圆时，可以先画坐标轴，再 Create 椭圆
   - 证明定点时，可以让直线扫过不同角度，展示恒过一点
   - 计算面积时，可以高亮四边形，甚至动态改变形状
4. **保持简洁**: 不要在一个段落里塞太多图形，宁可少而精

# 输出要求

- 只输出 Python 代码片段，不要用 markdown 代码块包围
- 代码应该可以直接插入到 `construct(self)` 方法中
- 代码要有适当的注释，说明每个动画的目的
- 确保所有变量名清晰（例如: ellipse, axes, point_a）

# 特别提醒

- 如果板书内容比较抽象（例如：纯代数推导），可以适当简化可视化，但至少要有一些装饰性的图形元素
- 如果讲稿明确提到某个几何对象（例如："椭圆"、"直线AB"、"四边形"），**必须**为其创建对应的可视化
- 优先保证时长准确和布局不重叠，其次才是可视化的复杂度
"""

    user_prompt = f"""
[约束时长]: {duration:.2f} 秒
[音频文件]: {segment_id}.mp3
[段落ID]: {segment_id}

[板书标题]: {board_title}
[板书内容]:
{board_lines_str}

[讲稿（动画灵感来源）]:
"{narration_text}"

---

请严格遵守 System Prompt 中的所有约束，生成精确同步、布局合理、可视化生动的 Python Manim 代码片段。

注意：
1. 根据讲稿和板书内容，判断应该创建什么样的数学图形
2. 确保左侧（可视化）和右侧（板书）不重叠
3. 总时长必须等于 {duration:.2f} 秒
4. 代码第一行必须是 add_sound

现在请输出代码（不要用markdown包围）：
"""

    return system_prompt.strip(), user_prompt.strip()


async def call_qwen_api(client, system_prompt, user_prompt, segment_id):
    """调用 Qwen API 生成 Manim 代码"""
    print(f"📞 [Qwen API] 正在为 {segment_id} 请求可视化代码...")

    payload = {
        "model": QWEN_MODEL,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = await client.post(QWEN_API_URL, json=payload, headers=headers, timeout=180.0)
        response.raise_for_status()
        data = response.json()
        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not raw_content:
            print(f"❌ 错误：Qwen API 为 {segment_id} 返回了空内容。")
            return f"        # ERROR: Qwen API returned empty content for {segment_id}\n        self.wait({duration})"

        cleaned_code = raw_content.replace("```python", "").replace("```", "").strip()
        print(f"✅ [Qwen API] 成功接收 {segment_id} 的可视化代码。")
        return cleaned_code

    except httpx.RequestError as e:
        print(f"❌ API 请求失败 (segment {segment_id}): {e}")
        return f"        # ERROR: API Request failed for {segment_id}\n        self.wait({5.0})"
    except Exception as e:
        print(f"❌ 处理 API 响应失败 (segment {segment_id}): {e}")
        return f"        # ERROR: API Response processing failed for {segment_id}\n        self.wait({5.0})"


async def main_orchestrator():
    """主编排器"""
    print("=" * 70)
    print("Stage 2: Manim 可视化代码生成器（通用版）")
    print("=" * 70)

    # 步骤 1: 加载 plan.json
    try:
        with open(PLAN_FILENAME, "r", encoding="utf-8") as f:
            plan = json.load(f)
        print(f"✅ 成功加载 `{PLAN_FILENAME}`")
    except Exception as e:
        print(f"❌ 加载 `{PLAN_FILENAME}` 时发生错误: {e}")
        sys.exit(1)

    # 步骤 2: 模拟 TTS 并获取时长
    print("\n--- 🎶 开始模拟 TTS 并获取时长 ---")
    os.makedirs(AUDIO_DIR, exist_ok=True)

    audio_durations = []
    narration_segments = plan.get("narration", [])
    if not narration_segments:
        print(f"❌ 错误：`{PLAN_FILENAME}` 中没有 'narration' 数组。")
        sys.exit(1)

    for segment in narration_segments:
        segment_id = segment.get("to")
        text = segment.get("text")
        if not segment_id or text is None:
            continue
        audio_info = mock_call_tts_and_get_duration(text, segment_id, plan)
        audio_durations.append(audio_info)

    durations_dict = {item['id']: item['duration'] for item in audio_durations}
    print(f"📊 时长报告: {json.dumps(audio_durations, indent=2)}")

    json_dump_str = json.dumps(audio_durations, indent=2)
    header_comment = "\n".join([f"# {line}" for line in json_dump_str.splitlines()])

    # 步骤 3: 批量调用 Qwen API 生成可视化代码
    print("\n--- 🐍 开始批量调用 Qwen API 生成 Manim 可视化 ---")
    all_code_snippets = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for segment in narration_segments:
            segment_id = segment.get("to")
            if not segment_id:
                continue
            try:
                board_segment = next(item for item in plan["blackboard"] if item["id"] == segment_id)
                duration = durations_dict[segment_id]
            except (StopIteration, KeyError):
                print(f"⚠️ 警告：跳过 {segment_id}，因为找不到匹配的板书或时长。")
                continue

            sys_prompt, user_prompt = build_universal_manim_prompt(board_segment, segment, duration)
            tasks.append(call_qwen_api(client, sys_prompt, user_prompt, segment_id))

        all_code_snippets = await asyncio.gather(*tasks)

    print("\n--- 🔧 正在拼接最终脚本 ---")

    # 步骤 4: 拼接成最终的 Manim 脚本
    script_body_raw = "\n\n".join(all_code_snippets)
    script_body_indented = textwrap.indent(script_body_raw, " " * 8)

    script_footer_raw = """
# --- 脚本结束 ---
print("✅ AI 生成的脚本执行完毕")
self.play(
    FadeOut(mobjects_on_screen.get('current_board', VGroup())),
    *[FadeOut(mob) for mob in self.mobjects],
    run_time=1.0
)
self.wait(1)
"""
    script_footer_indented = textwrap.indent(textwrap.dedent(script_footer_raw), " " * 8)

    script_header = f"""from manim import *
import os
import numpy as np

# 这是一个由 AI (Qwen) 动态生成的通用 Manim 脚本
# 基于 {PLAN_FILENAME} 和以下音频时长生成:
{header_comment}

CN_FONT = "{CN_FONT}"
AUDIO_DIR = "{AUDIO_DIR}"

# 自动配置支持中文的 xelatex 模板
XELATEX_TEMPLATE = TexTemplate(
    tex_compiler="xelatex",
    output_format=".xdv",
    preamble=r"\\usepackage[UTF8]{{ctex}} \\usepackage{{amsmath}} \\usepackage{{amssymb}}"
)

class AutoGeneratedScene(Scene):
    def construct(self):
        # Mobject 跟踪器，用于跨段落传递对象
        mobjects_on_screen = {{}}
"""

    final_script_content = script_header + "\n" + script_body_indented + "\n\n" + script_footer_indented

    # 步骤 5: 保存所有产物
    try:
        with open(MANIM_SCRIPT_FILENAME, "w", encoding="utf-8") as f:
            f.write(final_script_content)
        print(f"💾 已保存 `{MANIM_SCRIPT_FILENAME}`")
    except Exception as e:
        print(f"❌ 保存 Manim 脚本时出错: {e}")
        sys.exit(1)

    # 生成 run_manim.sh
    shell_script = f"""#!/bin/bash
echo "--- 正在渲染 AI 生成的视频 (基于 {PLAN_FILENAME}) ---"
manim -pqm {MANIM_SCRIPT_FILENAME} AutoGeneratedScene
"""
    try:
        with open(RUN_SCRIPT_FILENAME, "w", encoding="utf-8") as f:
            f.write(shell_script)
        if os.name != 'nt':
            os.chmod(RUN_SCRIPT_FILENAME, 0o755)
        print(f"💾 已保存 `{RUN_SCRIPT_FILENAME}`")
    except Exception as e:
        print(f"❌ 保存运行脚本时出错: {e}")

    # --- 结束，打印后续步骤 ---
    print("\n\n" + "=" * 70)
    print("🎉 自动化流程全部完成!")
    print("=" * 70)

    print("\n下一步操作：\n")
    print("1️⃣ 创建音频文件（用于 Manim 同步）：\n")
    print(f"   mkdir -p {AUDIO_DIR}")
    for audio in audio_durations:
        filepath = os.path.join(AUDIO_DIR, audio["file"])
        print(f"   ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t {audio['duration']} -q:a 9 -acodec libmp3lame \"{filepath}\" -y")
    print("\n2️⃣ 运行 Manim 渲染：")
    print(f"   ./{RUN_SCRIPT_FILENAME}")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    # 检查 API Key
    if "sk-ffbd" not in QWEN_API_KEY:
        print("=" * 50)
        print("❌ 错误：请在脚本顶部的 `QWEN_API_KEY` 中填入您的 API Key。")
        print("=" * 50)
        sys.exit(1)

    # 检查 httpx
    try:
        import httpx
    except ImportError:
        print("=" * 50)
        print("❌ 错误：未找到 `httpx` 库。")
        print("   请运行：pip install httpx")
        print("=" * 50)
        sys.exit(1)

    asyncio.run(main_orchestrator())
