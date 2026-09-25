from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .adapter import SourceAdapter
from .models import SourceDescriptor


class ConnectorDescriptorError(ValueError):
    pass


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConnectorDescriptorError(
                f"duplicate YAML key is not allowed: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class ConnectorDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(alias="schemaVersion")
    adapter_key: str
    import_path: str
    source: SourceDescriptor

    @field_validator("schema_version")
    @classmethod
    def _schema_version_must_be_v1(cls, value: int) -> int:
        if value != 1:
            raise ValueError("schemaVersion must be 1")
        return value

    @field_validator("adapter_key")
    @classmethod
    def _adapter_key_is_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError("adapter_key must be a lowercase kebab-case slug")
        return value

    @field_validator("import_path")
    @classmethod
    def _import_path_shape(cls, value: str) -> str:
        if not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*",
            value,
        ):
            raise ValueError("import_path must be module.path:ClassName")
        return value

    @model_validator(mode="after")
    def _security_and_consistency(self) -> "ConnectorDescriptor":
        expected_package = "dotacni_majak_" + self.adapter_key.replace("-", "_")
        module_name, _ = self.import_path.split(":", 1)
        if not (
            module_name == expected_package
            or module_name.startswith(expected_package + ".")
        ):
            raise ValueError(
                "import_path must stay inside the connector package "
                f"{expected_package!r}"
            )

        hosts = self.source.allowed_hosts
        if not hosts:
            raise ValueError("allowed_hosts must not be empty")
        if len(hosts) != len(set(hosts)):
            raise ValueError("allowed_hosts must be unique")

        normalized_hosts: list[str] = []
        for host in hosts:
            normalized = host.rstrip(".").lower()
            if (
                host != normalized
                or "*" in host
                or "/" in host
                or ":" in host
                or not re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
                    host,
                )
            ):
                raise ValueError(
                    f"allowed_hosts contains non-canonical hostname: {host!r}"
                )
            normalized_hosts.append(normalized)

        base_host = self.source.base_url.host
        if base_host is None or base_host.rstrip(".").lower() not in normalized_hosts:
            raise ValueError("base_url host must be present in allowed_hosts")

        if not self.source.retrieval_modes:
            raise ValueError("retrieval_modes must not be empty")
        if len(self.source.retrieval_modes) != len(set(self.source.retrieval_modes)):
            raise ValueError("retrieval_modes must be unique")

        paths = self.source.allowed_post_paths
        if len(paths) != len(set(paths)):
            raise ValueError("allowed_post_paths must be unique")
        for path in paths:
            if (
                not path.startswith("/")
                or path.startswith("//")
                or "?" in path
                or "#" in path
                or "\\" in path
                or ".." in path.split("/")
            ):
                raise ValueError(
                    f"unsafe allowed_post_path: {path!r}"
                )

        if self.source.country_code is not None and not re.fullmatch(
            r"[A-Z]{2}",
            self.source.country_code,
        ):
            raise ValueError("country_code must be ISO-like uppercase alpha-2")

        return self


@dataclass(frozen=True, slots=True)
class ConnectorRegistration:
    directory: Path
    descriptor_path: Path
    descriptor: ConnectorDescriptor


class ConnectorRegistry:
    def __init__(self, registrations: list[ConnectorRegistration]) -> None:
        by_key: dict[str, ConnectorRegistration] = {}
        by_code: dict[str, ConnectorRegistration] = {}

        for registration in registrations:
            descriptor = registration.descriptor
            if descriptor.adapter_key in by_key:
                raise ConnectorDescriptorError(
                    f"duplicate adapter_key: {descriptor.adapter_key}"
                )
            if descriptor.source.code in by_code:
                raise ConnectorDescriptorError(
                    f"duplicate source code: {descriptor.source.code}"
                )
            by_key[descriptor.adapter_key] = registration
            by_code[descriptor.source.code] = registration

        self._by_key = by_key
        self._by_code = by_code

    @classmethod
    def from_connectors_root(cls, root: Path) -> "ConnectorRegistry":
        root = root.resolve()
        registrations: list[ConnectorRegistration] = []

        for descriptor_path in sorted(root.glob("*/descriptor.yaml")):
            directory = descriptor_path.parent
            descriptor = load_connector_descriptor(descriptor_path)
            if descriptor.adapter_key != directory.name:
                raise ConnectorDescriptorError(
                    f"{descriptor_path}: adapter_key {descriptor.adapter_key!r} "
                    f"must match connector directory {directory.name!r}"
                )
            registrations.append(
                ConnectorRegistration(
                    directory=directory,
                    descriptor_path=descriptor_path,
                    descriptor=descriptor,
                )
            )

        if not registrations:
            raise ConnectorDescriptorError(
                f"no connector descriptors found under {root}"
            )

        return cls(registrations)

    def registrations(self) -> tuple[ConnectorRegistration, ...]:
        return tuple(
            self._by_key[key]
            for key in sorted(self._by_key)
        )

    def by_adapter_key(self, adapter_key: str) -> ConnectorRegistration:
        try:
            return self._by_key[adapter_key]
        except KeyError as exc:
            raise ConnectorDescriptorError(
                f"unknown adapter_key: {adapter_key}"
            ) from exc

    def by_source_code(self, code: str) -> ConnectorRegistration:
        try:
            return self._by_code[code]
        except KeyError as exc:
            raise ConnectorDescriptorError(
                f"unknown source code: {code}"
            ) from exc

    def load_adapter_class(self, adapter_key: str) -> type[SourceAdapter]:
        registration = self.by_adapter_key(adapter_key)
        descriptor = registration.descriptor
        module_name, class_name = descriptor.import_path.split(":", 1)

        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ConnectorDescriptorError(
                f"cannot import connector module {module_name!r}"
            ) from exc

        try:
            value: Any = getattr(module, class_name)
        except AttributeError as exc:
            raise ConnectorDescriptorError(
                f"connector class {class_name!r} not found in {module_name!r}"
            ) from exc

        if not isinstance(value, type) or not issubclass(value, SourceAdapter):
            raise ConnectorDescriptorError(
                f"{descriptor.import_path!r} is not a SourceAdapter subclass"
            )

        runtime = value.descriptor.model_dump(mode="json")
        declared = descriptor.source.model_dump(mode="json")
        if runtime != declared:
            raise ConnectorDescriptorError(
                f"runtime SourceDescriptor drift for {adapter_key}: "
                f"yaml={declared!r} runtime={runtime!r}"
            )
        return value


def load_connector_descriptor(path: Path) -> ConnectorDescriptor:
    if path.name != "descriptor.yaml":
        raise ConnectorDescriptorError(
            f"descriptor filename must be descriptor.yaml: {path}"
        )
    payload = path.read_bytes()
    if len(payload) > 64 * 1024:
        raise ConnectorDescriptorError(
            f"descriptor is too large: {path}"
        )

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConnectorDescriptorError(
            f"descriptor must be UTF-8: {path}"
        ) from exc

    try:
        raw = yaml.load(text, Loader=_UniqueSafeLoader)
    except ConnectorDescriptorError:
        raise
    except yaml.YAMLError as exc:
        raise ConnectorDescriptorError(
            f"invalid YAML descriptor: {path}"
        ) from exc

    if not isinstance(raw, dict):
        raise ConnectorDescriptorError(
            f"descriptor root must be a mapping: {path}"
        )

    try:
        return ConnectorDescriptor.model_validate(raw)
    except ValidationError as exc:
        raise ConnectorDescriptorError(
            f"invalid connector descriptor {path}: {exc}"
        ) from exc
