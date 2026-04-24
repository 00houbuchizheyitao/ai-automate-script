import ast
import logging

logger = logging.getLogger(__name__)


class ScriptValidator:
    DANGEROUS_IMPORTS = {"os.system", "subprocess.call", "subprocess.Popen", "shutil.rmtree"}
    REQUIRED_IMPORTS = {"pyautogui"}

    def validate(self, script_code: str) -> dict:
        issues = []

        syntax_issue = self._check_syntax(script_code)
        if syntax_issue:
            issues.append(syntax_issue)

        security_issues = self._check_security(script_code)
        issues.extend(security_issues)

        import_issues = self._check_imports(script_code)
        issues.extend(import_issues)

        structure_issues = self._check_structure(script_code)
        issues.extend(structure_issues)

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "score": max(0, 100 - len(issues) * 15),
        }

    @staticmethod
    def _check_syntax(script_code: str) -> str | None:
        try:
            ast.parse(script_code)
            return None
        except SyntaxError as e:
            return f"语法错误: 第{e.lineno}行 - {e.msg}"

    def _check_security(self, script_code: str) -> list[str]:
        issues = []
        for dangerous in self.DANGEROUS_IMPORTS:
            if dangerous in script_code:
                issues.append(f"安全警告: 检测到危险调用 '{dangerous}'")
        return issues

    def _check_imports(self, script_code: str) -> list[str]:
        issues = []
        for required in self.REQUIRED_IMPORTS:
            if required not in script_code:
                issues.append(f"缺少必要导入: '{required}'")
        return issues

    @staticmethod
    def _check_structure(script_code: str) -> list[str]:
        issues = []
        if "if __name__" not in script_code:
            issues.append("建议添加 if __name__ == '__main__' 入口")
        if "try" not in script_code:
            issues.append("建议添加异常处理")
        if "logging" not in script_code:
            issues.append("建议添加日志记录")
        return issues
