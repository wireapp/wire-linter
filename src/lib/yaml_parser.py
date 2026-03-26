"""Minimal YAML parser for Wire config files.

Handles nested mappings, quoted/unquoted strings, booleans, nulls, integers,
floats, comments, blank lines, list items ('- value' / '- key: value'), inline
empty sequences ([]), and block scalars ('|' literal, '>' folded). Stripped
down, not a full YAML implementation.
"""

from __future__ import annotations

import re
from typing import Any


def _strip_inline_comment(value: str) -> str:
    """Strip inline comments from a YAML value.

    Looks for ' #' (space then hash) outside any quoted region. Respects both
    « and ' quotes so they're treated as literal chars inside the other kind.

    Args:
        value: The part after the colon in a YAML line.

    Returns:
        Value with inline comment removed, trailing whitespace stripped.
    """
    if not value:
        return value

    # '#' at the start means the whole thing is a comment
    if value.startswith('#'):
        return ''

    # Track quote state separately so "it's" doesn't break things
    in_double_quotes: bool = False
    in_single_quotes: bool = False

    prev_was_escape: bool = False

    for i, char in enumerate(value):
        # Backslash inside double quotes escapes the next character
        if in_double_quotes and prev_was_escape:
            prev_was_escape = False
            continue

        if in_double_quotes and char == '\\':
            prev_was_escape = True
            continue

        prev_was_escape = False

        if char == '"' and not in_single_quotes:
            in_double_quotes = not in_double_quotes
            continue

        if char == "'" and not in_double_quotes:
            in_single_quotes = not in_single_quotes
            continue

        # Found ' #' outside quotes, truncate here
        if not in_double_quotes and not in_single_quotes and char == '#' and i > 0 and value[i - 1] == ' ':
            return value[:i - 1].rstrip()

    return value


# Numeric patterns
_INT_PATTERN: re.Pattern[str] = re.compile(r'^-?\d+$')
_FLOAT_PATTERN: re.Pattern[str] = re.compile(r'^-?\d+\.\d+$')

# Block scalar indicators: |, >, |-, >-, |+, >+, etc.
_BLOCK_SCALAR_PATTERN: re.Pattern[str] = re.compile(r'^[|>][0-9]?[-+]?$')

# Booleans (case-insensitive)
_TRUE_VALUES: frozenset[str] = frozenset({'true', 'yes'})
_FALSE_VALUES: frozenset[str] = frozenset({'false', 'no'})
_NULL_VALUES: frozenset[str] = frozenset({'null', '~'})


def _split_inline_items(text: str) -> list[str]:
    """Split a comma-separated inline value.

    Respects quotes and nested brackets/braces so commas inside them aren't splits.

    Args:
        text: The inner content between [ ] or { } delimiters.

    Returns:
        List of non-empty stripped items.
    """
    items: list[str] = []
    current: list[str] = []
    depth: int = 0
    # Track quotes separately like in _strip_inline_comment
    in_double_quotes: bool = False
    in_single_quotes: bool = False

    prev_was_escape: bool = False

    for char in text:
        # Backslash inside double quotes escapes the next character
        if in_double_quotes and prev_was_escape:
            prev_was_escape = False
            current.append(char)
            continue

        if in_double_quotes and char == '\\':
            prev_was_escape = True
            current.append(char)
            continue

        prev_was_escape = False

        if char == '"' and not in_single_quotes:
            in_double_quotes = not in_double_quotes
            current.append(char)
        elif char == "'" and not in_double_quotes:
            in_single_quotes = not in_single_quotes
            current.append(char)
        elif in_double_quotes or in_single_quotes:
            current.append(char)
        elif char in ('[', '{'):
            depth += 1
            current.append(char)
        elif char in (']', '}'):
            depth -= 1
            current.append(char)
        elif char == ',' and depth == 0:
            # Found a top-level comma, flush the item
            item: str = ''.join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)

    # Don't forget the last item
    last: str = ''.join(current).strip()
    if last:
        items.append(last)

    return items


def _parse_inline_sequence(text: str) -> list[Any]:
    """Parse an inline YAML sequence like '[a, b, c]' or '[]'.

    Each element goes through _parse_value for type coercion.

    Args:
        text: The full sequence string with brackets.

    Returns:
        A Python list.
    """
    inner: str = text[1:-1].strip()
    if not inner:
        return []

    return [_parse_value(item) for item in _split_inline_items(inner)]


def _parse_inline_mapping(text: str) -> dict[str, Any]:
    """Parse an inline YAML mapping like '{key: val, k2: v2}' or '{}'.

    Args:
        text: The full mapping string with braces.

    Returns:
        A Python dict.
    """
    inner: str = text[1:-1].strip()
    if not inner:
        return {}

    result: dict[str, Any] = {}
    for item in _split_inline_items(inner):
        parts: list[str] = item.split(':', 1)
        if len(parts) == 2:
            raw_key: str = parts[0].strip()
            # Strip quotes from keys
            key: str = raw_key[1:-1] if raw_key.startswith('"') and raw_key.endswith('"') else raw_key
            result[key] = _parse_value(parts[1].strip())

    return result


def _parse_value(raw_value: str) -> Any:
    r"""Convert a YAML value to the right Python type.

    Order matters: quoted strings first, so « 123 » stays a string not an int.

    Rules: quoted string, list, dict, null, bool, int, float, or plain string.

    Args:
        raw_value: The value after comment stripping.

    Returns:
        The converted value.
    """
    stripped: str = raw_value.strip()

    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]

    if len(stripped) >= 2 and stripped.startswith("'") and stripped.endswith("'"):
        return stripped[1:-1]

    if stripped.startswith('[') and stripped.endswith(']'):
        return _parse_inline_sequence(stripped)

    if stripped.startswith('{') and stripped.endswith('}'):
        return _parse_inline_mapping(stripped)

    lower: str = stripped.lower()
    if lower in _NULL_VALUES:
        return None

    if lower in _TRUE_VALUES:
        return True

    if lower in _FALSE_VALUES:
        return False

    if _INT_PATTERN.match(stripped):
        return int(stripped)

    if _FLOAT_PATTERN.match(stripped):
        return float(stripped)

    return stripped


def _store_block_scalar(
    block_indicator: str,
    block_lines: list[str],
    target: dict[str, Any],
    key: str,
) -> None:
    """Finalize a block scalar and write it.

    Supports three chomping modes based on the indicator suffix:
      clip (default, no suffix): strip leading/trailing blank lines
      strip ('-'): same as clip (no trailing newline)
      keep  ('+'): strip leading blanks but preserve all trailing newlines

    Args:
        block_indicator: Full indicator string, e.g. '|', '>-', '|+', '>2+'.
        block_lines:     Indented block content.
        target:          Dict to store in.
        key:             Key to store under.
    """
    # Determine style (literal vs folded) and chomping mode
    style: str = block_indicator[0]
    chomping: str = 'clip'
    if block_indicator.endswith('-'):
        chomping = 'strip'
    elif block_indicator.endswith('+'):
        chomping = 'keep'

    # Always strip leading blank lines
    lines: list[str] = block_lines[:]
    while lines and not lines[0]:
        lines.pop(0)

    if chomping == 'keep':
        # Count trailing blank lines before we touch them
        trailing_count: int = 0
        idx: int = len(lines) - 1
        while idx >= 0 and not lines[idx]:
            trailing_count += 1
            idx -= 1

        # Remove trailing blanks so the join is clean, then re-add as newlines
        while lines and not lines[-1]:
            lines.pop()

        if style == '|':
            content: str = '\n'.join(lines)
        else:
            content = ' '.join(line for line in lines if line)

        # Preserve all trailing newlines: one per blank line plus the final newline
        content += '\n' * (trailing_count + 1)
    else:
        # clip / strip: drop trailing blank lines, no trailing newline
        while lines and not lines[-1]:
            lines.pop()

        if style == '|':
            content = '\n'.join(lines)
        else:
            content = ' '.join(line for line in lines if line)

    target[key] = content


def parse_yaml(text: str) -> dict[str, Any]:
    """Parse YAML into a nested dict.

    Handles: indentation-based nesting, quoted/unquoted strings, booleans,
    numbers, comments, blank lines, list items (- value), inline sequences/mappings,
    and block scalars (| and >).

    Args:
        text: The YAML content.

    Returns:
        A nested dict.

    Raises:
        ValueError: If YAML is malformed (bad indentation, etc.)
    """
    result: dict[str, Any] = {}

    # Stack: (indent, container, parent_container, parent_key)
    # Lets us retroactively convert empty dicts to lists when we hit a list item.
    stack: list[tuple[int, Any, Any, Any]] = [(0, result, None, None)]

    # Block scalar state
    in_block: bool = False
    block_type: str = ''
    block_key_indent: int = 0
    block_content_indent: int = -1
    block_lines: list[str] = []
    block_target: dict[str, Any] = {}
    block_key: str = ''

    all_lines: list[str] = text.splitlines()
    line_count: int = len(all_lines)
    line_index: int = 0

    while line_index < line_count:
        line_number: int = line_index + 1
        line: str = all_lines[line_index]

        # Block scalar content
        if in_block:
            stripped_for_blank: str = line.rstrip()

            if not stripped_for_blank:
                block_lines.append('')
                line_index += 1
                continue

            line_indent: int = len(line) - len(line.lstrip())

            if line_indent <= block_key_indent:
                # Dedented back: block ends, process this line normally
                _store_block_scalar(block_type, block_lines, block_target, block_key)
                in_block = False
                block_lines = []
                block_content_indent = -1
            else:
                # Still in block, accumulate
                if block_content_indent == -1:
                    block_content_indent = line_indent
                block_lines.append(line[block_content_indent:].rstrip())
                line_index += 1
                continue

        # Regular line processing
        stripped_line: str = line.rstrip()

        if not stripped_line:
            line_index += 1
            continue

        if stripped_line.lstrip().startswith('#'):
            line_index += 1
            continue

        indent_level: int = len(line) - len(line.lstrip())

        # Pop deeper levels off the stack
        while len(stack) > 1 and stack[-1][0] > indent_level:
            stack.pop()

        line_content: str = line.lstrip()

        is_list_item: bool = line_content.startswith('- ') or line_content == '-'

        # If we hit a non-list line at the same indent as a list, pop the list
        if (
            not is_list_item
            and len(stack) > 1
            and stack[-1][0] == indent_level
            and isinstance(stack[-1][1], list)
        ):
            stack.pop()

        # List item handling

        if is_list_item:
            top_indent, top_container, top_parent, top_parent_key = stack[-1]

            if top_indent == indent_level and isinstance(top_container, list):
                active_list: list[Any] = top_container

            elif (
                top_indent == indent_level
                and isinstance(top_container, dict)
                and not top_container
            ):
                # Empty dict pushed by 'key:' line, convert to list
                active_list = []
                if top_parent is not None:
                    top_parent[top_parent_key] = active_list
                stack[-1] = (indent_level, active_list, top_parent, top_parent_key)

            elif (
                top_indent == indent_level
                and isinstance(top_container, dict)
                and top_container
            ):
                # Find the last key's empty dict and convert it to a list
                last_key: str | None = None
                for k in top_container:
                    last_key = k
                if (
                    last_key is not None
                    and isinstance(top_container[last_key], dict)
                    and not top_container[last_key]
                ):
                    active_list = []
                    top_container[last_key] = active_list
                    stack.append((indent_level, active_list, top_container, last_key))
                else:
                    raise ValueError(
                        f"Unexpected list item at line {line_number}: "
                        f"can't start a list here"
                    )

            else:
                raise ValueError(
                    f"Unexpected list item at line {line_number}: "
                    f"can't start a list here"
                )

            item_content: str = line_content[2:].strip() if len(line_content) > 1 else ''

            if not item_content or item_content.startswith('#'):
                # Bare '-' or '- #comment', content follows on indented lines
                item_dict: dict[str, Any] = {}
                active_list.append(item_dict)
                stack.append((indent_level + 2, item_dict, active_list, len(active_list) - 1))

            elif ':' not in item_content or item_content.startswith('"'):
                # Scalar list item: '- value' or '- "quoted: value"'
                active_list.append(_parse_value(_strip_inline_comment(item_content)))

            else:
                # Mapping list item: '- key: value' or '- key:'
                item_parts: list[str] = item_content.split(':', 1)
                item_key: str = item_parts[0].strip()
                item_raw_value: str = item_parts[1].strip() if len(item_parts) > 1 else ''

                item_dict = {}
                active_list.append(item_dict)

                if not item_raw_value or item_raw_value.startswith('#'):
                    # '- key:' on its own line
                    nested_dict: dict[str, Any] = {}
                    item_dict[item_key] = nested_dict
                    stack.append((indent_level + 2, item_dict, active_list, len(active_list) - 1))
                    stack.append((indent_level + 4, nested_dict, item_dict, item_key))
                else:
                    # '- key: value' all on one line
                    cleaned: str = _strip_inline_comment(item_raw_value)
                    item_dict[item_key] = _parse_value(cleaned)
                    stack.append((indent_level + 2, item_dict, active_list, len(active_list) - 1))

        # Regular key: value

        else:
            if stack[-1][0] != indent_level:
                raise ValueError(
                    f"Inconsistent indentation at line {line_number}"
                )

            top_container: Any = stack[-1][1]

            if not isinstance(top_container, dict):
                raise ValueError(
                    f"Expected mapping at line {line_number}: "
                    f"found a list instead"
                )

            parent_dict: dict[str, Any] = top_container

            parts: list[str] = line_content.split(':', 1)

            if len(parts) < 2:
                raise ValueError(
                    f"Expected key: value at line {line_number}: {stripped_line}"
                )

            key: str = parts[0].strip()
            raw_value: str = parts[1].strip()

            if not raw_value:
                # Empty value, push nested mapping
                new_dict: dict[str, Any] = {}
                parent_dict[key] = new_dict
                stack.append((indent_level + 2, new_dict, parent_dict, key))

            elif _BLOCK_SCALAR_PATTERN.match(raw_value):
                # Block scalar (|, >, |-, >+, etc.), collect content on next lines
                in_block = True
                block_type = raw_value
                block_key_indent = indent_level
                block_content_indent = -1
                block_lines = []
                block_target = parent_dict
                block_key = key
                parent_dict[key] = ''

            else:
                # Scalar value, parse type
                cleaned_value: str = _strip_inline_comment(raw_value)
                parsed_value: Any = _parse_value(cleaned_value)
                parent_dict[key] = parsed_value

        line_index += 1

    # Finalize any leftover block scalar
    if in_block:
        _store_block_scalar(block_type, block_lines, block_target, block_key)

    return result


def get_nested(data: dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    """Get a value from a nested dict using dotted path.

    Like «admin_host.ip» or «databases.cassandra».

    Args:
        data: The nested dictionary.
        dotted_path: Path like «admin_host.ip».
        default: Value to return if not found.

    Returns:
        The value at the path, or default.
    """
    if not dotted_path:
        return default

    current: Any = data
    for key in dotted_path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]

    return current
