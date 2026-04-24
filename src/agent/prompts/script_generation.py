SCRIPT_GENERATION_PROMPT = """基于以下信息生成Windows自动化脚本：

## 截图分析结果
{analysis}

## 用户需求
{user_requirement}

## OCR 识别文字
{ocr_text}

请生成一个完整的Python脚本，要求：
1. 包含所有必要的 import 语句
2. 使用 pyautogui 进行鼠标键盘操作
3. 使用 cv2 + mss 进行图像定位
4. 如果截图分析中提到用户标注了某个元素，脚本中应包含定位并操作该元素的逻辑
5. 包含适当的等待和重试逻辑
6. 包含异常处理
7. 添加中文注释
8. 脚本可直接运行

输出格式：
```python
# 脚本代码
```
"""

SCRIPT_GENERATION_TEXT_ONLY_PROMPT = """用户需求：{user_requirement}

请生成一个完整的Windows自动化Python脚本，要求：
1. 包含所有必要的 import 语句
2. 使用 pyautogui 进行鼠标键盘操作
3. 包含适当的等待和重试逻辑
4. 包含异常处理
5. 添加中文注释
6. 脚本可直接运行

输出格式：
```python
# 脚本代码
```
"""

SCRIPT_REFINEMENT_PROMPT = """以下脚本在验证时发现问题，请修正：

## 原始脚本
{original_script}

## 问题描述
{issues}

## 截图分析
{analysis}

请生成修正后的完整脚本。
"""
