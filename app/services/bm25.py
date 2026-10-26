"""BM25 关键词检索（手写精简版，零依赖）。

★ 为什么需要它：
  向量检索看"意思像不像"，但对【专有名词、缩写、型号、错别字】很弱 ——
  模型没见过的词，向量是随机的。
  BM25 看"这个词出现了没有、出现几次"，正好补这个短板。

★ 为什么手写不用 rank_bm25 库：
  一共 60 行，原理全透明；而 BM25 的公式本身值得你理解（面试常问）。

★ 中文怎么分词：
  英文靠空格切词，中文没有空格。生产上一般用 jieba；
  这里用【字符二元组】(2-gram)：把"缓存穿透"切成 缓存/存穿/穿透。
  不做词性分析，但召回率够用，且零依赖。
"""

import math
import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    """中文用字符 2-gram 当"词"。

    例：「缓存穿透」→ ['缓存', '存穿', '穿透']
    """
    text = re.sub(r"\s+", "", text)        # 去掉所有空白
    if len(text) < 2:
        return [text] if text else []
    return [text[i : i + 2] for i in range(len(text) - 1)]


class BM25:
    """BM25 打分器。

    参数 k1 : 控制"词频的饱和速度"。一个词出现 10 次和 100 次，
              对相关性的贡献差距会被 k1 压平（避免刷词）。默认 1.5
    参数 b  : 控制"文档长度归一化"的强度。0 = 完全不看长度，
              1 = 完全按长度惩罚。默认 0.75
    """

    def __init__(self, corpus: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus = corpus
        self.n_docs = len(corpus)
        self.doc_len = [len(d) for d in corpus]
        self.avg_len = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0

        self.term_freq = [Counter(d) for d in corpus]

        # document frequency：有多少篇文档包含某个词
        self.doc_freq: Counter = Counter()
        for doc in corpus:
            for term in set(doc):
                self.doc_freq[term] += 1

    def idf(self, term: str) -> float:
        """逆文档频率：越少见的词，权重越高。

        「的」「是」这种到处都有的词 → idf 接近 0，几乎不影响打分；
        「SETNX」只在 1 篇里出现 → idf 很高，命中就大幅加分。
        """
        df = self.doc_freq.get(term, 0)
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    def score(self, query_terms: list[str], index: int) -> float:
        """给第 index 篇文档打一个相关性分。"""
        total = 0.0
        freqs = self.term_freq[index]
        length = self.doc_len[index] or 1

        for term in query_terms:
            f = freqs.get(term, 0)
            if f == 0:
                continue
            # BM25 主公式：词频饱和 + 长度归一化
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (
                1 - self.b + self.b * length / (self.avg_len or 1)
            )
            total += self.idf(term) * numerator / denominator

        return total

    def rank(self, query: str) -> list[tuple[int, float]]:
        """返回 [(文档下标, 分数)]，按分数从高到低。"""
        query_terms = tokenize(query)
        scored = [(i, self.score(query_terms, i)) for i in range(self.n_docs)]
        scored = [item for item in scored if item[1] > 0]   # 0 分的不返回
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
