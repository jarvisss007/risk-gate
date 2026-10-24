"""The gate census: a static proof that every writer READS the halt file before it writes.

A rule that lives where the actor reads binds only while the actor remembers. The census reads each writer's source
(never runs it), finds the named function and checks that it calls the gate: `.admit(` or `.binding(` on a riskgate
Gate or HaltFile. A missing file, a missing function or a function with no gate call is reported MISSING, never
waved through. `riskgate census` exits non-zero when any writer is missing the call, so a test suite or a CI step
fails the moment a writer is added without the read.
"""
import ast
import os
import re

GATE_CALL = re.compile(r'\.(admit|binding)\(')
GATE_IMPORT = re.compile(r'\briskgate\b')


def function_source(path, name):
    try:
        src = open(path, encoding='utf-8').read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return None, None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return src, ast.get_source_segment(src, n) or ''
    return src, None


def check(path, function):
    src, seg = function_source(path, function)
    if src is None:
        return {'writer': path, 'function': function, 'present': False,
                'note': 'file missing' if not os.path.exists(path) else 'file does not parse'}
    if seg is None:
        return {'writer': path, 'function': function, 'present': False, 'note': f'no function {function}()'}
    ok = bool(GATE_CALL.search(seg)) and bool(GATE_IMPORT.search(src))
    return {'writer': path, 'function': function, 'present': ok,
            'note': 'gate call present' if ok else f'{function}() does not call the gate (.admit/.binding) through riskgate'}


def census(writers):
    """writers: [(path, function)] -> [check(...)]."""
    return [check(p, f) for p, f in writers]


def parse_spec(spec):
    """'path/to/writer.py:function' -> (path, function)."""
    if ':' not in spec:
        raise ValueError(f'{spec!r}: expected path.py:function')
    p, f = spec.rsplit(':', 1)
    return p, f
