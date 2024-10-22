import argparse
import sys
import yaml

from . import builtins
from . import context
from . import util
from . import registry

parser = argparse.ArgumentParser(prog="y4")
parser.add_argument("input")
parser.add_argument(
    "-p",
    "--path",
    action="append",
    default=[],
    help="add PATH to the module search path",
)
parser.add_argument(
    "--opt",
    nargs=2,
    action="append",
    default=[],
    metavar=("KEY", "VALUE"),
    help="pass the (KEY, VALUE) pair as an option",
)
parser.add_argument(
    "--trace",
    required=False,
    action="store_true",
    default=False,
    help="enable tracing to stderr",
)


def main():
    args = parser.parse_args()

    env = context.Environment()
    for k, v in args.opt:
        env.set_option(k, v)
    for path in args.path:
        env.add_search_path(path)

    ctx = context.Context(env=env)
    if args.trace:
        ctx.enable_tracing = True

    with open(args.input) as f:
        roots = yaml.compose_all(f, Loader=util.YamlLoader)
        for root in roots:
            if root.tag == "tag:y4.managarm.org:preamble":
                d = ctx.assemble_dict_keys(root)
                for tag, binding in context.process_bindings(ctx, d):
                    ctx.bind(tag, binding)
            else:
                out = ctx.evaluate(root)
                sys.stdout.write(yaml.dump(out, sort_keys=False, explicit_start=True))


if __name__ == "__main__":
    main()
