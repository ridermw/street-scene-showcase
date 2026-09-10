import hashlib
import json
import os
import unittest
from PIL import Image
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("PUBLICATION_SITE", ROOT / "docs")).resolve()


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
    def check_pages(self, names):
        for name in names:
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
                if target.is_dir():
                    target = target / "index.html"
                self.assertTrue(target.is_file(), url)

    def test_public_pages_have_resolvable_links_and_image_descriptions(self):
        self.check_pages(("index.html", "concept.html", "attempts.html"))

    def test_complete_interactive_candidate_preserves_navigation_and_local_links(self):
        manifest = SITE / "assets" / "interactive" / "scene-manifest.json"
        if not manifest.is_file() and "PUBLICATION_SITE" not in os.environ:
            self.skipTest("Generated release is not published; validate its staged PUBLICATION_SITE")
        self.assertTrue(manifest.is_file(), "Incomplete interactive candidate")
        self.check_pages(("interactive/index.html",))
        for name in ("index.html", "concept.html", "attempts.html"):
            parser = Links()
            parser.feed((SITE / name).read_text())
            self.assertIn("interactive/index.html", parser.urls)
        metadata = json.loads(manifest.read_text())
        asset = manifest.parent / metadata["asset"]["file"]
        self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), metadata["asset"]["sha256"])

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

    def test_public_comparison_is_complete_and_has_no_private_records(self):
        self.check_pages(("comparison.html",))
        for name in ("index.html", "concept.html", "attempts.html", "interactive/index.html"):
            self.assertIn("comparison.html", (SITE / name).read_text())
        assets = SITE / "assets" / "comparison"
        expected = {"motion-and-restart.mp4"}
        for frame in (1, 61, 120):
            for label in ("A", "B"):
                name = f"frame-{frame:03}-{label}.jpg"
                expected.add(name)
                with Image.open(assets / name) as image:
                    self.assertEqual(image.size, (1920, 1136))
                    self.assertEqual(image.format, "JPEG")
                    self.assertFalse(image.getexif())
                    self.assertNotIn("xmp", image.info)
        self.assertEqual({file.name for file in assets.iterdir()}, expected)

    def test_published_video_is_the_selected_delivery(self):
        path = SITE / "assets" / "street-scene-attempt-23.mp4"
        self.assertTrue(path.is_file(), "Missing final video")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         "31b4c10b7051ce67b980fbc12d39b5eedf1bbcf37ec168be1cc8f6c270dd1b1e")


if __name__ == "__main__":
    unittest.main()
