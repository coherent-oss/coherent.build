import sys

if sys.version_info >= (3, 12):
    import importlib.resources
else:

    class importlib:
        import importlib_resources as resources
