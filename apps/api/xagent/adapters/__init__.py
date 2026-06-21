"""适配层：把成熟开源底座（LiteLLM / Langfuse / Qdrant / ...）封装为
X-Agent 内部统一的 Protocol 抽象，core 与 domains 只依赖抽象，不依赖具体库。

每个子包结构：
    base.py     —— Protocol 抽象 + 数据类型
    *_impl.py   —— 具体开源实现
    null.py     —— lite/测试用降级实现
    factory.py  —— 据 settings 返回实例（lru_cache 单例）
"""
