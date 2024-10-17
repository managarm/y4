import jq

from .. import util
from ..registry import builtin


class JqFunction:
    def __init__(self, script):
        self.program = jq.compile(script)

    def apply(self, ctx, node):
        obj = ctx.evaluate(node, tag="tag:yaml.org,2002:map")
        results = self.program.input_value(obj).all()
        if not results:
            raise util.Y4Error("jq script returned no results")
        if len(results) > 1:
            raise util.Y4Error("jq script returned more than one result")
        return util.represent(results[0])


@builtin(tag="jq::fn")
def fn(ctx, node):
    script = node.value
    return util.InternalNode("tag:y4.managarm.org:function", JqFunction(script))
