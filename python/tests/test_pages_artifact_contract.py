from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "static.yml"
LANDING_PAGE = ROOT / "docs" / "aegis-brief" / "index.html"
RECORDINGS = ("toolkit", "immune", "veriflow")


class VideoPlayers(HTMLParser):
    def __init__(self):
        super().__init__()
        self.players = []

    def handle_starttag(self, tag, attrs):
        if tag == "video":
            self.players.append(dict(attrs))


def test_pages_landing_page_embeds_each_recording_and_transcript():
    page = LANDING_PAGE.read_text(encoding="utf-8")
    parser = VideoPlayers()
    parser.feed(page)
    sources = {player.get("src"): player for player in parser.players}

    for recording in RECORDINGS:
        source = f"./docs/demos/{recording}.mp4"
        assert source in sources
        assert "controls" in sources[source]
        assert f'href="{source.replace(".mp4", ".txt")}"' in page
        assert (ROOT / "docs" / "demos" / f"{recording}.mp4").stat().st_size > 0


def test_pages_workflow_stages_and_validates_landing_page_and_recordings():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "set -euo pipefail" in workflow
    assert "cp -a docs/aegis-brief/. _site/" in workflow
    assert "cp -a docs/demos/. _site/docs/demos/" in workflow
    assert "test -s _site/index.html" in workflow
    assert 'test -s "_site/docs/demos/${recording}.mp4"' in workflow
    assert 'grep -Fq "src=\\"./docs/demos/${recording}.mp4\\"" docs/aegis-brief/index.html' in workflow
    assert "path: _site" in workflow
