import json
import re

from app.schemas.resume import ResumeParsed
from app.services.llm import chat

SYSTEM_PROMPT = """你是简历解析器。规则：

1. 只输出 JSON，不要任何解释、不要 markdown 代码块
2. 严格按下面的结构，**字段名必须用英文，一字不能改**
3. 原文里没有的信息，给空字符串或空数组，**绝对不要编造**
4. highlights 里每条是一句话，保留原文的能力描述和数字

结构示例：
{
  "name": "张三",
  "phone": "13800000000",
  "email": "zhangsan@example.com",
  "skills": ["Python", "FastAPI"],
  "projects": [
    {"name": "某项目", "tech": ["FastAPI"], "highlights": ["用 FastAPI 搭建后端，支持下单"]}
  ],
  "education": "某某大学 软件工程 本科 2023.09-2027.06"
}"""

def _extract_json(text: str) -> dict:
    """从模型返回里抠出 JSON（第三层防线）。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start : end + 1])

    raise ValueError("模型返回里找不到可解析的 JSON")

def parse_resume(text: str) -> tuple[ResumeParsed, int, int]:
    trimmed = text[:8000]

    raw, input_tokens, output_tokens = chat(
        SYSTEM_PROMPT, trimmed, json_mode=True
    )

    data = _extract_json(raw)                  # 第三层
    parsed = ResumeParsed.model_validate(data) # 第四层
    return parsed, input_tokens, output_tokens
