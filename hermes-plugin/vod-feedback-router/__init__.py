"""vod-feedback-router：强制评估钩子插件（forced-eval，业界 ~84% 激活率模式）。"""
from . import router


def register(ctx):
    ctx.register_hook("pre_llm_call", router._on_pre_llm_call)
