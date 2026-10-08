# Contracts directory

Live contracts are YAML files placed directly in this directory
(`contracts/*.yaml`). The engine loads only direct files, in sorted
order.

`contracts/examples/` holds documented examples. Those files are never
loaded automatically. Copy an example here to try it as a live policy.

Validate any contract before use:

```bash
cd backend
arc validate ../contracts/examples/interactive-session-relief.yaml
```

See [Contract Reference](../docs/contracts.md) for the complete schema,
operators, lifecycle semantics, actions, and permission limitations.
