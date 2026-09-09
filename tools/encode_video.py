"""Encode a complete content checked frame sequence without replacing outputs."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.evidence import digest, validate_sequence


def encode(directory, output, records, start, end, identity, width=1920, height=1080):
    directory, output = Path(directory), Path(output)
    validate_sequence(records,start,end,identity)
    for record in records:
        path=directory/f"{record['frame']:04d}.png"
        if digest(path)!=record["sha256"]:
            raise ValueError("Frame hash differs from accepted capture")
    if output.exists():
        raise FileExistsError(output)
    subprocess.run(["ffmpeg","-v","error","-n","-framerate","24","-start_number",str(start),
                    "-i",str(directory/"%04d.png"),"-frames:v",str(end-start+1),
                    "-c:v","libx264","-preset","slow","-crf","16","-pix_fmt","yuv420p",
                    "-color_primaries","bt709","-color_trc","bt709","-colorspace","bt709",
                    "-movflags","+faststart",str(output)],check=True)
    result=json.loads(subprocess.check_output([
        "ffprobe","-v","error","-count_frames","-select_streams","v:0",
        "-show_entries","stream=width,height,r_frame_rate,nb_read_frames,duration",
        "-of","json",str(output)]))["streams"][0]
    if (result["width"]!=width or result["height"]!=height
            or result["r_frame_rate"]!="24/1"
            or int(result["nb_read_frames"])!=end-start+1):
        raise ValueError("Encoded video does not match dimensions, rate or frame count")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("directory",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    rows=json.loads((args.directory/"sequence.json").read_text())
    if not rows:
        raise ValueError("No sequence records")
    result=encode(args.directory,args.output,rows,1,120,rows[0]["fingerprint"])
    print(json.dumps(result,indent=2))
