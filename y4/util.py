import yaml

YAML_SEQ_TAG = "tag:yaml.org,2002:seq"
YAML_MAP_TAG = "tag:yaml.org,2002:map"
YAML_STR_TAG = "tag:yaml.org,2002:str"

YamlLoader = yaml.SafeLoader


class InternalNode(yaml.Node):
    id = "internal"

    def __init__(self, tag, value):
        self.tag = tag
        self.value = value


class Y4Error(Exception):
    pass


def validate_node(node, desc, *, kind=None, tag=None):
    if kind is not None and not isinstance(node, kind):
        raise Y4Error(
            f"Invalid node kind {type(node).id} for {desc}, expected {kind.id}"
        )
    if tag is not None and node.tag != tag:
        raise Y4Error(f"Invalid node tag {node.tag} for {desc}, expected {tag}")


def get_local(tag):
    if not tag.startswith("!"):
        raise Y4Error(f"unexpected tag {tag}")
    return tag[1:]


def get_marker_tag(node):
    if not isinstance(node, yaml.ScalarNode):
        raise Y4Error("Marker nodes must be scalar")
    if node.value:
        raise Y4Error("Marker nodes must be empty")
    return node.tag


def copy_node(node, *, tag=None):
    if tag is None:
        tag = node.tag

    if isinstance(node, yaml.SequenceNode):
        return yaml.SequenceNode(tag, node.value)
    elif isinstance(node, yaml.MappingNode):
        return yaml.MappingNode(tag, node.value)
    elif isinstance(node, yaml.ScalarNode):
        return yaml.ScalarNode(tag, node.value)
    else:
        raise Y4Error(f"Unknown kind when transmuting tag")


def construct(node, *, tag=None):
    if tag is None:
        tag = node.tag

    if tag == "tag:yaml.org,2002:seq":
        if not isinstance(node, yaml.SequenceNode):
            raise Y4Error(f"Expected sequence node for {tag}")
        return [construct(item) for item in node.value]
    elif tag == "tag:yaml.org,2002:map":
        if not isinstance(node, yaml.MappingNode):
            raise Y4Error(f"Expected mapping node for {tag}")
        return {construct(k): construct(v) for k, v in node.value}
    elif tag == "tag:yaml.org,2002:str":
        if not isinstance(node, yaml.ScalarNode):
            raise Y4Error(f"Expected scalar node for {tag}")
        return node.value
    elif tag == "tag:yaml.org,2002:bool":
        if not isinstance(node, yaml.ScalarNode):
            raise Y4Error(f"Expected scalar node for {tag}")
        if node.value == "true":
            return True
        elif node.value == "false":
            return False
        else:
            raise Y4Error(f"Unexpected value {node.value} for boolean")
    elif tag == "tag:yaml.org,2002:int":
        if not isinstance(node, yaml.ScalarNode):
            raise Y4Error(f"Expected scalar node for {tag}")
        return int(node.value)
    else:
        raise Y4Error(f"Cannot construct value from tag {tag}")


def represent(data):
    if isinstance(data, dict):
        value = []
        for k, v in data.items():
            rep = (represent(k), represent(v))
            value.append(rep)
        return yaml.MappingNode("tag:yaml.org,2002:map", value)
    elif isinstance(data, list):
        value = []
        for item in data:
            rep = represent(item)
            value.append(rep)
        return yaml.SequenceNode("tag:yaml.org,2002:seq", value)
    elif isinstance(data, str):
        return yaml.ScalarNode("tag:yaml.org,2002:str", data)
    elif isinstance(data, bool):
        if data is True:
            value = "true"
        elif data is False:
            value = "false"
        else:
            raise Y4Error(f"Neither true or false: {data}")
        return yaml.ScalarNode("tag:yaml.org,2002:bool", value)
    elif isinstance(data, int):
        return yaml.ScalarNode("tag:yaml.org,2002:int", str(data))
    else:
        raise Y4Error(f"Cannot represent value of type {type(data)}")
