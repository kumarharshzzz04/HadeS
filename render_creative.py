import pathlib
from PIL import Image, ImageDraw, ImageFont

DIRECTORY = pathlib.Path(__file__).resolve().parent
out_png = DIRECTORY / "hades_creative_view.png"

canvas = Image.new("RGB", (1240, 1120), "#07080b")
draw = ImageDraw.Draw(canvas)

def font(size, bold=False):
    candidates = []
    if bold:
        candidates += ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/calibribd.ttf"]
    candidates += ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/tahoma.ttf"]
    for p in candidates:
        if pathlib.Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

f_head = font(60, bold=True)
f_sub = font(20)
f_body = font(22)
f_small = font(17)
f_tiny = font(15)

def rrect(box, radius, fill=None, outline=None, width=1):
    draw.rectangle(box, fill=fill, outline=outline, width=width)
    x0, y0, x1, y1 = box
    draw.pieslice([x0, y0, x0 + 2*radius, y0 + 2*radius], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x1 - 2*radius, y0, x1, y0 + 2*radius], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x0, y1 - 2*radius, x0 + 2*radius, y1], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x1 - 2*radius, y1 - 2*radius, x1, y1], 0, 90, fill=fill, outline=outline, width=width)

y = 120
draw.text((60, y), "HadeS", font=f_head, fill="#ECEEF2")
y += 84
draw.text((60, y), "Local AI Teaching Assistant", font=f_sub, fill="#9AA1AD")
y += 44
draw.text((60, y), "Ask your lectures. Get the answer and the minute.", font=f_head, fill="#ECEEF2")
y += 84
draw.text((60, y), "A local AI tutor over recorded lectures. Ask in plain words, and every answer", font=f_body, fill="#9AA1AD")
y += 38
draw.text((60, y), "points back to the exact lesson and timestamp where it was taught — no cloud,", font=f_body, fill="#9AA1AD")
y += 38
draw.text((60, y), "no API keys, no uploads.", font=f_body, fill="#9AA1AD")
y += 64
rrect([60, y, 60 + 220, y + 32], 16, fill="#161B26", outline="#1F2735", width=1)
draw.text((76, y + 7), "RAG · offline · local only", font=f_tiny, fill="#9AA1AD")
y += 64
for label, value in [("3 courses", "3"), ("chunks indexed", "2,077"), ("retrieval eval", "11/11")]:
    draw.text((60, y), value, font=f_head, fill="#ECEEF2")
    draw.text((60 + 150, y + 14), label.upper(), font=f_tiny, fill="#6C7480")
    y += 86

y += 36
draw.line([(60, y), (1180, y)], fill="#1F2735", width=1)
y += 46
draw.text((60, y), "WHAT IT DOES", font=f_tiny, fill="#9AA1AD")
y += 34
draw.text((60, y), "HadeS turns a folder of lecture recordings into something you can talk to.", font=f_body, fill="#9AA1AD")
y += 34
draw.text((60, y), "Ask normal questions like “What are functions?” — each answer points back to", font=f_body, fill="#9AA1AD")
y += 34
draw.text((60, y), "the exact lesson and timestamp where it was taught.", font=f_body, fill="#9AA1AD")
y += 60
rrect([60, y, 340, y + 84], 14, fill="#11151C", outline="#1F2735", width=1)
draw.text((80, y + 14), "Why does age = age + 1 work?", font=f_body, fill="#C7D2FF")
rrect([380, y, 700, y + 84], 14, fill="#11151C", outline="#1F2735", width=1)
draw.text((400, y + 14), "It rebinds the name: age stops", font=f_body, fill="#9AA1AD")
draw.text((400, y + 40), "pointing at the old value and starts", font=f_body, fill="#9AA1AD")
y += 104
rrect([60, y, 330, y + 44], 16, fill="#121722", outline="#2D3850", width=1)
draw.text((80, y + 10), "★ Variables & assignment", font=f_tiny, fill="#9AA1AD")
draw.text((80, y + 26), "01:01:33", font=f_tiny, fill="#6C7480")
rrect([390, y, 630, y + 44], 16, fill="#121722", outline="#2D3850", width=1)
draw.text((410, y + 10), "▷ Also mentioned", font=f_tiny, fill="#9AA1AD")
draw.text((410, y + 26), "00:39", font=f_tiny, fill="#6C7480")
y += 104

draw.line([(60, y), (1180, y)], fill="#1F2735", width=1)
y += 46
draw.text((60, y), "WHAT YOU NOTICE FIRST", font=f_tiny, fill="#9AA1AD")
y += 34
cards = [
    ("Ask like a person", "No keywords, no lecture numbers."),
    ("Answers show their work", "Each reply carries the lesson behind it."),
    ("Play the exact moment", "Open a source and the lecture plays in place."),
    ("Quiz while it’s fresh", "Three questions, graded on click."),
    ("A course is its own world", "History and review never mix."),
    ("Nothing leaves this machine", "No account, no uploads, offline forever."),
]
for i, (title, desc) in enumerate(cards):
    col = i % 3
    row = i // 3
    x = 60 + col * 360
    yy = y + row * 138
    rrect([x, yy, x + 340, yy + 122], 14, fill="#0E1116", outline="#1F2735", width=1)
    rrect([x + 12, yy + 14, x + 52, yy + 50], 10, fill="#151B27", outline="#273140", width=1)
    draw.text((x + 24, yy + 24), "✓", font=f_body, fill="#9AA1AD")
    draw.text((x + 72, yy + 18), title, font=f_body, fill="#ECEEF2")
    draw.text((x + 24, yy + 62), desc, font=f_small, fill="#9AA1AD")

y += 286
draw.line([(60, y), (1180, y)], fill="#1F2735", width=1)
y += 46
draw.text((60, y), "HOW IT WORKS", font=f_tiny, fill="#9AA1AD")
y += 38
steps = [
    ("1", "Transcribe the lectures", "Recordings are transcribed with exact second timestamps, then split into clean chunks."),
    ("2", "Embed and index them", "Each chunk gets a local embedding and is stored in a FAISS vector index, fully offline."),
    ("3", "Retrieve then curate", "Top candidates are clustered into lessons; the model picks the main lesson and demotes incidental mentions."),
    ("4", "Answer and cite", "The answer is generated from the grounded lesson and streamed word-by-word, with timestamps attached."),
]
for num, title, desc in steps:
    rrect([60, y, 630, y + 64], 14, fill="#0E1116", outline="#1F2735", width=1)
    rrect([84, y + 18, 110, y + 44], 8, fill="#161D2B", outline="#2D3850", width=1)
    draw.text((92, y + 22), num, font=f_body, fill="#9AA1AD")
    draw.text((128, y + 14), title, font=f_body, fill="#ECEEF2")
    draw.text((128, y + 38), desc, font=f_small, fill="#9AA1AD")
    y += 82

y += 44
draw.line([(60, y), (1180, y)], fill="#1F2735", width=1)
y += 46
rrect([60, y, 340, y + 36], 16, fill="#161B26", outline="#1F2735", width=1)
draw.text((80, y + 8), "100% local · offline forever", font=f_tiny, fill="#9AA1AD")
rrect([410, y, 690, y + 36], 16, fill="#161B26", outline="#1F2735", width=1)
draw.text((430, y + 8), "No cloud · no API keys", font=f_tiny, fill="#9AA1AD")
rrect([760, y, 1060, y + 36], 12, fill="#10141B", outline="#1F2735", width=1)
draw.ellipse([776, y + 12, 784, y + 20], fill="#5B6C86")
draw.text((796, y + 6), "demo-ready · talk to it like a tutor", font=f_tiny, fill="#9AA1AD")
y += 60
draw.text((60, y), "Built by Kumar Harsh", font=f_small, fill="#ECEEF2")
draw.text((60, y + 22), "local RAG teaching assistant · v2", font=f_tiny, fill="#6C7480")

out_png.parent.mkdir(parents=True, exist_ok=True)
canvas.save(out_png)
print("RENDER_READY")
print("width", canvas.width, "height", canvas.height)
print("bytes", out_png.stat().st_size)
print("markdown", f"![HadeS creative]({out_png})")
