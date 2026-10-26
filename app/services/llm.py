import logging
import time 

from openai import OpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_client: OpenAI | None = None

def get_llm() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=60.0,
        )
    return _client

def chat(
    system:str,
    user:str,
    *,
    json_mode:bool = False,
    retries:int = 1,
) -> tuple[str,int,int]:
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            start = time.perf_counter()

            kwargs = {
                "model": settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
            }
            if json_mode:
                kwargs["response_format"] = {"type":"json_object"}

            resp =get_llm().chat.completions.create(**kwargs)

            input_tokens = resp.usage.prompt_tokens
            output_tokens = resp.usage.completion_tokens
            elapsed = (time.perf_counter() - start) * 1000

            logger.info(
                "LLM 调用成功 model=%s 输入=%d 输出=%d 耗时=%.0fms",
                settings.deepseek_model, input_tokens, output_tokens, elapsed,
            )

            return resp.choices[0].message.content or "", input_tokens, output_tokens

        except Exception as exc:
            last_error = exc
            logging.warning("LLM 调用失败（第 %d 次）：%s", attempt + 1, exc)
            if attempt < retries:
                time.sleep(1.5 ** attempt)

    raise RuntimeError(f"LLM 调用失败：{last_error}") from last_error