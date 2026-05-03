---
alwaysApply: false
description: 生成Git提交信息时生效
scene: git_message
---
# Git 提交信息规范

请遵循 Conventional Commits 规范生成提交信息。格式如下：
<类型>(<范围>): <描述>

## 类型 (Type) 规定：
- feat: 新功能 (feature)
- fix: 修补 bug
- docs: 文档修改 (documentation)
- style: 格式修改 (不影响代码运行的变动)
- refactor: 重构 (即不是新增功能，也不是修改bug的代码变动)
- chore: 构建过程或辅助工具的变动
- perf: 性能优化

## 风格建议：
- 使用简体中文描述。
- 描述应简洁明了，结尾不加句号。
- 范围 (scope) 是可选的，可以写模块名（如：ui, llm, core）。

## 示例：
- feat(ui): 添加截图上传按钮
- fix(llm): 修复 Ollama 连接超时问题
- docs: 更新项目安装说明
