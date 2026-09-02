import base64
import struct

from app.games.poe.pob.tree_url import decode_tree_url


def _url(data: bytes) -> str:
    return "https://www.pathofexile.com/passive-skill-tree/" + base64.urlsafe_b64encode(
        data
    ).decode().rstrip("=")


def test_version_4_layout():
    data = struct.pack(">IBBB", 4, 3, 1, 0) + struct.pack(">3H", 100, 200, 65535)
    t = decode_tree_url(_url(data))
    assert t is not None
    assert (t.version, t.class_id, t.ascendancy_id) == (4, 3, 1)
    assert t.node_ids == (100, 200, 65535)


def test_version_6_layout_with_masteries():
    data = struct.pack(">IBB", 6, 4, 1)
    data += bytes([2]) + struct.pack(">2H", 10, 20)  # nodes
    data += bytes([1]) + struct.pack(">H", 30)  # cluster nodes
    data += bytes([1]) + struct.pack(">2H", 999, 10)  # mastery pair (effect, node)
    t = decode_tree_url(_url(data))
    assert t is not None
    assert t.node_ids == (10, 20, 30)
    assert t.mastery_effects == {10: 999}


def test_unknown_is_none_not_a_guess():
    assert decode_tree_url("https://www.pathofexile.com/passive-skill-tree/") is None
    assert (
        decode_tree_url("https://www.pathofexile.com/passive-skill-tree/AAAAAg") is None
    )  # version 2
    assert decode_tree_url("not a url ///") is None


def test_legacy_export_url_decodes(code_legacy):
    from app.games.poe.pob import codec
    from app.games.poe.pob.xml_parser import parse_xml

    export = parse_xml(codec.decode(code_legacy))
    assert export.spec is not None and export.spec.url
    t = decode_tree_url(export.spec.url)
    assert t is not None and len(t.node_ids) > 100
