"""Unit tests for bilingual ASS subtitle generation."""
from app.services.dubbing.subtitle_burn import (
    _ass_escape,
    _build_ass_header,
    write_bilingual_ass,
)


def test_default_font_size_is_readable_at_1080p():
    header = _build_ass_header()
    # Chinese style is the third style line and carries the base size.
    assert "Style: Chinese,Microsoft YaHei,48," in header


def test_ass_escape_neutralises_override_tags_and_newlines():
    assert _ass_escape("hello {\\b1}world") == "hello \\{\\\\b1\\}world"
    assert _ass_escape("line1\nline2") == "line1\\Nline2"


def test_write_bilingual_ass_escapes_text(tmp_path):
    out = tmp_path / "sub.ass"
    segments = [{"start": 0.0, "end": 1.5, "text": "Hello {world}"}]
    translations = ["你好 {世界}"]

    write_bilingual_ass(segments, translations, str(out))

    content = out.read_text(encoding="utf-8")
    assert "Hello \\{world\\}" in content
    assert "你好 \\{世界\\}" in content
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,Original" in content

