import sys
import types


def SimpleNamespaceShim(mapping_or_iterable=(), /, **kwargs):
    return types.SimpleNamespace(**dict(mapping_or_iterable), **kwargs)


SimpleNamespacePos = (
    types.SimpleNamespace if sys.version_info > (3, 13) else SimpleNamespaceShim
)
