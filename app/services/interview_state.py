"""面试状态机。

============================================================
这一块的核心思想（面试必问）：
  把「什么时候问什么」从模型手里拿走，交给代码决定。
  模型只负责「这个问题具体怎么措辞」。

为什么要这样：模型的天性是"一次说很多"。你让它自由发挥，它会：
  1. 一口气问三个问题
  2. 在一个点上无限追问
  3. 聊着聊着跑题
  4. 自己替候选人回答（自问自答）

约束它只有两条路：
  A. 在 prompt 里反复叮嘱 —— 不可靠，模型会忘
  B. 用代码控制流程，prompt 只负责局部 —— 可靠、可测

我们选 B。这就是"状态机"的意义：流程由代码保证，不由模型的自觉保证。
============================================================
"""

import json
import logging
import re

from sqlalchemy.orm import Session

from app.models.interview import InterviewTurn
from app.services.llm import chat

logger = logging.getLogger(__name__)


# ---------- 状态机的定义 ----------

STAGE_FLOW = [
    "self_intro",           # 1. 自我介绍
    "project_deep_dive",    # 2. 项目深挖
    "tech_qa",              # 3. 技术追问
    "candidate_questions",  # 4. 反问环节
]

MAX_ASK_PER_STAGE = {
    "self_intro": 1,
    # ↑ 自我介绍只问一句。问完就进下一阶段 ——
    #   真实面试里不会在自我介绍上纠缠三轮

    "project_deep_dive": 3,
    # ↑ 1 个主问 + 最多 2 层追问。
    #   为什么限 2 层：模型会无限追问下去（"那这个为什么？那那个为什么？"），
    #   真实面试官 2 层就换话题了。这个上限是防死循环的刹车片

    "tech_qa": 3,
    "candidate_questions": 1,
}

MAX_TOTAL_TURNS = 12
# 全局兜底：不管阶段怎么走，总轮次超了就结束。
# 为什么需要双保险：阶段逻辑万一有 bug，这条能保证请求不会无限膨胀

RECENT_TURNS_FULL = 6
# 最近 6 条完整保留，更早的只留问题（丢弃候选人的长回答）


STAGE_LABEL = {
    "self_intro": "自我介绍",
    "project_deep_dive": "项目深挖",
    "tech_qa": "技术追问",
    "candidate_questions": "候选人反问",
}


# ---------- 历史压缩 ----------

def compress_history(turns: list[InterviewTurn]) -> str:
    """把对话历史压成 prompt 里的文本。

    ★ 为什么要压缩：每轮问答都塞进去，10 轮之后输入就有几千 token。
      成本是一方面，更重要的是【模型会失焦】——
      上下文太长时它容易忽略前面的规则，开始一次问多个问题。

    ★ 压缩策略（零成本，不额外调模型）：
      最近的完整保留（模型需要接得上话），
      更早的【只留面试官问过什么】，丢掉候选人的长回答
      （回答里的细节对"下一个问题问什么"影响不大，但很占 token）。
    """
    if not turns:
        return "（面试刚开始）"

    if len(turns) <= RECENT_TURNS_FULL:
        return "\n".join(
            f"{'面试官' if t.role == 'interviewer' else '候选人'}：{t.content}"
            for t in turns
        )

    early = turns[:-RECENT_TURNS_FULL]
    recent = turns[-RECENT_TURNS_FULL:]

    early_questions = [t.content for t in early if t.role == "interviewer"]
    early_text = "【更早的提问（回答已省略）】\n" + "\n".join(
        f"- {q[:60]}" for q in early_questions
    )

    recent_text = "\n".join(
        f"{'面试官' if t.role == 'interviewer' else '候选人'}：{t.content}"
        for t in recent
    )

    return f"{early_text}\n\n【最近对话】\n{recent_text}"


# ---------- 状态机：决定下一步走哪个阶段 ----------

def count_asked_in_stage(turns: list[InterviewTurn], stage: str) -> int:
    """当前阶段面试官已经问了几次。"""
    return sum(1 for t in turns if t.role == "interviewer" and t.stage == stage)


def decide_next_stage(current_stage: str, turns: list[InterviewTurn]) -> str:
    """根据"当前阶段问了几次"，决定下一个问题属于哪个阶段。

    这就是状态机的全部 —— 一段纯函数，不涉及 LLM，可以单独测。
    """
    asked = count_asked_in_stage(turns, current_stage)
    limit = MAX_ASK_PER_STAGE.get(current_stage, 1)

    if asked < limit:
        return current_stage          # 还在本阶段，继续追问

    # 本阶段问够了 → 进入下一个阶段
    try:
        idx = STAGE_FLOW.index(current_stage)
    except ValueError:
        return STAGE_FLOW[-1]

    if idx + 1 < len(STAGE_FLOW):
        return STAGE_FLOW[idx + 1]

    return STAGE_FLOW[-1]             # 已经是最后一个阶段


# ---------- 生成问题 ----------

QUESTION_SYSTEM = """你是一位技术面试官，正在面试一名应届生。

【本轮的阶段】{stage_label}

【本阶段的任务】
{stage_task}

【硬性规则 —— 违反任何一条都算失败】
1. 每次只能问【一个】问题，绝对不能在一句话里问两件事
2. 不要自己回答这个问题，也不要替候选人假设答案
3. 不要写"好的""明白了"这类寒暄，直接问
4. 问题要具体，能落到项目和代码上，不要问"你有什么优点"这种空话
5. 如果能从简历里找到素材，优先针对简历里的真实项目提问

【输出格式】
只输出一个 JSON 对象：
{{"question": "你要问的那一句话"}}
"""

STAGE_TASK = {
    "self_intro": "让候选人介绍自己，重点问他的项目和技术栈。",
    "project_deep_dive": (
        "针对候选人提到的项目深入追问：他具体负责什么、技术选型为什么这么定、"
        "遇到过什么问题、怎么解决的。每次挑一个点往下挖一层。"
    ),
    "tech_qa": (
        "考察基础功底：根据简历里写到的技术，问一个具体的原理题"
        "（比如为什么索引能加速、GIL 是什么、事务隔离级别）。"
    ),
    "candidate_questions": (
        "面试接近尾声，请候选人提问。只问一句：你有什么想问我的吗？"
    ),
}


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ValueError("模型返回里找不到 JSON")


def generate_question(
    *,
    stage: str,
    resume_summary: str,
    history_text: str,
    last_answer: str = "",
) -> str:
    """让模型生成本阶段的【一个】问题。"""
    system = QUESTION_SYSTEM.format(
        stage_label=STAGE_LABEL.get(stage, stage),
        stage_task=STAGE_TASK.get(stage, ""),
    )

    user = f"""【候选人的简历摘要】
{resume_summary[:1500]}

【已有对话】
{history_text}
"""
    if last_answer:
        user += f"""
【候选人刚才的回答】
{last_answer[:800]}

请针对这个回答，在「{STAGE_LABEL.get(stage, stage)}」阶段提出下一个问题。
"""
    else:
        user += "\n请提出第一个问题。"

    raw, in_tok, out_tok = chat(system, user, json_mode=True)
    logger.info("生成问题 stage=%s 输入=%d 输出=%d", stage, in_tok, out_tok)

    data = _extract_json(raw)
    question = (data.get("question") or "").strip()

    if not question:
        raise ValueError("模型没有生成问题")

    return question


# ---------- 面试总结 ----------

SUMMARY_SYSTEM = """你是一位技术面试官，面试刚刚结束。请给候选人一份简短评估。

只输出 JSON：
{
  "summary": "两三句话总评，指出最大亮点和最大问题",
  "strengths": ["表现好的具体点"],
  "weaknesses": ["需要补的具体点"],
  "score": 70
}

要求：
1. 基于实际对话内容，不要编造候选人没说过的东西
2. score 0-100，按应届生标准打分
3. weaknesses 要具体到"哪个问题没答好、缺什么知识"，不要写"基础不扎实"这种空话
"""


def generate_summary(history_text: str) -> dict:
    """面试结束后生成评估。"""
    raw, in_tok, out_tok = chat(SUMMARY_SYSTEM, history_text[-6000:], json_mode=True)
    logger.info("生成总结 输入=%d 输出=%d", in_tok, out_tok)
    return _extract_json(raw)
