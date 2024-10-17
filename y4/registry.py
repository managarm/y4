from . import context

_builtin_registry = {}


def get_builtin_modules():
    return _builtin_registry


class BuiltinRule(context.Rule):
    def __init__(self, func):
        self.normalize = func


# Function decorator that registers a builtin.
def builtin(*, tag):
    def decorate(func):
        prefix, suffix = tag.split("::")

        module = _builtin_registry.get(prefix)
        if module is None:
            module = context.Namespace()
            _builtin_registry[prefix] = module

        rule = BuiltinRule(func)
        module._bindings[suffix] = rule

        return func

    return decorate
