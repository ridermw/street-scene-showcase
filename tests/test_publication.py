import hashlib
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "docs"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.images = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        for key in ("href", "src", "poster"):
            if key in attributes:
                self.urls.append(attributes[key])
        if tag == "img":
            self.images.append(attributes)


class PublicationTests(unittest.TestCase):
    def test_public_pages_have_resolvable_links_and_image_descriptions(self):
        for name in ("index.html", "concept.html", "attempts.html"):
            path = SITE / name
            self.assertTrue(path.is_file(), f"Missing public page: {name}")
            parser = Links()
            text = path.read_text()
            parser.feed(text)
            self.assertNotIn("/" + "Users/", text)
            self.assertNotIn("127." + "0.0.1", text)
            for image in parser.images:
                self.assertTrue(image.get("alt"))
            for url in parser.urls:
                parts = urlsplit(url)
                if parts.scheme:
                    self.assertEqual(parts.scheme, "https", url)
                    continue
                self.assertFalse(parts.netloc, url)
                target = (path.parent / unquote(parts.path)).resolve()
                self.assertTrue(target.is_relative_to(SITE), url)
                self.assertTrue(target.is_file(), url)

    def test_gallery_accounts_for_the_retained_attempts(self):
        path = SITE / "attempts.json"
        self.assertTrue(path.is_file(), "Missing attempt inventory")
        inventory = json.loads(path.read_text())
        self.assertEqual(inventory["missing_preview_attempts"], [4])
        self.assertEqual({row["attempt"] for row in inventory["attempts"]},
                         set(range(1, 24)) - {4})
        page = (SITE / "attempts.html").read_text()
        for row in inventory["attempts"]:
            self.assertTrue((SITE / row["image"]).is_file())
            self.assertIn(f'id="attempt-{row["attempt"]:02d}"', page)

    def test_published_video_is_the_selected_delivery(self):
        path = SITE / "assets" / "street-scene-attempt-23.mp4"
        self.assertTrue(path.is_file(), "Missing final video")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "31b4c10b7051ce67b980fbc12d39b5eedf1bbcf37ec168be1cc8f6c270dd1b1e")


if __name__ == "__main__":
    unittest.main()
