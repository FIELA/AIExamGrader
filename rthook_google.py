# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.

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
