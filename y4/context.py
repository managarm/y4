from copy import copy
import enum
import functools
import os
import sys
import yaml

from . import util
from . import registry


class Binding:
    pass


class Namespace(Binding):
    def __init__(self):
        self._bindings = {}

    def bind(self, tag, binding):
        assert tag not in self._bindings.keys()
        self._bindings[tag] = binding

    def lookup(self, tag):
        return self._bindings.get(tag)


class Rule(Binding):
    pass


class Environment:
    def __init__(self):
        self._mods = {}
        self._search_paths = []
        self._opts = {}

    def set_option(self, k, v):
        self._opts[k] = v

    def get_option(self, k):
        return self._opts.get(k)

    def add_search_path(self, path):
        self._search_paths.append(path)

    def locate_module_loaders(self, name):
        module = registry.get_builtin_modules().get(name)
        if module:
            yield functools.partial(self._load_builtin, module)

        for search_path in self._search_paths:
            path = os.path.join(search_path, f"{name}.yaml")
            if os.path.exists(path):
                yield functools.partial(self._load_from_path, path)

    def get_or_load_module(self, name):
        loaded = self._mods.get(name)
        if loaded:
            return loaded

        loaders = list(self.locate_module_loaders(name))
        if not loaders:
            raise util.Y4Error(f"Module {name} does not exist")
        if len(loaders) > 1:
            raise util.Y4Error(f"Module {name} is ambiguous")

        module = loaders[0]()
        self._mods[name] = module
        return module

    def _load_builtin(self, module):
        return module

    def _load_from_path(self, path):
        with open(path) as f:
            root = yaml.compose(f, Loader=util.YamlLoader)

        ctx = Context(env=self)
        module = Namespace()

        d = ctx.assemble_dict_keys(root)
        for tag, binding in process_bindings(ctx, d):
            module.bind(tag, binding)

        return module


class Context:
    def __init__(self, parent=None, *, env=None):
        if parent is None:
            assert env is not None

            self.env = env
            self.enable_tracing = False
            self._bindings = {}
        else:
            assert env is None

            self.env = parent.env
            self.enable_tracing = parent.enable_tracing
            self._bindings = copy(parent._bindings)

    # Binds a tag to a Rule or Namespace.
    def bind(self, tag, binding):
        if not isinstance(binding, Binding):
            raise RuntimeError("Bindings need to inherit from Binding class")
        if tag in self._bindings:
            raise util.Y4Error(f"Duplicate tag definition: {tag} is already defined")
        self._bindings[tag] = binding

    # Resolves a qualified tag or returns None on error.
    def resolve(self, tag):
        components = tag.split("::")
        if not components:
            return None
        first, *tail = components

        # Look up the first component.
        current = self._bindings.get(first)
        if current is None:
            return None

        # Look up nested components.
        for follow in tail:
            current = current.lookup(follow)
            if current is None:
                return None

        assert current is not None
        return current

    def normalize(self, node, *, tag=None):
        self.trace("normalize", node.tag, node)

        if tag is None:
            tag = node.tag

        if tag.startswith("!"):
            suffix = tag[1:]

            tf = self.resolve(suffix)
            if tf is not None:
                return tf.normalize(self, node)
            else:
                raise util.Y4Error(f"Undefined binding !{suffix}")
        elif tag == "tag:yaml.org,2002:seq":
            if not isinstance(node, yaml.SequenceNode):
                raise util.Y4Error(f"Invalid node kind for {tag}")
            value = []
            for item in node.value:
                tf = self.normalize(item)
                if tf.tag == "tag:y4.managarm.org:splice":
                    value.extend(tf.value)
                else:
                    value.append(tf)
            return yaml.SequenceNode(tag, value)
        elif tag == "tag:yaml.org,2002:map":
            if not isinstance(node, yaml.MappingNode):
                raise util.Y4Error(f"Invalid node kind for {tag}")
            value = []
            for k, v in node.value:
                tf = (self.normalize(k), self.normalize(v))
                value.append(tf)
            return yaml.MappingNode(tag, value)
        elif tag in [
            "tag:yaml.org,2002:str",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:bool",
        ]:
            if not isinstance(node, yaml.ScalarNode):
                raise util.Y4Error(f"Invalid node kind for {tag}")
            return yaml.ScalarNode(tag, node.value)
        elif tag in [
            "tag:y4.managarm.org:function",
            "tag:y4.managarm.org:context",
        ]:
            if not isinstance(node, util.InternalNode):
                raise util.Y4Error(f"Invalid node kind for {tag}")
            return util.InternalNode(tag, node.value)
        else:
            raise util.Y4Error(f"Unexpected YAML tag {node.tag}")

    def evaluate(self, node, *, tag=None):
        self.trace("evaluate", node)
        tf = self.normalize(node, tag=tag)
        return util.construct(tf)

    def assemble_dict_keys(self, node):
        d = {}
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                d[self.evaluate(k)] = v
        else:
            raise util.Y4Error(f"Cannot assemble dict from {type(node)}")
        return d

    def trace(self, event, *args):
        if not self.enable_tracing:
            return
        print(event, *args, file=sys.stderr)


class ConstRule(Rule):
    def __init__(self, const):
        self.const = const

    def normalize(self, ctx, node):
        return self.const


class CustomRule(Rule):
    def __init__(self, fn, *, normalize):
        self._fn = fn
        self._normalize = normalize

    def normalize(self, ctx, node):
        # Custom rules normalize the node as if it had the default tag,
        # i.e., the tag that the non-specific tag ! would resolve to.
        if isinstance(node, yaml.SequenceNode):
            base_tag = "tag:yaml.org,2002:seq"
        elif isinstance(node, yaml.MappingNode):
            base_tag = "tag:yaml.org,2002:map"
        elif isinstance(node, yaml.ScalarNode):
            # Scalars are normalized as strings.
            base_tag = "tag:yaml.org,2002:str"
        else:
            raise util.Y4Error(f"Cannot apply custom rule to node kind {type(node)}")

        if self._normalize:
            tf = ctx.normalize(node, tag=base_tag)
            return self._fn.apply(tf)
        else:
            ctx_node = util.InternalNode("tag:y4.managarm.org:context", ctx)
            tf = util.copy_node(node, tag=base_tag)
            return self._fn.apply(ctx_node, tf)


def process_bindings(ctx, d):
    if "import" in d:
        # TODO: Validate that d["import"] has the right (kind, tag).
        for item in d["import"].value:
            tag = util.get_local(item.tag)
            module = ctx.env.get_or_load_module(tag)
            ctx.bind(tag, module)
    if "const" in d:
        # TODO: Validate that d["const"] has the right (kind, tag).
        for k, v in d["const"].value:
            tag = util.get_local(k.tag)
            tf = ctx.normalize(v)
            yield (tag, ConstRule(tf))
    if "rule" in d:
        # TODO: Validate that d["rule"] has the right (kind, tag).
        for k, v in d["rule"].value:
            tag = util.get_local(k.tag)
            tf = ctx.normalize(v)
            if tf.tag == "tag:y4.managarm.org:function":
                util.validate_node(tf, "custom rule", kind=util.InternalNode)
                fn = tf.value
                normalize = True
            elif tf.tag == util.YAML_MAP_TAG:
                util.validate_node(tf, "custom rule", kind=yaml.MappingNode)
                tf_d = ctx.assemble_dict_keys(tf)
                fn = tf_d["fn"].value
                normalize = True
                if "normalize" in tf_d:
                    normalize = ctx.evaluate(tf_d["normalize"])
            else:
                raise util.Y4Error(f"Cannot define custom rule using {tf.tag}")
            yield (tag, CustomRule(fn, normalize=normalize))
