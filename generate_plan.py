#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 1: 从 LaTeX 数学题目和解答生成详细的教学计划 (plan.json)
"""
import json
import sys
import httpx
import asyncio

# API 配置
QWEN_API_KEY = "sk-ffbdc6a6150442ad974d33561ecf6953"
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen3-max"

OUTPUT_FILENAME = "plan.json"


def build_plan_generation_prompt(latex_problem: str, latex_solution: str) -> tuple[str, str]:
    """
    构建用于生成 plan.json 的通用 Prompt

    Args:
        latex_problem: LaTeX 格式的题目
        latex_solution: LaTeX 格式的完整解答

    Returns:
        (system_prompt, user_prompt)
    """

    system_prompt = """你是一名资深的数学教师和教学设计专家。你的任务是将一道数学题目和它的完整解答，拆解成适合制作教学视频的**详细教学计划**。

# 输出格式要求

你必须输出一个严格符合以下JSON Schema的结构：

```json
{
  "meta": {
    "title": "题目简短标题",
    "topic": "所属数学领域（如：解析几何-椭圆与直线关系）",
    "level": "学习阶段（如：高中/大学）",
    "difficulty": "难度等级（如：基础/进阶/挑战）",
    "learningObjectives": ["学习目标1", "学习目标2", ...]
  },
  "blackboard": [
    {
      "id": "b1",
      "title": "板书段落标题",
      "lines": [
        "板书第1行（LaTeX格式，用$包围数学内容）",
        "板书第2行",
        ...
      ],
      "notes": "可选的教学提示"
    },
    ...
  ],
  "narration": [
    {
      "to": "b1",
      "text": "对应b1的讲稿文本",
      "seconds": 估算的讲解时长（秒）,
      "intent": "这段讲解的意图（如：铺垫/推导/强调）"
    },
    ...
  ],
  "pitfalls": [
    "常见错误点1",
    "常见错误点2",
    ...
  ],
  "wrapup": {
    "summary": "本题总结",
    "takeaways": ["关键要点1", "关键要点2", ...]
  }
}
```

# 核心原则

1. **板书和讲稿一一对应**: 每个 blackboard[i] 必须有一个 narration[i]，它们通过 id 关联
2. **拆分要足够细**: 一个复杂的推导过程要分成多个小步骤（b1, b2, b3...），每步都有独立的板书和讲稿
3. **板书内容要精炼**: 每个 lines 数组应该只包含该步骤最关键的公式和结论，避免冗长
4. **讲稿要详细**: 讲稿要比板书更详细，包含思路引导、关键技巧点拨等
5. **时长合理**: 根据内容复杂度估算讲解时长，一般每步10-25秒
6. **LaTeX格式**: 板书中的数学内容必须用 $ 包围，如 "$\\frac{x^2}{a^2} + \\frac{y^2}{b^2} = 1$"

# 教学设计策略

- **起始段 (b1)**: 先读题，列出已知条件和待求目标
- **推导段 (b2-bN)**: 逐步推导，每段专注一个小目标
- **结论段 (bN+1)**: 总结答案和关键方法
- **注意**: 不要把所有公式堆在一个板书里，要像真正的老师一样分步讲解

# 数学内容适配性

你的设计必须是**通用的**，适用于各种数学题目类型：
- 代数：方程求解、不等式、函数性质
- 几何：解析几何、立体几何、三角函数
- 微积分：极限、导数、积分
- 概率统计：概率计算、分布、统计推断
- 其他任何中学到大学阶段的数学题目

不要在输出中包含任何特定题目类型的硬编码逻辑。
"""

    user_prompt = f"""请根据以下题目和解答，生成详细的教学计划JSON：

【题目（LaTeX格式）】
{latex_problem}

【完整解答（LaTeX格式）】
{latex_solution}

请严格按照 System Prompt 中的 JSON Schema 输出，确保：
1. 板书拆分足够细（至少5-10个段落）
2. 每个板书都有对应的讲稿
3. 讲稿要详细生动，富有启发性
4. 时长估算合理（总时长建议在2-5分钟）
5. 所有数学内容都使用LaTeX格式并用$包围

现在请输出完整的 JSON（不要用markdown代码块包围，直接输出JSON）：
"""

    return system_prompt.strip(), user_prompt.strip()


async def call_qwen_api(system_prompt: str, user_prompt: str) -> dict:
    """
    调用 Qwen API 生成 plan.json

    Returns:
        解析后的 JSON 字典
    """
    print("📞 正在调用 Qwen API 生成教学计划...")

    payload = {
        "model": QWEN_MODEL,
        "temperature": 0.3,  # 较低温度确保结构化输出
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }

    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                QWEN_API_URL,
                json=payload,
                headers=headers,
                timeout=180.0
            )
            response.raise_for_status()
            data = response.json()
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            if not raw_content:
                raise ValueError("API 返回了空内容")

            # 清理可能的 markdown 代码块包围
            cleaned_content = raw_content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.startswith("```"):
                cleaned_content = cleaned_content[3:]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()

            # 解析 JSON
            plan_data = json.loads(cleaned_content)
            print("✅ 成功生成教学计划")
            return plan_data

        except httpx.RequestError as e:
            print(f"❌ API 请求失败: {e}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析失败: {e}")
            print(f"返回内容: {raw_content[:500]}...")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            sys.exit(1)


async def main():
    """主函数"""
    print("=" * 60)
    print("Stage 1: 数学题可视化讲解 - 教学计划生成器")
    print("=" * 60)

    # 从命令行参数或交互式输入获取题目和解答
    if len(sys.argv) >= 3:
        problem_file = sys.argv[1]
        solution_file = sys.argv[2]

        try:
            with open(problem_file, 'r', encoding='utf-8') as f:
                latex_problem = f.read().strip()
            with open(solution_file, 'r', encoding='utf-8') as f:
                latex_solution = f.read().strip()
        except FileNotFoundError as e:
            print(f"❌ 文件不存在: {e}")
            sys.exit(1)
    else:
        print("\n使用方法:")
        print("  python generate_plan.py <题目文件.txt> <解答文件.txt>")
        print("\n或者直接运行，然后交互式输入\n")

        print("请输入题目（LaTeX格式，输入完成后按 Ctrl+D (macOS/Linux) 或 Ctrl+Z (Windows)）:")
        latex_problem = sys.stdin.read().strip()

        print("\n请输入完整解答（LaTeX格式，输入完成后按 Ctrl+D 或 Ctrl+Z）:")
        latex_solution = sys.stdin.read().strip()

    if not latex_problem or not latex_solution:
        print("❌ 题目和解答不能为空")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("输入信息:")
    print(f"题目长度: {len(latex_problem)} 字符")
    print(f"解答长度: {len(latex_solution)} 字符")
    print("=" * 60 + "\n")

    # 构建 Prompt
    system_prompt, user_prompt = build_plan_generation_prompt(latex_problem, latex_solution)

    # 调用 API
    plan_data = await call_qwen_api(system_prompt, user_prompt)

    # 验证基本结构
    required_keys = ["meta", "blackboard", "narration"]
    for key in required_keys:
        if key not in plan_data:
            print(f"⚠️ 警告: 生成的计划缺少必需字段 '{key}'")

    # 检查板书和讲稿是否匹配
    board_ids = {item["id"] for item in plan_data.get("blackboard", [])}
    narration_ids = {item["to"] for item in plan_data.get("narration", [])}

    if board_ids != narration_ids:
        print(f"⚠️ 警告: 板书ID和讲稿ID不匹配")
        print(f"  板书ID: {board_ids}")
        print(f"  讲稿ID: {narration_ids}")

    # 保存到文件
    try:
        with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(plan_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 教学计划已保存到: {OUTPUT_FILENAME}")
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")
        sys.exit(1)

    # 打印统计信息
    num_boards = len(plan_data.get("blackboard", []))
    total_duration = sum(item.get("seconds", 0) for item in plan_data.get("narration", []))

    print("\n" + "=" * 60)
    print("生成统计:")
    print(f"  板书段落数: {num_boards}")
    print(f"  预计总时长: {total_duration:.1f} 秒 ({total_duration/60:.1f} 分钟)")
    print(f"  题目主题: {plan_data.get('meta', {}).get('topic', 'N/A')}")
    print("=" * 60)

    print("\n下一步: 运行 Stage 2 生成 Manim 代码")
    print(f"  python run_orchestrator_v2.py")


if __name__ == "__main__":
    asyncio.run(main())
