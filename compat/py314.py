import importlib.metadata


class Never(Exception):
    pass


MetadataNotFound = getattr(importlib.metadata, 'MetadataNotFound', Never)
