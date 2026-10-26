import json
import logging
import re

from app.db.session import SessionLocal
from app.models.analysis import Analysis
from app.models.resume import Resume
from app.schemas.analysis import AnalysisResult
from app.services.llm import chat

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位资深技术面试官，正在帮应届生评估简历与岗位的匹配度。

严格按下面的 JSON 结构输出，字段名必须用英文，一字不能改：

{
  "score": 75,
  "summary": "一句话总评，说明最大的优势和最大的短板",
  "matched": ["简历中符合岗位要求的点，引用原文关键词"],
  "gaps": ["岗位要求但简历中没有体现的能力"],
  "suggestions": ["具体可执行的改法，不要说'加强学习'这种空话"]
}

打分标准：
- 90+ ：几乎完全匹配，可以直接面试
- 70-89：核心要求满足，有明显短板
- 50-69：部分满足，需要补关键能力
- 50以下：方向不匹配

要求：
1. 只输出 JSON，不要解释、不要 markdown 代码块
2. gaps 和 suggestions 必须一一对应（每个 gap 有一条对应的建议）
3. suggestions 要具体到"改哪句话、加什么内容"，不要泛泛而谈
4. 不要编造简历里没有的经历
"""
def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise ValueError("模型返回里找不到可解析的 JSON")

def analyze(resume_text: str, parsed_summary: str, jd_text: str) -> AnalysisResult:
    user_content = f"""【简历结构化信息】
{parsed_summary}
【简历原文（节选）】
{resume_text[:3000]}

【岗位 JD】
{jd_text}

请按要求输出 JSON。"""
    raw, in_tok, out_tok = chat(SYSTEM_PROMPT, user_content, json_mode=True)
    logger.info("分析完成 输入=%d 输出=%d", in_tok, out_tok)

    return AnalysisResult.model_validate(_extract_json(raw))

def run_analysis_task(analysis_id: int) -> None:
     with SessionLocal() as db:
        analysis = db.get(Analysis, analysis_id)
        if analysis is None:
            logger.warning("分析任务找不到记录 id=%s", analysis_id)
            return

        analysis.status = "running"
        db.commit()

        try:
            resume = db.get(Resume, analysis.resume_id)
            if resume is None:
                raise ValueError("简历不存在")

            # 用已解析的结构化信息做摘要，比直接塞全文更省 token
            parsed_summary = resume.parsed_json[:2000] if resume.parsed_json else "（未解析）"

            result = analyze(resume.raw_text, parsed_summary, analysis.jd_text)

            analysis.result_json = json.dumps(result.model_dump(), ensure_ascii=False)
            analysis.score = result.score
            analysis.status = "done"

        except Exception as exc:
            logger.exception("分析失败 id=%s", analysis_id)
            analysis.status = "failed"
            analysis.error = str(exc)[:500]

        db.commit()