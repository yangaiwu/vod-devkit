# 验收标准（vod-core）

- [ ] 意图→工具表里的每个工具名都在 `contract/tools.schema.json` 中存在
- [ ] 意图→技能表里的每个技能名都在 `skills/` 中存在
- [ ] 每个非 core 技能都被本技能的某一行引用（无孤儿技能）
- [ ] 路由表不承诺当前传输面没有的工具（远程面：draft/commit/list_submitted 缺失时
      必须就地标注"仅 stdio 面"）
- [ ] `SKILL.md` ≤ 500 行；frontmatter 合规（name=目录名、tags≤5、version 在 metadata 下）
- [ ] 改动后：`tests/test_skill_structure.py` 全绿 + 四宿主装机副本 md5 对齐