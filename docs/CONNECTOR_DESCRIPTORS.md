# Connector Descriptor Registry

Issue #249 moves connector operational metadata into validated
`connectors/<key>/descriptor.yaml` files.

## Why

The descriptor is the machine-readable contract for:
- source identity and authority,
- retrieval modes,
- base URL,
- exact allowed hosts,
- explicitly permitted POST paths,
- refresh rate,
- concurrency/rate policy,
- disappearance confirmation threshold,
- adapter version,
- Python adapter import path.

## Security

The loader:
- uses PyYAML SafeLoader with duplicate-key rejection,
- rejects unknown fields via Pydantic,
- limits descriptors to 64 KiB,
- requires exact lowercase hostnames (no wildcards, schemes, paths or ports),
- requires base_url host to be allowlisted,
- validates POST paths as absolute path-only values,
- restricts import_path to the connector's own
  `dotacni_majak_<adapter_key>` package.

Registry loading itself does not import connector Python modules.

## Runtime drift check

`ConnectorRegistry.load_adapter_class(key)` imports the configured adapter,
verifies it is a `SourceAdapter`, then compares the runtime
`SourceDescriptor` with the YAML descriptor. Any mismatch fails closed.

## Migration

Reference descriptors are provided first for:
- EU Funding & Tenders,
- NSA,
- DotaceEU,
- Plzeňský kraj.

Other connector issues can add descriptors without changing the registry
contract.
