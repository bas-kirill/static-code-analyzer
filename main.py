import logging
import logging.config
import os.path
import sys
import typing
from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from typing import List
import re

COMMENT_SEP = "#"


@dataclass(frozen=True, order=True)
class Line:
    pos: int = field(compare=True)
    content: str = field(compare=False)

    def __getitem__(self, item):
        if item not in ("pos", "content"):
            raise KeyError
        return getattr(self, item)


class LineFormatter:
    @staticmethod
    def remove_comment(line: Line) -> Line:
        comment_pos = line.content.find(COMMENT_SEP)
        if comment_pos == -1:
            return line
        new_line = Line(line.pos, line.content[:comment_pos])
        return new_line

    @staticmethod
    def remove_finishing_spaces(line: Line) -> Line:
        new_line = Line(line.pos, line.content.rstrip())
        return new_line

    @staticmethod
    def remove_leading_spaces(line: Line) -> Line:
        new_line = Line(line.pos, line.content.lstrip())
        return new_line


@dataclass(frozen=True)
class IssueCode:
    code: str
    description: str

    def __getitem__(self, item):
        if item not in ("code", "description"):
            raise KeyError
        return getattr(self, item)


class IssueCodes:
    DUMMY = IssueCode("-1", "Error dummy")  # instead of None
    MAX_LENGTH = IssueCode("S001", "Too long")
    INDENTATION_MULTIPLE_FOUR = IssueCode("S002",
                                          "Indentation is not a multiple of four")
    UNNECESSARY_SEMICOLON = IssueCode("S003",
                                      "Unnecessary semicolon")
    AT_LEAST_2_SPACES_BEFORE_INLINE_COMMENT = IssueCode("S004",
                                                        "At least two spaces required before inline comments")
    TODO_FOUND = IssueCode("S005", "TODO found")
    MORE_TWO_BLANK_LINES_PRECEDING_CODE_LINE = IssueCode("S006",
                                                         "More than two blank lines used before this line")
    TOO_MANY_SPACES_AFTER_DEF_OR_CLASS = IssueCode("S007",
                                                   "Too many spaces after construction_name (def or class)")
    CLASS_NAME_IN_CAMEL_CASE = IssueCode("S008",
                                         "Class name class_name should be written in CamelCase")
    FUNCTION_NAME_IN_SNAKE_CASE = IssueCode("S009",
                                            "Function name function_name should be written in snake_case")


class PEP8Rule(ABC):
    @abstractmethod
    def check(self, line: Line):
        pass


class MaxLineLength(PEP8Rule):
    _PEP8_MAX_LINE_LENGTH = 79

    def check(self, line: Line) -> IssueCode:
        if len(line.content) > self._PEP8_MAX_LINE_LENGTH:
            return IssueCodes.MAX_LENGTH
        return IssueCodes.DUMMY


class IndentationMultipleOfFour(PEP8Rule):
    def check(self, line: Line) -> IssueCode:
        line_len = len(line.content)
        leading_spaces_cnt = len(line.content.lstrip())
        if (line_len - leading_spaces_cnt) % 4 != 0:
            return IssueCodes.INDENTATION_MULTIPLE_FOUR
        return IssueCodes.DUMMY


class UnnecessarySemicolonAfterStatement(PEP8Rule):
    # note that semicolons are acceptable in comments
    _SEMICOLON_SEP = ";"

    def check(self, line: Line):
        new_line = LineFormatter.remove_comment(line)
        new_line = LineFormatter.remove_finishing_spaces(new_line)
        if len(new_line.content) > 0 and new_line.content[
            -1] == self._SEMICOLON_SEP:
            return IssueCodes.UNNECESSARY_SEMICOLON
        return IssueCodes.DUMMY


class AtLeastTwoSpacesBeforeInlineComment(PEP8Rule):
    def check(self, line: Line):
        new_line = LineFormatter.remove_leading_spaces(line)
        if new_line.content.startswith(COMMENT_SEP):
            return IssueCodes.DUMMY

        try:
            comment_sep_pos = new_line.content.index(COMMENT_SEP)
        except ValueError:
            return IssueCodes.DUMMY

        idx, spaces_cnt = comment_sep_pos - 1, 0
        while idx >= 0 and line.content[idx].isspace():
            spaces_cnt += 1
            idx -= 1

        if spaces_cnt < 2:
            return IssueCodes.AT_LEAST_2_SPACES_BEFORE_INLINE_COMMENT
        return IssueCodes.DUMMY


class TodoFound(PEP8Rule):
    # in comments only and case-insensitive
    _TODO_KEYWORD = "todo"

    @staticmethod
    def _extract_comment(line):
        try:
            comment_sep_pos = line.content.index(COMMENT_SEP)
        except ValueError:
            return ""

        comment = line.content[comment_sep_pos:]
        return comment

    def check(self, line: Line):
        comment = TodoFound._extract_comment(line)
        comment = comment.lower()
        if comment.count(self._TODO_KEYWORD):
            return IssueCodes.TODO_FOUND
        return IssueCodes.DUMMY


class MoreThanTwoBlankLinesPrecedingCodeLine(PEP8Rule):
    def __init__(self):
        self.prev_lines = None

    def set_prev_lines(self, prev_lines: List[Line]):
        self.prev_lines = prev_lines

    def check(self, line: Line):
        if len(self.prev_lines) <= 2:
            return IssueCodes.DUMMY
        if self.prev_lines[-3].content == self.prev_lines[-2].content == \
            self.prev_lines[-1].content == "":
            return IssueCodes.MORE_TWO_BLANK_LINES_PRECEDING_CODE_LINE
        return IssueCodes.DUMMY


class TooManySpacesAfterClass(PEP8Rule):
    @staticmethod
    def is_class_declaration(line: Line):
        class_template = r"^class\s+[\w\d]+\(*.*?\)*:\s*"
        is_class = re.match(class_template, line.content) is not None
        return is_class

    def check(self, line: Line):
        new_line = LineFormatter.remove_leading_spaces(line)

        if not TooManySpacesAfterClass.is_class_declaration(new_line):
            return IssueCodes.DUMMY

        class_template = r"^class\s[\w\d]+\(*.*?\)*:\s*"
        is_class_one_space = re.match(class_template,
                                      new_line.content) is not None
        if not is_class_one_space:
            return IssueCodes.TOO_MANY_SPACES_AFTER_DEF_OR_CLASS
        return IssueCodes.DUMMY


class TooManySpacesAfterDef(PEP8Rule):
    @staticmethod
    def is_def_declaration(line: Line):
        def_template = r"^def\s+[\w\d]+\(.*?\):\s*"
        is_def = re.match(def_template, line.content) is not None
        return is_def

    def check(self, line: Line):
        new_line = LineFormatter.remove_leading_spaces(line)

        if not TooManySpacesAfterDef.is_def_declaration(new_line):
            return IssueCodes.DUMMY

        def_temp = r"^def\s_*[\w\d]+\(.*?\):\s*"
        is_def_one_space = re.match(def_temp, new_line.content) is not None
        if not is_def_one_space:
            return IssueCodes.TOO_MANY_SPACES_AFTER_DEF_OR_CLASS
        return IssueCodes.DUMMY


class ClassNameInCamelCase(PEP8Rule):
    @staticmethod
    def is_class_declaration(line: Line) -> bool:
        class_template = r"class\s+[\w\d]+\(*.*\)*:\s*$"
        return re.match(class_template, line.content) is not None

    @staticmethod
    def is_def_declaration(line: Line) -> bool:
        def_template = r"def\s+[\w\d_]+\(.*\):\s*$"
        return re.match(def_template, line.content) is not None

    def check(self, line: Line):
        new_line = LineFormatter.remove_leading_spaces(line)
        if not ClassNameInCamelCase.is_class_declaration(new_line):
            return IssueCodes.DUMMY
        class_name_camel_case = r"^class\s+([A-Z][a-z]+)+\(*.*?\)*:"
        if re.match(class_name_camel_case, new_line.content) is None:
            return IssueCodes.CLASS_NAME_IN_CAMEL_CASE
        return IssueCodes.DUMMY


class FunctionNameInSnakeCase(PEP8Rule):
    @staticmethod
    def is_def_declaration(line: Line) -> bool:
        def_template = r"def\s+[\w\d_]+\(.*\):\s*$"
        return re.match(def_template, line.content) is not None

    @staticmethod
    def is_dunder_method(line: Line):
        dunder_template = r"^def\s+__[\w]+?__\(.*?\):\s*"
        is_dunder = re.match(dunder_template, line.content) is not None
        return is_dunder

    def check(self, line: Line):
        new_line = LineFormatter.remove_leading_spaces(line)
        if not FunctionNameInSnakeCase.is_def_declaration(new_line):
            return IssueCodes.DUMMY

        if FunctionNameInSnakeCase.is_dunder_method(new_line):
            return IssueCodes.DUMMY

        def_name_snake_case = r"^def\s_*([a-z0-9]+_*)+\(.*\):\s*"
        if re.match(def_name_snake_case, new_line.content) is None:
            return IssueCodes.FUNCTION_NAME_IN_SNAKE_CASE
        return IssueCodes.DUMMY


def set_up_logger():
    LOGGING_CONFIG = "logging.conf"
    logging.config.fileConfig(LOGGING_CONFIG)
    logging.debug(f"Logging was initialized from {LOGGING_CONFIG}")


def init_rules() -> typing.List[PEP8Rule]:
    return [
        MaxLineLength(),
        IndentationMultipleOfFour(),
        UnnecessarySemicolonAfterStatement(),
        AtLeastTwoSpacesBeforeInlineComment(),
        TodoFound(),
        MoreThanTwoBlankLinesPrecedingCodeLine(),
        TooManySpacesAfterClass(),
        TooManySpacesAfterDef(),
        ClassNameInCamelCase(),
        FunctionNameInSnakeCase(),
    ]


def open_python_file(path_to_file):
    try:
        file = open(path_to_file)
        logging.debug(f"File {path_to_file} opened")
    except FileNotFoundError:
        print("Can not open the file")
        exit(1)
    else:
        return file


def check_file(file, rules, lines):
    for pos, content in enumerate(file, start=1):
        content = content.rstrip()  # remove '\n'
        logging.info(f"Processing line at pos {pos} with content: {content}")
        line = Line(pos, content)
        errors = []
        for rule in rules:
            if isinstance(rule, MoreThanTwoBlankLinesPrecedingCodeLine):
                if content == "":
                    continue
                rule.set_prev_lines(lines)

            logging.debug(f"Trying to apply rule {rule}.")
            error = rule.check(line)

            if error != IssueCodes.DUMMY:
                logging.debug(f"{error.description} was added to errors list.")
                errors.append(error)

        errors.sort(key=lambda e: e.code)
        for error in errors:
            print(f"{file.name}: Line {pos}: {error.code} {error.description}")

        lines.append(line)
    logging.info("Lines processed.")
    file.close()


def scan_python_file(path):
    files = []
    if os.path.isfile(path):
        files.append(path)
    elif os.path.isdir(path):
        logging.debug("Scanning directories...")
        files.extend([
            os.path.join(dirpath, file)
            for dirpath, _, files in os.walk(path)
            for file in files
            if file.endswith(".py")
        ])
    files.sort()
    return files


def main():
    # set_up_logger()
    logging.debug(sys.argv)
    path = sys.argv[1]
    files = scan_python_file(path)
    logging.info(f"Found {len(files)} files: {files}")
    rules = init_rules()
    for file in files:
        file = open_python_file(file)
        processed_lines = []
        check_file(file, rules, processed_lines)


main()
