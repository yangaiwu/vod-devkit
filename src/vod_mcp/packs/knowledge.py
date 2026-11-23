"""knowledge pack：规则技能披露薄壳（实现在 skills_registry，本层只做错误码转译）。"""
from vod_mcp import errors

def list_skills(params: dict, client_info: dict | None = None) -> dict:
    from vod_mcp import skills_registry as sr
    try:
        return sr.list_skills(params)
    except sr.SkillError as e:
        raise errors.ToolError(str(e), code=e.code)


def retrieve_skill(params: dict, client_info: dict | None = None) -> dict:
    from vod_mcp import skills_registry as sr
    try:
        return sr.retrieve_skill(params)
    except sr.SkillError as e:
        raise errors.ToolError(str(e), code=e.code)
