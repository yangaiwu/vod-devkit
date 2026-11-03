---
name: vod-category-matching-rules
description: VOD分类匹配规则 — 功能子类关键词词典、四级匹配策略、AI匹配约束规则
---

# VOD分类匹配规则

## 四级匹配策略

匹配顺序: 三级特性(L3) → 二级特性(L2) → 功能子类 → 功能大类

每级先做关键词预匹配，再用AI语义匹配，最后做校验修正。

## 功能子类关键词词典

| 功能子类 | 关键词 |
|---------|--------|
| 内置Tools | 内置工具、内置tool、bash、batch、terminal、内置命令、tool调用、工具调用 |
| 内置浏览器 | 浏览器、browser、webview、网页预览、页面预览、图片无法展示、图标消失 |
| AI IDE安装 | 安装、install、部署、下载、更新版本、卸载、软件包 |
| 系统登录 | 登录、login、鉴权、认证、账号、注册 |
| IDE插件安装&升级&卸载 | 插件报错、插件崩溃、插件卡、idea报错、vscode报错、插件异常、插件安装 |
| ASK代码问答 | 对话、问答、ask、聊天、提问、回答、ai对话、智能体对话、回复慢、会话 |
| Agent入口 | agent入口、模式切换、agent模式、智能体模式、doer模式 |
| CodeAgent项目级代码生成 | codeagent、代码生成、项目级、智能编码、自动编码、figma、设计稿 |
| 模型能力 | 模型、model、推理、token、排队、限流、配额、模型响应、deepseek、glm、qwen |

## AI匹配约束规则（关键）

1. 严禁将产品BUG/功能需求/体验问题归到"问题反馈"分类
   - "问题反馈"仅限反馈功能本身的问题（反馈入口打不开、截图上传失败）
2. "卡顿与响应慢"仅限真正的性能问题
   - 严禁把功能需求、体验优化、数据异常、UI交互、安装失败归到此类
3. 功能需求/体验优化类不要选"卡顿与响应慢"，应选对应功能子类
4. 数据异常类不要选"卡顿与响应慢"，应选对应功能子类
5. 选择"卡顿与响应慢"时必须根据具体功能选正确子类:
   - AI对话慢→智能体对话
   - 代码补全慢→代码续写
   - IDE整体卡→IDE设置
   - 插件崩溃→IDE插件安装
   - 安装慢→AI IDE安装
   - 模型响应慢→模型能力
6. 谨慎选择: 能看出功能领域的应选对应子类，只有纯情绪发泄/正向评价才输出0

## AI匹配输出格式

```
分析：[推理过程，20-30字]
序号：[数字]
```

## 分类配置文件

- 分类树: `product_profiles/codearts/categories.json` (1614行，430+候选分类)
- 短名映射: `product_profiles/codearts/short_name.json`
- 产品配置: `product_profiles/codearts/profile.json`

## 实现位置

- Python: `workflow/src/category_matcher.py` (941行，最大模块)
- AI调用: `_call_llm_match()` 多模型轮转
- 缓存: 线程安全 `_categories_cache`
