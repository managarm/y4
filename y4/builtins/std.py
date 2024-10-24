import yaml

from .. import context
from .. import util
from ..registry import builtin


class Y4Function:
    def __init__(self, inner_ctx, expr):
        self._inner_ctx = inner_ctx
        self._expr = expr

    def apply(self, node):
        # Note that the arguments are not normalized before application.
        # They will usually be normalized by the caller.

        # We compute the function using the inner context with !arg introduced.
        apply_ctx = context.Context(self._inner_ctx)
        apply_ctx.bind("arg", context.ConstRule(node))
        return apply_ctx.normalize(self._expr)


@builtin(tag="std::let")
def let(ctx, node):
    d = ctx.assemble_dict_keys(node)
    # TODO: We should not assume that d["const"] is a MappingNode.
    nested_ctx = context.Context(ctx)
    for tag, rule in context.process_bindings(ctx, d):
        nested_ctx.bind(tag, rule)
    res = nested_ctx.normalize(d["in"])
    return res


@builtin(tag="std::fn")
def fn(ctx, node):
    # Note that the inner context of the function is a snapshot of the current context.
    # It is not equal to the current context, i.e., subsequently introduced rules
    # will not affect the inner context.
    inner_ctx = context.Context(ctx)

    d = ctx.assemble_dict_keys(node)
    expr = d["return"]
    return util.InternalNode(
        "tag:y4.managarm.org:function", Y4Function(inner_ctx, expr)
    )


@builtin(tag="std::opt")
def opt(ctx, node):
    k = ctx.evaluate(node, tag="tag:yaml.org,2002:str")
    return util.represent(ctx.env.get_option(k))


@builtin(tag="std::ite")
def ite(ctx, node):
    d = ctx.assemble_dict_keys(node)
    cond = ctx.evaluate(d["if"])
    if cond:
        return ctx.normalize(d["then"])
    else:
        return ctx.normalize(d["else"])


@builtin(tag="std::get")
def get(ctx, node):
    if isinstance(node, yaml.SequenceNode):
        raw_obj = node.value[0]
        raw_key = node.value[1]
    elif isinstance(node, yaml.MappingNode):
        d = ctx.assemble_dict_keys(node)
        raw_obj = d["object"]
        raw_key = d["key"]
    else:
        raise util.Y4Error("Invalid node kind for !std::get")
    obj = ctx.normalize(raw_obj)
    key = ctx.evaluate(raw_key)
    obj_dict = ctx.assemble_dict_keys(obj)
    return obj_dict[key]


@builtin(tag="std::contains")
def contains(ctx, node):
    obj = ctx.evaluate(node, tag="tag:yaml.org,2002:map")
    return util.represent(obj["item"] in obj["list"])


@builtin(tag="std::apply")
def apply(ctx, node):
    tf = ctx.normalize(node, tag="tag:yaml.org,2002:map")
    d = ctx.assemble_dict_keys(tf)
    func = d["fn"].value
    return func.apply(d["arg"])


@builtin(tag="std::splice_if")
def splice_if(ctx, node):
    value = []
    for raw_item in node.value:
        item = ctx.normalize(raw_item)
        d = ctx.assemble_dict_keys(item)
        if ctx.evaluate(d["if"]):
            value.append(d["item"])

    return yaml.SequenceNode("tag:y4.managarm.org:splice", value)


@builtin(tag="std::join")
def join(ctx, node):
    parts = [ctx.evaluate(item) for item in node.value]

    return util.represent("".join(parts))
