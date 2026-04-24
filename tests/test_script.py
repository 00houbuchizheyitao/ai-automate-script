import pytest

from src.script.validator import ScriptValidator


@pytest.fixture
def validator():
    return ScriptValidator()


class TestScriptValidator:
    def test_valid_script(self, validator):
        script = '''
import pyautogui
import logging

logging.basicConfig(level=logging.INFO)

def main():
    try:
        pyautogui.click(100, 100)
    except Exception as e:
        logging.error(e)

if __name__ == "__main__":
    main()
'''
        result = validator.validate(script)
        assert result["valid"] is True
        assert result["score"] > 0

    def test_syntax_error(self, validator):
        script = "def main(\n"
        result = validator.validate(script)
        assert result["valid"] is False
        assert any("语法错误" in issue for issue in result["issues"])

    def test_dangerous_import(self, validator):
        script = '''
import pyautogui
import os

os.system("rm -rf /")

if __name__ == "__main__":
    pass
'''
        result = validator.validate(script)
        assert any("安全警告" in issue for issue in result["issues"])

    def test_missing_import(self, validator):
        script = '''
if __name__ == "__main__":
    pass
'''
        result = validator.validate(script)
        assert any("缺少必要导入" in issue for issue in result["issues"])
