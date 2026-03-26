"""Unit tests for the minimal YAML parser module.

Covers basic key-value parsing, nested mappings, multi-level nesting,
comment handling, value type coercion, malformed input detection,
inline comment stripping, the get_nested() helper, and the sample config.
"""

from __future__ import annotations

# External
from typing import Any

# Ours
from src.lib.yaml_parser import (
    parse_yaml, get_nested, _strip_inline_comment, _parse_value,
    _split_inline_items, _parse_inline_sequence, _parse_inline_mapping,
)
from src.lib.test_config_sample import SAMPLE_CONFIG_YAML


# ---------------------------------------------------------------------------
# parse_yaml basic parsing
# ---------------------------------------------------------------------------

def test_parse_yaml_simple() -> None:
    """Basic key-value parsing with string, int, and bool types."""
    # Mix all three scalar types in one YAML snippet
    yaml_text: str = "name: hello\nport: 8080\nenabled: true"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['name'] == 'hello', f"Expected 'hello', got {result['name']!r}"
    assert result['port'] == 8080, f"Expected 8080, got {result['port']!r}"
    assert result['enabled'] is True, f"Expected True, got {result['enabled']!r}"


def test_parse_yaml_empty_input() -> None:
    """Empty string should return an empty dict."""
    result: dict[str, Any] = parse_yaml("")

    # Empty document should produce empty mapping, not None or raise
    assert result == {}, f"Expected empty dict, got {result!r}"


def test_parse_yaml_only_comments_and_blanks() -> None:
    """Only comments and blanks should return empty dict."""
    # Exercise all skip conditions: comments, blanks, and whitespace-only lines
    yaml_text: str = "# just a comment\n\n# another comment\n   \n"
    result: dict[str, Any] = parse_yaml(yaml_text)
    assert result == {}, f"Expected empty dict, got {result!r}"


# ---------------------------------------------------------------------------
# parse_yaml nesting
# ---------------------------------------------------------------------------

def test_parse_yaml_nested() -> None:
    """2-space indentation creates nested dicts."""
    yaml_text: str = "parent:\n  child_a: value_a\n  child_b: 42"
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Parent maps to a nested dict, not a string
    assert isinstance(result['parent'], dict), "Parent should be a dict"
    assert result['parent']['child_a'] == 'value_a', \
        f"Expected 'value_a', got {result['parent']['child_a']!r}"
    assert result['parent']['child_b'] == 42, \
        f"Expected 42, got {result['parent']['child_b']!r}"


def test_parse_yaml_multi_level_nesting() -> None:
    """3+ levels of nesting parse correctly."""
    yaml_text: str = (
        "level1:\n"
        "  level2:\n"
        "    level3_a: deep_value\n"
        "    level3_b: 99\n"
        "  sibling: hello\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Deep paths resolve correctly
    assert result['level1']['level2']['level3_a'] == 'deep_value'
    assert result['level1']['level2']['level3_b'] == 99

    # Sibling at level 2 works after popping from level 3
    assert result['level1']['sibling'] == 'hello'


def test_parse_yaml_return_to_root_after_nesting() -> None:
    """Parser returns to root level after nested block."""
    yaml_text: str = (
        "section:\n"
        "  inner: value\n"
        "top_level: root_value\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Parser pops indent stack when seeing shallower line
    assert result['section']['inner'] == 'value'
    assert result['top_level'] == 'root_value'


def test_parse_yaml_multiple_top_level_sections() -> None:
    """Multiple independent nested sections at root level."""
    yaml_text: str = (
        "first:\n"
        "  a: 1\n"
        "second:\n"
        "  b: 2\n"
        "third:\n"
        "  c: 3\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Each top-level section stays independent
    assert result['first']['a'] == 1
    assert result['second']['b'] == 2
    assert result['third']['c'] == 3


# ---------------------------------------------------------------------------
# parse_yaml comments
# ---------------------------------------------------------------------------

def test_parse_yaml_comments() -> None:
    """Comment lines skipped, inline comments stripped."""
    yaml_text: str = (
        "# this is a comment\n"
        "\n"
        "name: hello # greeting\n"
        'desc: "has # inside"'
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Only 2 keys: comments and blanks get skipped
    assert len(result) == 2, f"Expected 2 keys, got {len(result)}"

    # Inline comment stripped from value
    assert result['name'] == 'hello', f"Expected 'hello', got {result['name']!r}"

    # Hash inside quotes stays as literal data
    assert result['desc'] == 'has # inside', \
        f"Expected 'has # inside', got {result['desc']!r}"


# ---------------------------------------------------------------------------
# parse_yaml value types
# ---------------------------------------------------------------------------

def test_parse_yaml_value_types() -> None:
    """All value type conversions: quoted string, bool, int, float."""
    yaml_text: str = (
        'name: "quoted value"\n'
        "host: unquoted\n"
        "enabled: true\n"
        "disabled: false\n"
        "active: yes\n"
        "inactive: no\n"
        "port: 8080\n"
        "offset: -5\n"
        "ratio: 3.14\n"
        "temp: -0.5"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Quoted string strips quotes, stays str
    assert result['name'] == 'quoted value', f"Got {result['name']!r}"
    assert isinstance(result['name'], str), "Quoted value should be str"

    # Unquoted non-keywords stay str
    assert result['host'] == 'unquoted', f"Got {result['host']!r}"

    # All bool variants (true/false/yes/no) become Python bool
    assert result['enabled'] is True, f"Got {result['enabled']!r}"
    assert isinstance(result['enabled'], bool), "Should be bool"
    assert result['disabled'] is False, f"Got {result['disabled']!r}"
    assert result['active'] is True, f"Got {result['active']!r}"
    assert result['inactive'] is False, f"Got {result['inactive']!r}"

    # Integers become int, not str
    assert result['port'] == 8080, f"Got {result['port']!r}"
    assert isinstance(result['port'], int), "Should be int"

    # Negative integers
    assert result['offset'] == -5, f"Got {result['offset']!r}"
    assert isinstance(result['offset'], int), "Should be int"

    # Floats become float, not str
    assert result['ratio'] == 3.14, f"Got {result['ratio']!r}"
    assert isinstance(result['ratio'], float), "Should be float"

    # Negative floats
    assert result['temp'] == -0.5, f"Got {result['temp']!r}"
    assert isinstance(result['temp'], float), "Should be float"


def test_parse_yaml_colon_in_value() -> None:
    """Values with colons (like URLs) parse correctly."""
    yaml_text: str = 'url: "http://example.com:8080/path"'
    result: dict[str, Any] = parse_yaml(yaml_text)

    # Quoted URL with embedded colons stays intact
    assert result['url'] == 'http://example.com:8080/path'


# ---------------------------------------------------------------------------
# parse_yaml malformed input
# ---------------------------------------------------------------------------

def test_parse_yaml_malformed() -> None:
    """ValueError raised for various malformed inputs."""
    # Case 1: 3-space indent rejected (parser uses 2-space increments)
    try:
        parse_yaml("   key: val")
        assert False, "Should have raised ValueError for 3-space indent"
    except ValueError as e:
        assert 'line 1' in str(e), f"Error should mention line 1: {e}"
        assert 'multiple of 2' in str(e), f"Error should mention multiple of 2: {e}"

    # Case 2: No colon means not a key-value pair
    try:
        parse_yaml("no_colon_here")
        assert False, "Should have raised ValueError for missing colon"
    except ValueError as e:
        assert 'key: value' in str(e), f"Error should mention key: value format: {e}"

    # Case 3: Indent jump of >1 level is invalid (no parent for child)
    try:
        parse_yaml("parent:\n      deep: val")
        assert False, "Should have raised ValueError for indent jump"
    except ValueError as e:
        assert 'line 2' in str(e) or 'indentation' in str(e).lower(), \
            f"Error should mention line or indentation: {e}"


# ---------------------------------------------------------------------------
# _strip_inline_comment direct tests
# ---------------------------------------------------------------------------

def test_strip_inline_comment_empty() -> None:
    """Empty string returned as-is."""
    assert _strip_inline_comment("") == ""


def test_strip_inline_comment_no_comment() -> None:
    """Value with no comment returned unchanged."""
    assert _strip_inline_comment("hello world") == "hello world"


def test_strip_inline_comment_with_comment() -> None:
    """Inline comment stripped."""
    # Space before '#' marks comment; everything after removed
    assert _strip_inline_comment("value # comment") == "value"


def test_strip_inline_comment_hash_in_quotes() -> None:
    """Hash inside quotes preserved."""
    result: str = _strip_inline_comment('"has # inside"')

    # Quoted hash is literal, not comment delimiter
    assert result == '"has # inside"', f"Got {result!r}"


def test_strip_inline_comment_hash_without_space() -> None:
    """Hash without space not treated as comment."""
    # '#' without space is not a comment delimiter per spec
    result: str = _strip_inline_comment("color:#fff")
    assert result == "color:#fff", f"Got {result!r}"


# ---------------------------------------------------------------------------
# _parse_value direct tests
# ---------------------------------------------------------------------------

def test_parse_value_quoted_string() -> None:
    """Double-quoted strings have quotes removed."""
    # Outer quotes are YAML syntax, not part of value
    assert _parse_value('"hello"') == "hello"


def test_parse_value_boolean_case_insensitive() -> None:
    """Boolean detection is case-insensitive."""
    # YAML supports True/true/TRUE and Yes/yes/YES as truthy
    assert _parse_value("True") is True
    assert _parse_value("TRUE") is True
    assert _parse_value("False") is False
    assert _parse_value("FALSE") is False
    assert _parse_value("Yes") is True
    assert _parse_value("YES") is True
    assert _parse_value("No") is False
    assert _parse_value("NO") is False


def test_parse_value_integer() -> None:
    """Integer parsing including zero and negative."""
    # Zero parses as int, not bool False
    assert _parse_value("0") == 0
    assert isinstance(_parse_value("0"), int)
    assert _parse_value("42") == 42
    assert _parse_value("-10") == -10


def test_parse_value_float() -> None:
    """Float parsing."""
    # Decimal point distinguishes floats from ints
    assert _parse_value("1.5") == 1.5
    assert isinstance(_parse_value("1.5"), float)
    assert _parse_value("-2.7") == -2.7


def test_parse_value_plain_string() -> None:
    """Unrecognized values stay as plain strings."""
    # Anything not matching bool/int/float/quoted patterns stays str
    assert _parse_value("hello") == "hello"
    assert isinstance(_parse_value("hello"), str)


# ---------------------------------------------------------------------------
# get_nested
# ---------------------------------------------------------------------------

def test_get_nested() -> None:
    """Dotted-path traversal with various edge cases."""
    data: dict[str, Any] = {'a': {'b': 2}, 'x': 1}

    # Simple single-key lookup
    assert get_nested(data, 'x') == 1, "Simple key lookup should work"

    # Dotted path traverses nesting
    assert get_nested(data, 'a.b') == 2, "Dotted path should traverse nesting"

    # Missing key returns default (None)
    assert get_nested(data, 'missing') is None, "Missing key should return None"

    # Missing intermediate key returns None, not KeyError
    assert get_nested(data, 'x.y.z') is None, \
        "Missing intermediate key should return None"

    # Custom default overrides None
    assert get_nested(data, 'missing', 'default') == 'default', \
        "Custom default should be returned for missing key"

    # Empty path returns default
    assert get_nested(data, '') is None, "Empty path should return None"


def test_get_nested_deep_path() -> None:
    """get_nested works with 3+ level dotted paths."""
    data: dict[str, Any] = {'a': {'b': {'c': 'deep'}}}

    # Three-segment path exercises full descent
    assert get_nested(data, 'a.b.c') == 'deep'


# ---------------------------------------------------------------------------
# parse_yaml list support
# ---------------------------------------------------------------------------

def test_parse_yaml_scalar_list() -> None:
    """Simple scalar list under a key parses to Python list."""
    yaml_text: str = "items:\n  - alpha\n  - beta\n  - gamma\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['items'] == ['alpha', 'beta', 'gamma'], \
        f"Expected ['alpha', 'beta', 'gamma'], got {result['items']!r}"


def test_parse_yaml_scalar_list_typed_values() -> None:
    """List items type-coerced like regular values."""
    yaml_text: str = "values:\n  - 42\n  - true\n  - 3.14\n  - hello\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['values'] == [42, True, 3.14, 'hello'], \
        f"Unexpected values: {result['values']!r}"


def test_parse_yaml_mapping_list() -> None:
    """List of mapping items (- key: value) parses correctly."""
    yaml_text: str = (
        "nodes:\n"
        "  - host: server1\n"
        "    port: 9042\n"
        "  - host: server2\n"
        "    port: 9043\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert isinstance(result['nodes'], list), "nodes should be a list"
    assert len(result['nodes']) == 2, f"Expected 2 items, got {len(result['nodes'])}"
    assert result['nodes'][0] == {'host': 'server1', 'port': 9042}
    assert result['nodes'][1] == {'host': 'server2', 'port': 9043}


def test_parse_yaml_list_then_sibling_key() -> None:
    """List followed by sibling key at parent level."""
    yaml_text: str = (
        "section:\n"
        "  items:\n"
        "    - a\n"
        "    - b\n"
        "  count: 2\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['section']['items'] == ['a', 'b']
    assert result['section']['count'] == 2


def test_parse_yaml_multiple_lists() -> None:
    """Multiple independent lists in same document."""
    yaml_text: str = (
        "first:\n"
        "  - x\n"
        "  - y\n"
        "second:\n"
        "  - 1\n"
        "  - 2\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['first'] == ['x', 'y']
    assert result['second'] == [1, 2]


def test_parse_yaml_inline_empty_list() -> None:
    """Inline '[]' parses to empty Python list."""
    yaml_text: str = "domains: []\nother: value\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['domains'] == [], f"Expected [], got {result['domains']!r}"
    assert isinstance(result['domains'], list), "Should be a list, not a string"
    assert result['other'] == 'value'


def test_parse_yaml_inline_list_with_values() -> None:
    """Inline list with string, int, bool, and float elements."""
    yaml_text: str = "values: [hello, 42, true, 3.14]\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['values'] == ['hello', 42, True, 3.14], \
        f"Got {result['values']!r}"


def test_parse_yaml_inline_list_quoted_with_comma() -> None:
    """Quoted items in inline lists preserve embedded commas."""
    yaml_text: str = 'domains: ["a.com", "b.com"]\n'
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['domains'] == ['a.com', 'b.com'], \
        f"Got {result['domains']!r}"


def test_parse_yaml_inline_list_single_element() -> None:
    """Single-element inline list is a list, not a scalar."""
    yaml_text: str = "hosts: [10.0.0.1]\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['hosts'] == ['10.0.0.1'], f"Got {result['hosts']!r}"
    assert isinstance(result['hosts'], list)


def test_parse_yaml_inline_mapping_single_pair() -> None:
    """Inline mapping with one key-value pair."""
    yaml_text: str = "config: {status: disabled}\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['config'] == {'status': 'disabled'}, \
        f"Got {result['config']!r}"
    assert isinstance(result['config'], dict)


def test_parse_yaml_inline_mapping_multiple_pairs() -> None:
    """Inline mapping with multiple key-value pairs."""
    yaml_text: str = "endpoint: {host: server1, port: 9042}\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['endpoint'] == {'host': 'server1', 'port': 9042}, \
        f"Got {result['endpoint']!r}"


def test_parse_yaml_nested_inline_list_in_mapping() -> None:
    """Inline list nested inside an inline mapping."""
    yaml_text: str = "rule: {domains: [a.com, b.com], enabled: true}\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['rule']['domains'] == ['a.com', 'b.com']
    assert result['rule']['enabled'] is True


def test_split_inline_items_basic() -> None:
    """_split_inline_items splits on commas correctly."""
    assert _split_inline_items('a, b, c') == ['a', 'b', 'c']


def test_split_inline_items_respects_quotes() -> None:
    """_split_inline_items doesn't split on commas inside quotes."""
    assert _split_inline_items('"a, b", c') == ['"a, b"', 'c']


def test_split_inline_items_respects_nested_brackets() -> None:
    """_split_inline_items doesn't split on commas inside nested brackets."""
    assert _split_inline_items('[a, b], c') == ['[a, b]', 'c']


def test_parse_inline_sequence_empty() -> None:
    """_parse_inline_sequence handles '[]'."""
    assert _parse_inline_sequence('[]') == []


def test_parse_inline_sequence_typed() -> None:
    """_parse_inline_sequence applies type coercion to each element."""
    assert _parse_inline_sequence('[1, true, hello]') == [1, True, 'hello']


def test_parse_inline_mapping_empty() -> None:
    """_parse_inline_mapping handles '{}'."""
    assert _parse_inline_mapping('{}') == {}


def test_parse_inline_mapping_typed_values() -> None:
    """_parse_inline_mapping applies type coercion to values."""
    result: dict[str, Any] = _parse_inline_mapping('{port: 9042, enabled: true}')
    assert result == {'port': 9042, 'enabled': True}


def test_parse_yaml_inline_empty_mapping() -> None:
    """Inline '{}' parses to empty Python dict."""
    yaml_text: str = "config: {}\nname: test\n"
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['config'] == {}, f"Expected {{}}, got {result['config']!r}"
    assert isinstance(result['config'], dict), "Should be a dict, not a string"


# ---------------------------------------------------------------------------
# parse_yaml block scalars
# ---------------------------------------------------------------------------

def test_parse_yaml_literal_block_scalar() -> None:
    """'|' block scalar preserves newlines as multi-line string."""
    yaml_text: str = (
        "key: |\n"
        "  line one\n"
        "  line two\n"
        "other: value\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['key'] == 'line one\nline two', \
        f"Expected literal block content, got {result['key']!r}"
    assert result['other'] == 'value', "Sibling key after block scalar must parse"


def test_parse_yaml_folded_block_scalar() -> None:
    """'>' block scalar folds newlines to spaces."""
    yaml_text: str = (
        "key: >\n"
        "  line one\n"
        "  line two\n"
        "other: value\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['key'] == 'line one line two', \
        f"Expected folded block content, got {result['key']!r}"
    assert result['other'] == 'value'


def test_parse_yaml_block_scalar_strip_indicator() -> None:
    """'|-' (strip chomping) block scalar handled without crashing."""
    yaml_text: str = (
        "cert: |-\n"
        "  -----BEGIN CERTIFICATE-----\n"
        "  MIIB...\n"
        "  -----END CERTIFICATE-----\n"
        "name: test\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert isinstance(result['cert'], str), "Block scalar value must be a string"
    assert '-----BEGIN CERTIFICATE-----' in result['cert']
    assert result['name'] == 'test'


def test_parse_yaml_block_scalar_at_end_of_document() -> None:
    """Block scalar at end of file (no trailing dedent) is finalized."""
    yaml_text: str = (
        "description: |\n"
        "  first line\n"
        "  second line\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['description'] == 'first line\nsecond line', \
        f"Got {result['description']!r}"


def test_parse_yaml_block_scalar_nested() -> None:
    """Block scalar works inside a nested mapping."""
    yaml_text: str = (
        "parent:\n"
        "  script: |\n"
        "    echo hello\n"
        "    echo world\n"
        "  timeout: 30\n"
    )
    result: dict[str, Any] = parse_yaml(yaml_text)

    assert result['parent']['script'] == 'echo hello\necho world', \
        f"Got {result['parent']['script']!r}"
    assert result['parent']['timeout'] == 30


# ---------------------------------------------------------------------------
# Sample config integration
# ---------------------------------------------------------------------------

def test_sample_config_parses_successfully() -> None:
    """Sample config YAML parses without error."""
    result: dict[str, Any] = parse_yaml(SAMPLE_CONFIG_YAML)

    # Spot-check values from major sections to confirm nothing was silently dropped
    assert get_nested(result, 'admin_host.ip') == '10.0.0.1'
    assert get_nested(result, 'admin_host.ssh_port') == 22
    assert get_nested(result, 'cluster.domain') == 'wire.example.com'
    assert get_nested(result, 'databases.cassandra') == '10.0.1.1'
    assert get_nested(result, 'options.check_kubernetes') is True
    assert get_nested(result, 'options.check_network') is False
    assert get_nested(result, 'options.check_wire_services') is True
    assert get_nested(result, 'options.output_format') == 'jsonl'
    assert get_nested(result, 'timeout') == 60
    assert get_nested(result, 'kubernetes_context') == 'prod-cluster'
