import pytest

from app.domain.errors import InvalidBuildCode
from app.games.poe.pob import codec


def test_roundtrip():
    xml = b'<PathOfBuilding><Build level="1"/></PathOfBuilding>'
    assert codec.decode(codec.encode(xml)) == xml


def test_decode_tolerates_whitespace_and_standard_alphabet(code_modern):
    wrapped = "\n".join(code_modern[i : i + 76] for i in range(0, len(code_modern), 76))
    assert codec.decode(wrapped) == codec.decode(code_modern)
    assert codec.decode(code_modern.replace("-", "+").replace("_", "/")) == codec.decode(
        code_modern
    )


@pytest.mark.parametrize("bad", ["", "   ", "hello world", "eJ!!!", "aGVsbG8gd29ybGQ"])
def test_decode_rejects_garbage(bad):
    with pytest.raises(InvalidBuildCode):
        codec.decode(bad)


def test_decode_rejects_non_xml_zlib():
    import base64
    import zlib

    payload = base64.urlsafe_b64encode(zlib.compress(b"not xml at all")).decode()
    with pytest.raises(InvalidBuildCode, match="not XML"):
        codec.decode(payload)


def test_looks_like_code(code_modern, code_legacy):
    assert codec.looks_like_code(code_modern)
    assert codec.looks_like_code(code_legacy)
    assert not codec.looks_like_code("Find me a tanky Lightning Strike build under 20 divines")
