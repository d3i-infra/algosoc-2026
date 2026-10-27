"""Tests for ``scripts/generate_port_config.py`` (loaded by path; it is not a package)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "generate_port_config.py"
_spec = importlib.util.spec_from_file_location("generate_port_config", _SCRIPT)
assert _spec is not None and _spec.loader is not None
generate_port_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_port_config)


def _docstring(inputs_json: str) -> str:
    return (
        "Synthetic extractor.\n\n"
        "    Table config::\n\n"
        "        {\n"
        '            "id": "t",\n'
        f'            "inputs": {inputs_json}\n'
        "        }\n"
    )


@pytest.mark.parametrize("bad", ['"x"', "[1]", '[""]'])
def test_generator_rejects_bad_inputs(bad):
    with pytest.raises(ValueError, match="synthetic_fn.*inputs"):
        generate_port_config._parse_table_config_block("synthetic_fn", _docstring(bad))


def test_generator_accepts_valid_inputs():
    entry = generate_port_config._parse_table_config_block(
        "synthetic_fn", _docstring('["a.json", "re:x"]')
    )
    assert entry["inputs"] == ["a.json", "re:x"]


def test_generator_rejects_a_pattern_input_that_does_not_compile():
    with pytest.raises(ValueError, match=r"synthetic_fn: 'inputs' entry 're:\(' "):
        generate_port_config._parse_table_config_block("synthetic_fn", _docstring('["a.json", "re:("]'))
