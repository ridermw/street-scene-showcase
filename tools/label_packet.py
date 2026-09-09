"""Prepare equal presentation images with visible neutral identity labels."""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.evidence import atomic_json, digest


def make_packet(sources, output):
    if not sources or any(len(label)!=1 or not "A"<=label<="Z" for label in sources):
        raise ValueError("Use neutral single uppercase labels")
    images={}
    for label,source in sources.items():
        with Image.open(source) as image:
            images[label]=image.convert("RGB")
    if len({image.size for image in images.values()})!=1:
        raise ValueError("Comparison images must have identical dimensions")
    output=Path(output)
    output.mkdir(exist_ok=False)
    manifest={}
    for label,image in images.items():
        canvas=Image.new("RGB",(image.width,image.height+56),"black")
        canvas.paste(image,(0,56))
        ImageDraw.Draw(canvas).text((16,7),label,font=ImageFont.load_default(size=36),fill="white")
        path=output/f"{label}.jpg"
        canvas.save(path,quality=95,subsampling=0)
        manifest[label]={"source":str(sources[label]),"source_sha256":digest(sources[label]),
                         "image":str(path),"sha256":digest(path)}
    atomic_json(output.parent/f"{output.name}-manifest.json",manifest)
    return manifest


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("sources",nargs="+",help="Neutral label=source path")
    args=parser.parse_args()
    make_packet(dict(value.split("=",1) for value in args.sources),args.output)
