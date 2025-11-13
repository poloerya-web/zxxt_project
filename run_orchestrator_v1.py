import json
import os
import time
import sys
import re
import asyncio  # 导入异步 IO
import httpx  # 导入 HTTP 客户端
import textwrap  # 导入 textwrap 来处理缩进

# --- 1. 常量配置 ---
PLAN_FILENAME = "plan.json"  # 您提供的计划文件名
AUDIO_DIR = "media/sounds"  # 模拟音频的输出目录
MANIM_SCRIPT_FILENAME = "final_video_script.py"  # 最终生成的 Manim 脚本
RUN_SCRIPT_FILENAME = "run_manim.sh"  # 最终生成的运行脚本
CN_FONT = "Heiti SC"  # "Source Han Sans SC"  # 您的中文字体 (macOS 默认 "Heiti SC")

# --- 2. Qwen API 配置 (使用您提供的 Key) ---
QWEN_API_KEY = "sk-ffbdc6a6150442ad974d33561ecf6953"
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen3-max"  # "qwen-max" 或您选择的模型


# -------------------------------------------------------------------
# 步骤 3: 模拟 TTS - (读取 plan.json 并生成时长)
# -------------------------------------------------------------------
def mock_call_tts_and_get_duration(text, segment_id, plan):
    # (此函数无变化)
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


# -------------------------------------------------------------------
# 步骤 4: 构建 Qwen (Prompt 2) - [!!! 最终版高级 Prompt !!!]
# -------------------------------------------------------------------
def build_manim_visualization_prompt(board_segment, narration_segment, duration):
    # 提取板书和讲稿文本
    board_title = board_segment.get("title", "")
    board_lines_str = "\n".join(board_segment.get("lines", []))
    narration_text = narration_segment.get("text", "")

    # [!!!] 这是实现您需求的核心：一个高度定制化的 Prompt [!!!]
    system_prompt = f"""
你是一名顶级的 Manim 动画设计师和 Python 专家，擅长制作精美的数学可视化。
你的任务是为 Manim 场景 `construct(self)` 方法生成一个【Python 代码片段】。

### 核心目标：可视化
你的**首要任务**是根据【讲稿】和【板书】内容创建**生动的图形和动画**（例如椭圆、动点、直线、四边形）。
你的**次要任务**才是展示【板书】文本。

### 严格约束：
1.  **精确同步**：所有 `self.play(...)` 的 `run_time` 和 `self.wait(...)` 的总和，**必须严格等于** {duration:.2f} 秒。
2.  **音频**：代码片段的**第一行**必须是 `self.add_sound("{os.path.join(AUDIO_DIR, narration_segment['to'] + '.mp3')}")`。
3.  **状态管理 (最重要)**：
    * 你**必须**使用 `mobjects_on_screen` 字典来持久化 Mobjects。
    * 例如：`mobjects_on_screen['axes'] = axes`。
    * 例如：`mobjects_on_screen['ellipse'] = ellipse`。
    * 例如：`mobjects_on_screen['k_tracker'] = k_tracker`。
    * **[!!! 关键修复 !!!]** **严禁**在 Mobject (如 VGroup) 上调用 `.has_updaters()` 方法。
    * **[!!! 关键修复 !!!]** 对于 `always_redraw` 的 Mobject (例如 `dynamic_line` 或 `quad`)，你**必须**使用 `self.add(mobject)` 将其添加到场景，**严禁**对其使用 `self.play(Create(mobject))`。
4.  **精美布局 (最重要)**：
    * **严禁重叠**。
    * **可视化区**：所有图形（`Axes`, `Ellipse`, `Dot`, `Line`）**必须**被放置在屏幕左侧。
        * (例如: `axes_group = VGroup(axes, ellipse).to_edge(LEFT, buff=0.5).scale(0.9)`)
    * **板书区**：所有文本（`Tex`, `Text`）**必须**被放置在屏幕右侧。
        * (例如: `board_group = VGroup(b_title, b_line1, ...).to_edge(RIGHT, buff=0.5).scale(0.8)`)
5.  **衔接**：
    * 在动画开始时，使用 `self.play(FadeOut(mobjects_on_screen.get('current_board_text', VGroup())), run_time=1.0)` 来**只清空右侧的旧板书**。
    * **不要**清空 `axes` 或 `ellipse`。
    * 在动画结束时，将**本节的板书**保存到 `mobjects_on_screen['current_board_text'] = board_group` 中。
6.  **文本渲染规则 (固定)**：
    * **标题 (纯中文):** `Text(r"...", font=CN_FONT, weight=BOLD)`。
    * **所有数学/混合内容:** **必须**使用 `Tex(r"...", tex_template=XELATEX_TEMPLATE, font_size=38)`。
    * **必须**将所有数学内容用 `$` 包围。 (例如: `Tex(r"$\text{{椭圆 }} C: \frac{{x^2}}{{a^2}} = 1$", ...)` )
    * **严禁**使用 `MathTex`。
    * **[!!! 关键修复 !!!]** **严禁**使用 `"SimHei"` 字体。**必须**使用 `CN_FONT` 变量。
7.  **时长计算**：你必须自己计算 `total_anim_time`，然后使用 `wait_time = {duration:.2f} - total_anim_time` 来补足 `self.wait(wait_time)`。

---
### [!!!] 特定任务指导 (Qwen 必须遵守) [!!!]

**任务 (b1 - 求椭圆方程):**
* **讲稿提到 "椭圆C" 和 "求...方程"**:
* **动画**:
    1.  `self.play(Write(title_text))` (写标题)。
    2.  `axes = Axes(x_range=[-4, 4, 1], y_range=[-3, 3, 1], ...)`
    3.  `ellipse = Ellipse(width=2*np.sqrt(12), height=2*2, ...)` **展示最终的椭圆** $\frac{{x^2}}{{12}}+\frac{{y^2}}{{4}}=1$。
    4.  `p_dot = Dot(axes.c2p(0, 2), color=YELLOW)` 来标记点 P。
    5.  `self.play(Create(axes), Create(ellipse), Create(p_dot))`
    6.  **保存状态**:
        `mobjects_on_screen['axes'] = axes`
        `mobjects_on_screen['ellipse'] = ellipse`
        `mobjects_on_screen['p_dot'] = p_dot`
* **板书**: 在右侧 `Write` 出 `b1` 的所有 `lines`。

**任务 (b2 - 证明定点):**
* **讲稿提到 "直线AB过定点"**:
* **动画 (必须实现)**:
    1.  **获取状态**: `axes = mobjects_on_screen.get('axes')` (以及 'ellipse', 'p_dot')
    2.  `k_tracker = ValueTracker(1)` (创建一个动态斜率 k)。
    3.  **保存状态**: `mobjects_on_screen['k_tracker'] = k_tracker`
    4.  `m_val = -1` (因为 $y=kx-1$)
    5.  定义 `get_intersection_points()` 函数时，**必须**使用 `x_vals = np.linspace(-np.sqrt(12) + 0.01, np.sqrt(12) - 0.01, 400)` 来避免 `sqrt` 错误。
    6.  **[!!! 关键修复 !!!]** `dynamic_line = always_redraw(lambda: Line(axes.c2p(-4, mobjects_on_screen['k_tracker'].get_value()*(-4) + m_val), ...))` (必须从 mobjects_on_screen 获取)
    7.  `a_dot = always_redraw(...)` (也必须从 mobjects_on_screen 获取 k_tracker)
    8.  `b_dot = always_redraw(...)` (也必须从 mobjects_on_screen 获取 k_tracker)
    9.  **保存状态**: `mobjects_on_screen['a_dot'] = a_dot`, `mobjects_on_screen['b_dot'] = b_dot`
    10. `fixed_dot = Dot(axes.c2p(0, -1), color=RED)` **创建定点**。
    11. `self.add(dynamic_line, a_dot, b_dot)` (使用 `self.add`)
    12. `self.play(Create(fixed_dot))`
    13. `self.play(mobjects_on_screen['k_tracker'].animate.set_value(-1), run_time=...)` 来**演示**直线 $AB$ 扫过定点。
* **板书**: 在右侧逐步 `Write` 出 `b2` 的推导 `lines`。

**任务 (b3 - 求四边形面积):**
* **讲稿提到 "四边形 $F_1AF_2B$"**:
* **动画 (必须实现)**:
    1.  **获取状态**:
        `axes = mobjects_on_screen.get('axes')`
        `k_tracker = mobjects_on_screen.get('k_tracker')`
        `a_dot = mobjects_on_screen.get('a_dot')`
        `b_dot = mobjects_on_screen.get('b_dot')`
    2.  `f1_dot = Dot(axes.c2p(-np.sqrt(8), 0), ...)` (创建焦点 F1)。
    3.  `f2_dot = Dot(axes.c2p(np.sqrt(8), 0), ...)` (创建焦点 F2)。
    4.  **[!!! 关键修复 !!!]** `quad = always_redraw(lambda: Polygon(f1_dot.get_center(), mobjects_on_screen['a_dot'].get_center(), f2_dot.get_center(), mobjects_on_screen['b_dot'].get_center(), ...))` **创建动态四边形**。
    5.  `self.add(quad)` (使用 `self.add`)
    6.  `self.play(Create(f1_dot), Create(f2_dot))`
    7.  `self.play(mobjects_on_screen['k_tracker'].animate.set_value(0.5), run_time=...)` **演示 $k$ 值变化**。
* **板书**: 在右侧 `Write` 出 `b3` 的面积推导 `lines`。
---
""".strip()

    user_prompt = f"""
[约束时长]: {duration:.2f} 秒
[音频文件]: {narration_segment['to']}.mp3

[板书标题]: 【{board_segment['id']}】{board_title}
[板书内容]:
{board_lines_str}

[讲稿 (动画灵感)]:
"{narration_text}"

请严格遵守 System Prompt 中的所有约束 (特别是**可视化**、**布局**、**状态管理**和**[!!!]特定任务指导[!!!]**)，生成精确同步的 Python Manim 代码片段：
""".strip()

    return system_prompt, user_prompt


# -------------------------------------------------------------------
# 步骤 4 (续): 真正调用 Qwen API 的函数
# -------------------------------------------------------------------
async def call_qwen_api(client, system_prompt, user_prompt, segment_id):
    # (此函数无变化)
    print(f"📞 [Qwen Prompt 2] 正在为 {segment_id} 请求可视化代码...")

    payload = {
        "model": QWEN_MODEL,
        "temperature": 0.4,  # 稍微提高一点T，允许AI发挥创意
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
        response = await client.post(QWEN_API_URL, json=payload, headers=headers, timeout=180.0)  # 延长超时
        response.raise_for_status()
        data = response.json()
        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not raw_content:
            print(f"❌ 错误：Qwen API 为 {segment_id} 返回了空内容。")
            return f"        # ERROR: Qwen API returned empty content for {segment_id}\n        self.wait({5.0})"

        cleaned_code = raw_content.replace("```python", "").replace("```", "").strip()
        print(f"✅ [Qwen Prompt 2] 成功接收 {segment_id} 的可视化代码。")
        return cleaned_code

    except httpx.RequestError as e:
        print(f"❌ API 请求失败 ( segment {segment_id} ): {e}")
        return f"        # ERROR: API Request failed for {segment_id}\n        self.wait({5.0})"
    except Exception as e:
        print(f"❌ 处理 API 响应失败 ( segment {segment_id} ): {e}")
        return f"        # ERROR: API Response processing failed for {segment_id}\n        self.wait({5.0})"


# -------------------------------------------------------------------
# 步骤 5: 真正的主编排器 (异步)
# -------------------------------------------------------------------
async def main_orchestrator():
    print("--- 🎬 Manim [真实 AI] 自动化流程 ---")

    # 步骤 1: 加载 plan.json
    try:
        with open(PLAN_FILENAME, "r", encoding="utf-8") as f:
            plan = json.load(f)
        print(f"✅ 成功加载 `{PLAN_FILENAME}`")
    except Exception as e:
        print(f"❌ 加载 `{PLAN_FILENAME}` 时发生错误: {e}")
        sys.exit(1)

    # 步骤 3: 模拟 TTS 并获取时长 (同步执行)
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
        if not segment_id or text is None: continue
        audio_info = mock_call_tts_and_get_duration(text, segment_id, plan)
        audio_durations.append(audio_info)

    durations_dict = {item['id']: item['duration'] for item in audio_durations}
    print(f"📊 时长报告: {json.dumps(audio_durations, indent=2)}")

    json_dump_str = json.dumps(audio_durations, indent=2)
    header_comment = "\n".join([f"# {line}" for line in json_dump_str.splitlines()])

    # 步骤 4: 批量调用 Qwen API 生成可视化代码
    print("\n--- 🐍 开始批量调用 Qwen (Prompt 2) 生成 Manim 可视化 ---")
    all_code_snippets = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for segment in narration_segments:
            segment_id = segment.get("to")
            if not segment_id: continue
            try:
                board_segment = next(item for item in plan["blackboard"] if item["id"] == segment_id)
                duration = durations_dict[segment_id]
            except (StopIteration, KeyError):
                print(f"⚠️ 警告：跳过 {segment_id}，因为找不到匹配的板书或时长。")
                continue

            sys_prompt, user_prompt = build_manim_visualization_prompt(board_segment, segment, duration)
            tasks.append(call_qwen_api(client, sys_prompt, user_prompt, segment_id))

        all_code_snippets = await asyncio.gather(*tasks)

    print("\n---  stitching (拼接) 最终脚本 ---")

    # 步骤 5: 拼接成最终的 Manim 脚本

    script_body_raw = "\n\n".join(all_code_snippets)
    script_body_indented = textwrap.indent(script_body_raw, " " * 8)

    script_footer_raw = """
# --- 脚本结束 ---
print("AI 生成的脚本执行完毕。")
self.play(FadeOut(mobjects_on_screen.get('current_board_text', VGroup())),
          FadeOut(mobjects_on_screen.get('axes', VGroup())),
          FadeOut(mobjects_on_screen.get('ellipse', VGroup())),
          FadeOut(mobjects_on_screen.get('p_dot', VGroup())),
          # 动态对象也需要被移除 (如果存在)
          *[FadeOut(mob) for mob in self.mobjects if hasattr(mob, 'has_updater') and mob.has_updater()]
          ,run_time=0.5)
self.wait(3)
"""
    # [!!! BUG 修复 !!!] 修复了 footer 中的 has_updater() 检查
    script_footer_indented = textwrap.indent(textwrap.dedent(script_footer_raw), " " * 8)

    script_header = f"""from manim import *
import os # 导入 os 以便 add_sound 可以使用
import numpy as np # AI 可能会用到 numpy

# 这是一个由 AI 助手 (Qwen) 动态生成的 Manim 脚本
# 它是基于 {PLAN_FILENAME} 和以下音频时长生成的：
{header_comment}

# 确保您已安装中文字体: {CN_FONT}
CN_FONT = "{CN_FONT}"
AUDIO_DIR = "{AUDIO_DIR}"

# 自动配置一个支持中文的 xelatex 模板 (用于 Tex)
XELATEX_TEMPLATE = TexTemplate(
    tex_compiler="xelatex",
    output_format=".xdv",
    preamble=r"\\usepackage[UTF8]{{ctex}} \\usepackage{{amsmath}} \\usepackage{{amssymb}}"
)

class AutoGeneratedScene(Scene):
    def construct(self):
        # Mobject 跟踪器，用于在步骤间传递对象
        mobjects_on_screen = {{}}
"""

    final_script_content = script_header + "\n" + script_body_indented + "\n\n" + script_footer_indented

    # 步骤 6: 保存所有产物
    try:
        with open(MANIM_SCRIPT_FILENAME, "w", encoding="utf-8") as f:
            f.write(final_script_content)
        print(f"💾 已保存 `{MANIM_SCRIPT_FILENAME}`")
    except Exception as e:
        print(f"❌ 保存 Manim 脚本时出错: {e}")
        sys.exit(1)

    # (生成 run_manim.sh)
    shell_script = f"""#!/bin/bash
echo "--- 正在渲染 AI 生成的视频 (基于 {PLAN_FILENAME}) ---"
manim -pqm {MANIM_SCRIPT_FILENAME} AutoGeneratedScene
"""
    try:
        with open(RUN_SCRIPT_FILENAME, "w", encoding="utf-8") as f:
            f.write(shell_script)
        if os.name != 'nt': os.chmod(RUN_SCRIPT_FILENAME, 0o755)
    except Exception as e:
        print(f"❌ 保存运行脚本时出错: {e}")

    # --- 结束，打印后续步骤 ---
    print("\n\n--- 🎉 [真实 AI] 自动化流程全部完成! ---")
    print("\n下一步操作：\n")
    print("1️⃣ ⚠️ 【重要】创建 '假的' 音频文件：")
    print("   (你之前创建的音频文件可以继续使用，但如果 plan.json 变了，最好重新运行。)\n")

    print(f"   # --- 复制并粘贴以下命令到您的终端 (确保覆盖旧文件) ---")
    print(f"   mkdir -p {AUDIO_DIR}")
    for audio in audio_durations:
        filepath = os.path.join(AUDIO_DIR, audio["file"])
        print(f"   ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 1 -q:a 9 -acodec libmp3lame \"{filepath}\" -y")
    print("   # -------------------------------------\n")

    print("2️⃣ 运行 Manim 渲染：")
    print(f"   ./{RUN_SCRIPT_FILENAME}")


# --- 脚本入口 (使用 asyncio.run) ---
if __name__ == "__main__":
    # 检查 API Key
    if "sk-ffbd" not in QWEN_API_KEY:
        print("=" * 50)
        print("❌ 错误：请在 run_orchestrator_v1.py 脚本顶部")
        print("   的 `QWEN_API_KEY` 常量中填入您自己的 API Key。")
        print("=" * 50)
        sys.exit(1)

    # 检查 httpx
    try:
        import httpx
    except ImportError:
        print("=" * 50)
        print("❌ 错误：未找到 `httpx` 库。")
        print("   请在您的 Manim 环境中运行：")
        print("   pip install httpx")
        print("=" * 50)
        sys.exit(1)

    asyncio.run(main_orchestrator())
