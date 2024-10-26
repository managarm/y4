import os
import pytest
import subprocess
import sys
import yaml

cases = [
    "map.y4.yml",
    "reduce.y4.yml",
]


@pytest.mark.parametrize("path", cases)
def test_y4(path):
    args = [sys.executable, "-m", "y4", os.path.join("tests", path)]
    result = subprocess.run(args, stdout=subprocess.PIPE)
    assert result.returncode == 0

    yml = yaml.load(result.stdout, Loader=yaml.SafeLoader)
    assert yml["result"] == yml["expected"]
