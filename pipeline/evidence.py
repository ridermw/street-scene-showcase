"""Content bound evidence and an atomic local comparison page."""

import hashlib
import html
import json
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fingerprint(paths, settings):
    payload = {"files": {str(Path(p).resolve()): digest(p) for p in paths},
               "settings": settings}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def atomic_text(path, text):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink()
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, data):
    atomic_text(path, json.dumps(data, indent=2, sort_keys=True))


def retain_dependencies(paths, root):
    root = Path(root)
    root.mkdir(exist_ok=True)
    retained = {}
    for source in paths:
        source = Path(source)
        checksum = digest(source)
        target = root / checksum
        if not target.exists():
            with source.open("rb") as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
        if digest(target) != checksum:
            raise ValueError("Retained dependency content differs from its hash")
        retained[str(source)] = {"path": str(target), "sha256": checksum}
    return retained


def validate_review(review, scene_fingerprint, reference_fingerprint, instructions_version):
    if (review["scene_fingerprint"] != scene_fingerprint
            or review["reference_fingerprint"] != reference_fingerprint
            or review["instructions_version"] != instructions_version):
        raise ValueError("Review fingerprint or instruction version is stale")
    if not review["image_hashes"]:
        raise ValueError("Review has no images")
    for path, expected in review["image_hashes"].items():
        if digest(path) != expected:
            raise ValueError("Reviewed image has changed")
    if review["decision"] not in {"reject", "improve", "accept", "inconclusive"}:
        raise ValueError("Invalid review decision")


def validate_sequence(frames, start, end, expected_fingerprint):
    if [row["frame"] for row in frames] != list(range(start, end + 1)):
        raise ValueError("Frame sequence is incomplete, duplicated, or out of order")
    if any(row["fingerprint"] != expected_fingerprint for row in frames):
        raise ValueError("Frame sequence mixes capture specifications")


def write_progress(root, description, images, state, videos=()):
    root = Path(root).resolve()
    cards = []
    for image in list(images)+list(videos):
        image = Path(image).resolve()
        if not image.is_relative_to(root):
            raise ValueError("Image is outside preview root")
        if not image.is_file():
            raise FileNotFoundError(image)
        relative = image.relative_to(root).as_posix()
        media=(f'<video controls preload="metadata" src="{quote(relative)}"></video>'
               if image.suffix.lower()==".mp4"
               else f'<img src="{quote(relative)}" alt="{html.escape(image.stem)}">')
        cards.append(f'<figure>{media}'
                     f'<figcaption>{html.escape(image.stem)}</figcaption></figure>')
    document = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="refresh" content="30">
<title>Street scene comparison</title>
<style>body{{margin:2rem;background:#15191f;color:#e8edf2;font:16px/1.5 system-ui}}
h1{{font-size:1.6rem}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:1rem}}
figure{{margin:0;background:#202731;padding:.5rem}}img,video{{width:100%;height:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}
figcaption{{padding:.4rem}}.status{{color:#e3ba73}}</style>
<h1>Street scene comparison</h1><p class="status">State: {html.escape(state)}. User acceptance: pending.</p>
<pre>{html.escape(description)}</pre><div class="grid">{''.join(cards)}</div></html>"""
    atomic_text(root / "index.html", document)
