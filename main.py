import logging
import logging.config
import os.path
import sys
import typing
from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from typing import List

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
    DUMMY_ISSUE = IssueCode("-1", "Error dummy")  # dummy error instead of None
    MAX_LENGTH_ISSUE = IssueCode("S001", "Too long")
    INDENTATION_MULTIPLE_FOUR_ISSUE = IssueCode("S002", "Indentation is not a multiple of four")
    UNNECESSARY_SEMICOLON_ISSUE = IssueCode("S003",
                                            "Unnecessary semicolon")
    AT_LEAST_2_SPACES_BEFORE_INLINE_COMMENT_ISSUE = IssueCode("S004",
                                                              "At least two spaces required before inline comments")
    TODO_FOUND_ISSUE = IssueCode("S005", "TODO found")
    MORE_TWO_BLANK_LINES_PRECEDING_CODE_LINE_ISSUE = IssueCode("S006",
                                                               "More than two blank lines used before this line")


class PEP8Rule(ABC):
    @abstractmethod
    def check(self, line: Line):
        pass


class MaxLineLength(PEP8Rule):
    _PEP8_MAX_LINE_LENGTH = 79

    def check(self, line: Line) -> IssueCode:
        if len(line.content) > self._PEP8_MAX_LINE_LENGTH:
            return IssueCodes.MAX_LENGTH_ISSUE
        return IssueCodes.DUMMY_ISSUE


class IndentationMultipleOfFour(PEP8Rule):
    def check(self, line: Line) -> IssueCode:
        line_len = len(line.content)
        leading_spaces_cnt = len(line.content.lstrip())
        if (line_len - leading_spaces_cnt) % 4 != 0:
            return IssueCodes.INDENTATION_MULTIPLE_FOUR_ISSUE
        return IssueCodes.DUMMY_ISSUE


class UnnecessarySemicolonAfterStatement(PEP8Rule):
    # note that semicolons are acceptable in comments
    _SEMICOLON_SEP = ";"

    def check(self, line: Line):
        new_line = LineFormatter.remove_comment(line)
        new_line = LineFormatter.remove_finishing_spaces(new_line)
        if len(new_line.content) > 0 and new_line.content[-1] == self._SEMICOLON_SEP:
            return IssueCodes.UNNECESSARY_SEMICOLON_ISSUE
        return IssueCodes.DUMMY_ISSUE


class AtLeastTwoSpacesBeforeInlineComment(PEP8Rule):
    def check(self, line: Line):
        new_line = LineFormatter.remove_leading_spaces(line)
        if new_line.content.startswith(COMMENT_SEP):
            return IssueCodes.DUMMY_ISSUE

        try:
            comment_sep_pos = new_line.content.index(COMMENT_SEP)
        except ValueError:
            return IssueCodes.DUMMY_ISSUE

        idx, spaces_cnt = comment_sep_pos - 1, 0
        while idx >= 0 and line.content[idx].isspace():
            spaces_cnt += 1
            idx -= 1

        if spaces_cnt < 2:
            return IssueCodes.AT_LEAST_2_SPACES_BEFORE_INLINE_COMMENT_ISSUE
        return IssueCodes.DUMMY_ISSUE


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
            return IssueCodes.TODO_FOUND_ISSUE
        return IssueCodes.DUMMY_ISSUE


class MoreThanTwoBlankLinesPrecedingCodeLine(PEP8Rule):
    def __init__(self):
        self.prev_lines = None

    def set_prev_lines(self, prev_lines: List[Line]):
        self.prev_lines = prev_lines

    def check(self, line: Line):
        if len(self.prev_lines) <= 2:
            return IssueCodes.DUMMY_ISSUE
        if self.prev_lines[-3].content == self.prev_lines[-2].content == self.prev_lines[-1].content == "":
            return IssueCodes.MORE_TWO_BLANK_LINES_PRECEDING_CODE_LINE_ISSUE
        return IssueCodes.DUMMY_ISSUE


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


def check_file(file, rules):
    lines = []
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

            if error != IssueCodes.DUMMY_ISSUE:
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
        check_file(file, rules)


main()
