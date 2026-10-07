"""Small shared readers and identity helpers for Phase A contracts."""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def load_document(path: Path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        value = json.loads(text, object_pairs_hook=_unique_json, parse_constant=_invalid_constant)
    else:
        try:
            value = yaml.load(text, Loader=UniqueLoader)
        except yaml.YAMLError as error:
            raise ValueError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def load_contract(relative_path: str) -> dict:
    return load_document(ROOT / relative_path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def host_fingerprint() -> str:
    return canonical_digest({"node": platform.node(), "system": platform.system(), "machine": platform.machine()})


def schema_errors(value: dict, schema: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"invalid schema: {error.message}") from error
    def check_refs(node):
        if isinstance(node, dict):
            if "$ref" in node and not node["$ref"].startswith("#"):
                raise ValueError("Phase A schemas cannot fetch external references")
            for child in node.values():
                check_refs(child)
        elif isinstance(node, list):
            for child in node:
                check_refs(child)
    check_refs(schema)
    validator = Draft202012Validator(schema)
    return [f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
            for error in sorted(validator.iter_errors(value), key=lambda e: str(list(e.absolute_path)))]


def contained_path(base: Path, relative: str) -> Path:
    base = Path(base).resolve()
    result = (base / relative).resolve()
    if not result.is_relative_to(base):
        raise ValueError(f"path leaves project root: {relative}")
    return result


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
