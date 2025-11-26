# Runtime hook for google namespace
import sys
import types

# Ensure google is registered as a module so submodules can be attached
if 'google' not in sys.modules:
    import importlib
    try:
        # Try to find it if it exists but wasn't imported
        importlib.import_module('google')
    except ImportError:
        # If it's completely missing (namespace issue), create a dummy package
        # This is a fallback to allow google.generativeai to attach itself
        m = types.ModuleType('google')
        m.__path__ = []
        sys.modules['google'] = m
