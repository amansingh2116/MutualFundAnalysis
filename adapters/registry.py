"""
Adapter registry — central access point for all data source adapters.
"""
from .amfi_adapter import AMFIAdapter
from .captnemo_adapter import CaptnemoAdapter
from .mstarpy_adapter import MstarpyAdapter
from .benchmark_adapter import BenchmarkAdapter

ADAPTERS = {
    'amfi': AMFIAdapter,
    'captnemo': CaptnemoAdapter,
    'mstarpy': MstarpyAdapter,
    'benchmark': BenchmarkAdapter,
}

def get_adapter(name: str):
    """Factory function to get an instantiated adapter by name."""
    adapter_cls = ADAPTERS.get(name)
    if not adapter_cls:
        raise ValueError(f"Unknown adapter: {name}")
    return adapter_cls()
