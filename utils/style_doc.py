# coding=utf-8
# Copyright 2020 The HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Style utils for the .rst and the docstrings."""

import argparse
import os
import re
import warnings
from enum import Enum


# Special blocks where the inside should be formatted.
TEXTUAL_BLOCKS = ["note", "warning"]
# List of acceptable characters for titles and sections underline.
TITLE_SPECIAL_CHARS = """= - ` : ' " ~ ^ _ * + # < >""".split(" ")
# Special words for docstrings (s? means the s is optional)
DOC_SPECIAL_WORD = [
    "Args?",
    "Params?",
    "Parameters?",
    "Arguments?",
    "Examples?",
    "Usage",
    "Returns?",
    "Raises?",
    "Attributes?",
]

# Regexes
# Matches any declaration of textual block, like `.. note::`. (ignore case to avoid writing all versions in the list)
_re_textual_blocks = re.compile(r"^\s*\.\.\s+(" + "|".join(TEXTUAL_BLOCKS) + r")\s*::\s*$", re.IGNORECASE)
# Matches list introduction in rst.
_re_list = re.compile(r"^(\s*-\s+|\s*\*\s+|\s*\d+.\s+)")
# Matches the indent in a line.
_re_indent = re.compile(r"^(\s*)\S")
# Matches a table declaration in rst.
_re_table = re.compile(r"(\+-+)+\+\s*$")
# Matches a code block in rst `:: `.
_re_code_block = re.compile(r"^\s*::\s*$")
# Matches any block of the form `.. something::` or `.. something:: bla`.
_re_ignore = re.compile(r"^\s*\.\.\s+(\S+)\s*::\s*\S*\s*$")
# Matches comment introduction in rst.
_re_comment = re.compile(r"\s*\.\.\s*$")
# Matches the special tag to ignore some paragraphs.
_re_doc_ignore = re.compile(r"(\.\.|#)\s*docstyle-ignore")
# Matches the example introduction in docstrings.
_re_example = re.compile(r"::\s*$")
# Matches the parameters introduction in docstrings.
_re_arg_def = re.compile(r"^\s*(Args?|Parameters?|Params|Arguments?|Environment|Attributes?)\s*:\s*$")
# Matches the return introduction in docstrings.
_re_return = re.compile(r"^\s*(Returns?|Raises?|Note)\s*:\s*$")
# Matches any doc special word without an empty line before.
_re_any_doc_special_word = re.compile(r"[^\n]\n([ \t]*)(" + "|".join(DOC_SPECIAL_WORD) + r")(::?\s*)\n")


class SpecialBlock(Enum):
    NOT_SPECIAL = 0
    NO_STYLE = 1
    ARG_LIST = 2


def split_text_in_lines(text, max_len, prefix="", min_indent=None):
    """
    Split `text` in the biggest lines possible with the constraint of `max_len` using `prefix` on the first line and
    then indenting with the same length as `prefix`.
    """
    text = re.sub(r"\s+", " ", text)
    indent = " " * len(prefix)
    if min_indent is not None:
        if len(indent) < len(min_indent):
            indent = min_indent
        if len(prefix) < len(min_indent):
            prefix = " " * (len(min_indent) - len(prefix)) + prefix
    new_lines = []
    words = text.split(" ")
    current_line = f"{prefix}{words[0]}"
    for word in words[1:]:
        try_line = f"{current_line} {word}"
        if len(try_line) > max_len:
            new_lines.append(current_line)
            current_line = f"{indent}{word}"
        else:
            current_line = try_line
    new_lines.append(current_line)
    return "\n".join(new_lines)


def get_indent(line):
    """Get the indentation of `line`."""
    indent_search = _re_indent.search(line)
    return indent_search.groups()[0] if indent_search is not None else ""


class CodeStyler:
    """A generic class to style .rst files."""

    def is_no_style_block(self, line):
        """Whether or not `line` introduces a block where styling should be ignore"""
        if _re_code_block.search(line) is not None:
            return True
        if _re_textual_blocks.search(line) is not None:
            return False
        return _re_ignore.search(line) is not None

    def is_comment_or_textual_block(self, line):
        """Whether or not `line` introduces a block where styling should not be ignored (note, warnings...)"""
        if _re_comment.search(line):
            return True
        return _re_textual_blocks.search(line) is not None

    def is_special_block(self, line):
        """Whether or not `line` introduces a special block."""
        if self.is_no_style_block(line):
            self.in_block = SpecialBlock.NO_STYLE
            return True
        return False

    def init_in_block(self, text):
        """
        Returns the initial value for `self.in_block`.

        Useful for some docstrings beginning inside an argument declaration block (all models).
        """
        return SpecialBlock.NOT_SPECIAL

    def style_paragraph(self, paragraph, max_len, no_style=False, min_indent=None):
        """
        Style `paragraph` (a list of lines) by making sure no line goes over `max_len`, except if the `no_style` flag
        is passed.
        """
        if len(paragraph) == 0:
            return ""
        if no_style or self.in_block == SpecialBlock.NO_STYLE:
            return "\n".join(paragraph)
        if _re_list.search(paragraph[0]) is not None:
            # Great, we're in a list. So we need to split our paragraphs in smaller parts, one for each item.
            result = ""
            remainder = ""
            prefix = _re_list.search(paragraph[0]).groups()[0]
            prefix_indent = get_indent(paragraph[0])
            current_item = [paragraph[0][len(prefix) :]]
            for i, line in enumerate(paragraph[1:]):
                new_item_search = _re_list.search(line)
                indent = get_indent(line)
                if len(indent) < len(prefix_indent) or (len(indent) == len(prefix_indent) and new_item_search is None):
                    # There might not be an empty line after the list, formatting the remainder recursively.
                    remainder = "\n" + self.style_paragraph(
                        paragraph[i + 1 :], max_len, no_style=no_style, min_indent=min_indent
                    )
                    break
                elif new_item_search is not None:
                    text = " ".join([l.strip() for l in current_item])
                    result += split_text_in_lines(text, max_len, prefix, min_indent=min_indent) + "\n"
                    prefix = new_item_search.groups()[0]
                    prefix_indent = indent
                    current_item = [line[len(prefix) :]]
                else:
                    current_item.append(line)
            # Treat the last item
            text = " ".join([l.strip() for l in current_item])
            result += split_text_in_lines(text, max_len, prefix, min_indent=min_indent)
            # Add the potential remainder
            return result + remainder

        if len(paragraph) > 1 and self.is_comment_or_textual_block(paragraph[0]):
            # Comments/notes in rst should be restyled with indentation, ignoring the first line.
            indent = get_indent(paragraph[1])
            text = " ".join([l.strip() for l in paragraph[1:]])
            return paragraph[0] + "\n" + split_text_in_lines(text, max_len, indent, min_indent=min_indent)

        if self.in_block == SpecialBlock.ARG_LIST:
            # Arg lists are special: we need to ignore the lines that are at the first indentation level beneath the
            # Args/Parameters (parameter description), then we can style the indentation level beneath.
            result = ""
            # The args/parameters could be in that paragraph and should be ignored
            if _re_arg_def.search(paragraph[0]) is not None:
                if len(paragraph) == 1:
                    return paragraph[0]
                result += paragraph[0] + "\n"
                paragraph = paragraph[1:]

            if self.current_indent is None:
                self.current_indent = get_indent(paragraph[1])

            current_item = []
            for line in paragraph:
                if get_indent(line) == self.current_indent:
                    if len(current_item) > 0:
                        item_indent = get_indent(current_item[0])
                        text = " ".join([l.strip() for l in current_item])
                        result += split_text_in_lines(text, max_len, item_indent, min_indent=min_indent) + "\n"
                    result += line + "\n"
                    current_item = []
                else:
                    current_item.append(line)
            if len(current_item) > 0:
                item_indent = get_indent(current_item[0])
                text = " ".join([l.strip() for l in current_item])
                result += split_text_in_lines(text, max_len, item_indent, min_indent=min_indent) + "\n"
            return result[:-1]

        indent = get_indent(paragraph[0])
        text = " ".join([l.strip() for l in paragraph])
        return split_text_in_lines(text, max_len, indent, min_indent=min_indent)

    def style(self, text, max_len=119, min_indent=None):
        """Style `text` to `max_len`."""
        new_lines = []
        paragraph = []
        self.current_indent = ""
        # If one of those is True, the paragraph should not be touched (code samples, lists...)
        no_style = False
        no_style_next = False
        self.in_block = self.init_in_block(text)
        # If this is True, we force-break a paragraph, even if there is no new empty line.
        break_paragraph = False

        lines = text.split("\n")
        last_line = None
        for line in lines:
            # New paragraph
            line_is_empty = len(line.strip()) == 0
            list_begins = (
                _re_list.search(line) is not None
                and last_line is not None
                and len(get_indent(line)) > len(get_indent(last_line))
            )
            if line_is_empty or break_paragraph or list_begins:
                if len(paragraph) > 0:
                    if self.in_block != SpecialBlock.NOT_SPECIAL:
                        indent = get_indent(paragraph[0])
                        # Are we still in a no-style block?
                        if self.current_indent is None:
                            # If current_indent is None, we haven't begun the interior of the block so the answer is
                            # yes, unless we have an indent of 0 in which case the special block took one line only.
                            if len(indent) == 0:
                                self.in_block = SpecialBlock.NOT_SPECIAL
                            else:
                                self.current_indent = indent
                        elif not indent.startswith(self.current_indent):
                            # If not, we are leaving the block when we unindent.
                            self.in_block = SpecialBlock.NOT_SPECIAL

                    if self.is_special_block(paragraph[0]):
                        # Maybe we are starting a special block.
                        if len(paragraph) > 1:
                            # If we have the interior of the block in the paragraph, we grab the indent.
                            self.current_indent = get_indent(paragraph[1])
                        else:
                            # We will determine the indent with the next paragraph
                            self.current_indent = None
                    styled_paragraph = self.style_paragraph(
                        paragraph, max_len, no_style=no_style, min_indent=min_indent
                    )
                    new_lines.append(styled_paragraph + "\n")
                else:
                    new_lines.append("")

                paragraph = []
                no_style = no_style_next
                no_style_next = False
                last_line = None
                if (not break_paragraph and not list_begins) or line_is_empty:
                    break_paragraph = False
                    continue
                break_paragraph = False

            # Title and section lines should go to the max + add a new paragraph.
            if (
                len(set(line)) == 1
                and line[0] in TITLE_SPECIAL_CHARS
                and last_line is not None
                and len(line) >= len(last_line)
            ):
                line = line[0] * max_len
                break_paragraph = True
            # proper doc comment indicates the next paragraph should be no-style.
            if _re_doc_ignore.search(line) is not None:
                no_style_next = True
            # Table are in just one paragraph and should be no-style.
            if _re_table.search(line) is not None:
                no_style = True
            paragraph.append(line)
            last_line = line

        # Just have to treat the last paragraph. It could still be in a no-style block (or not)
        if len(paragraph) > 0:
            # Are we still in a special block
            # (if current_indent is None, we are but no need to set it since we are the end.)
            if self.in_block != SpecialBlock.NO_STYLE and self.current_indent is not None:
                indent = get_indent(paragraph[0])
                if not indent.startswith(self.current_indent):
                    self.in_block = SpecialBlock.NOT_SPECIAL
            _ = self.is_special_block(paragraph[0])
            new_lines.append(self.style_paragraph(paragraph, max_len, no_style=no_style, min_indent=min_indent) + "\n")
        return "\n".join(new_lines)


class DocstringStyler(CodeStyler):
    """Class to style docstrings that take the main method from `CodeStyler`."""

    def is_no_style_block(self, line):
        if _re_example.search(line) is not None:
            return True
        return _re_code_block.search(line) is not None
        # return super().is_no_style_block(line) is not None

    def is_comment_or_textual_block(self, line):
        if _re_return.search(line) is not None:
            self.in_block = SpecialBlock.NOT_SPECIAL
            return True
        return super().is_comment_or_textual_block(line)

    def is_special_block(self, line):
        if self.is_no_style_block(line):
            self.in_block = SpecialBlock.NO_STYLE
            return True
        if _re_arg_def.search(line) is not None:
            self.in_block = SpecialBlock.ARG_LIST
            return True
        return False

    def init_in_block(self, text):
        lines = text.split("\n")
        while len(lines) > 0 and len(lines[0]) == 0:
            lines = lines[1:]
        if len(lines) == 0:
            return SpecialBlock.NOT_SPECIAL
        if re.search(r":\s*$", lines[0]):
            indent = get_indent(lines[0])
            if (
                len(lines) == 1
                or len(get_indent(lines[1])) > len(indent)
                or (len(get_indent(lines[1])) == len(indent) and re.search(r":\s*$", lines[1]))
            ):
                self.current_indent = indent
                return SpecialBlock.ARG_LIST
        return SpecialBlock.NOT_SPECIAL


rst_styler = CodeStyler()
doc_styler = DocstringStyler()


def style_rst_file(doc_file, max_len=119, check_only=False):
    """ Style one rst file `doc_file` to `max_len`."""
    with open(doc_file, "r", encoding="utf-8") as f:
        doc = f.read()
    clean_doc = rst_styler.style(doc, max_len=max_len)

    diff = clean_doc != doc
    if not check_only and diff:
        print(f"Overwriting content of {doc_file}.")
        with open(doc_file, "w", encoding="utf-8") as f:
            f.write(clean_doc)

    return diff


def style_docstring(docstring, max_len=119):
    """Style `docstring` to `max_len`."""
    # One-line docstring that are not too long are left as is.
    if len(docstring) < max_len and "\n" not in docstring:
        return docstring

    # Grab the indent from the last line
    last_line = docstring.split("\n")[-1]
    # Is it empty except for the last triple-quotes (not-included in `docstring`)?
    indent_search = re.search(r"^(\s*)$", last_line)
    if indent_search is not None:
        indent = indent_search.groups()[0]
        if len(indent) > 0:
            docstring = docstring[: -len(indent)]
    # Or are the triple quotes next to text (we will fix that).
    else:
        indent_search = _re_indent.search(last_line)
        indent = indent_search.groups()[0] if indent_search is not None else ""

    # Add missing new lines before Args/Returns etc.
    docstring = _re_any_doc_special_word.sub(r"\n\n\1\2\3\n", docstring)
    # Style
    styled_doc = doc_styler.style(docstring, max_len=max_len, min_indent=indent)

    # Add new lines if necessary
    if not styled_doc.startswith("\n"):
        styled_doc = "\n" + styled_doc
    if not styled_doc.endswith("\n"):
        styled_doc += "\n"
    return styled_doc + indent


def style_file_docstrings(code_file, max_len=119, check_only=False):
    """Style all docstrings in `code_file` to `max_len`."""
    with open(code_file, "r", encoding="utf-8") as f:
        code = f.read()
    splits = code.split('"""')
    splits = [
        (s if i % 2 == 0 or _re_doc_ignore.search(splits[i - 1]) is not None else style_docstring(s, max_len=max_len))
        for i, s in enumerate(splits)
    ]
    clean_code = '"""'.join(splits)

    diff = clean_code != code
    if not check_only and diff:
        print(f"Overwriting content of {code_file}.")
        with open(code_file, "w", encoding="utf-8") as f:
            f.write(clean_code)

    return diff


def style_doc_files(*files, max_len=119, check_only=False):
    """
    Style all `files` to `max_len` and fixes mistakes if not `check_only`, otherwise raises an error if styling should
    be done.
    """
    changed = []
    for file in files:
        # Treat folders
        if os.path.isdir(file):
            files = [os.path.join(file, f) for f in os.listdir(file)]
            files = [f for f in files if os.path.isdir(f) or f.endswith(".rst") or f.endswith(".py")]
            changed += style_doc_files(*files, max_len=max_len, check_only=check_only)
        # Treat rst
        elif file.endswith(".rst"):
            if style_rst_file(file, max_len=max_len, check_only=check_only):
                changed.append(file)
        # Treat python files
        elif file.endswith(".py"):
            if style_file_docstrings(file, max_len=max_len, check_only=check_only):
                changed.append(file)
        else:
            warnings.warn(f"Ignoring {file} because it's not a py or an rst file or a folder.")
    return changed


def main(*files, max_len=119, check_only=False):
    changed = style_doc_files(*files, max_len=max_len, check_only=check_only)
    if check_only and len(changed) > 0:
        raise ValueError(f"{len(changed)} files should be restyled!")
    elif len(changed) > 0:
        print(f"Cleaned {len(changed)} files!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="The file(s) or folder(s) to restyle.")
    parser.add_argument("--max_len", type=int, help="The maximum length of lines.")
    parser.add_argument("--check_only", action="store_true", help="Whether to only check and not fix styling issues.")
    args = parser.parse_args()

    main(*args.files, max_len=args.max_len, check_only=args.check_only)
