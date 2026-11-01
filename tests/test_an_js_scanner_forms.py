"""AN-GATE-1 K-JS.6 scanner self-test (RULING 11:58Z, round 3, 2): the
nine forms the second review fed the scanner, and more. Each source
below references json (or pydantic's JSON parsers) in a way that is not
json.dumps or json.dump, so the scanner must report at least one hit.

# __an_js_scanner_forms_v1__
"""
from __future__ import annotations

import pytest

import test_an_js_inventory as I

FORMS = {
    "alias_assign": "import json\nparse = json.loads\nparse(b)\n",
    "map": "import json\nlist(map(json.loads, ls))\n",
    "decoder_attr": "import json\njson.decoder.JSONDecoder().decode(b)\n",
    "from_decoder": "from json.decoder import JSONDecoder\nJSONDecoder()\n",
    "getattr": "import json\ngetattr(json, 'loads')(b)\n",
    "importlib": "import importlib\nimportlib.import_module('json').loads(b)\n",
    "type_adapter": "from pydantic import TypeAdapter\nTypeAdapter(dict).validate_json(b)\n",
    "pydantic_core": "import pydantic_core\npydantic_core.from_json(b)\n",
    "default_arg": "import json\ndef f(fh, p=json.load):\n    return p(fh)\n",
    "import_as": "import json as _q\n_q.loads(b)\n",
    "from_import": "from json import loads as _l\n_l(b)\n",
    "dunder_import": "__import__('json').loads(b)\n",
    "module_value": "import json\nm = json\nm.loads(b)\n",
    "raw_decode": "x.raw_decode(b)\n",
    "model_validate_json": "M.model_validate_json(b)\n",
    "parse_raw": "M.parse_raw(b)\n",
}


@pytest.mark.parametrize("name", sorted(FORMS))
def test_scanner_sees_form(name):
    assert I.scan(FORMS[name], "x"), name


def test_scanner_allows_dumps():
    src = "import json\njson.dumps({})\njson.dump({}, fh)\n"
    assert I.scan(src, "x") == []
