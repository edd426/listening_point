"""Decision code may not divide with /, write a float literal, or import math (BUILD section 2).

Every module of the package is held to it, not only the ones that decide, so nothing can drift in.
"""
import ast
import os
import unittest

import support  # noqa: F401  (puts the repo root on sys.path)
import shorekit

PKG = os.path.dirname(os.path.abspath(shorekit.__file__))
BANNED_MODULES = {"math", "cmath", "decimal", "fractions", "statistics", "random", "time", "datetime", "numpy"}
BANNED_NAMES = {"float", "complex", "round"}


def problems(src, name):
    out = []
    for node in ast.walk(ast.parse(src, name)):
        where = "%s:%d" % (name, getattr(node, "lineno", 0))
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.Div):
            out.append(where + " uses /")
        elif isinstance(node, ast.Constant) and type(node.value) in (float, complex):
            out.append(where + " has a float literal")
        elif isinstance(node, ast.Import):
            out += [where + " imports " + a.name for a in node.names if a.name.split(".")[0] in BANNED_MODULES]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in BANNED_MODULES:
            out.append(where + " imports from " + node.module)
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            out.append(where + " names " + node.id)
        elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow) and isinstance(node.right, ast.UnaryOp)
              and isinstance(node.right.op, ast.USub)):
            out.append(where + " raises to a negative power")
    return out


class TestIntegerOnly(unittest.TestCase):
    def test_modules(self):
        names = sorted(f for f in os.listdir(PKG) if f.endswith(".py"))
        for must in ("manifest.py", "rules.py", "geometry.py", "ledger.py", "compose.py", "font.py", "png.py",
                     "reference.py", "strictjson.py", "importer.py", "cli.py", "build.py"):
            self.assertIn(must, names)
        found = []
        for n in names:
            with open(os.path.join(PKG, n), encoding="utf-8") as f:
                found += problems(f.read(), n)
        self.assertEqual(found, [])

    def test_the_ban_bites(self):
        bad = "import math\nfrom fractions import Fraction\nx = 1 / 2\ny = 0.5\nx /= 3\nz = float(1)\nw = 2 ** -1\nq = 1e3\n"
        found = problems(bad, "bad.py")
        self.assertEqual(len(found), 8, found)
        self.assertEqual(problems("x = 7 // 2\ny = 7 >> 1\nz = 3 ** 2\n", "ok.py"), [])


if __name__ == "__main__":
    unittest.main()
