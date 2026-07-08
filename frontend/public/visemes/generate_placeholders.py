"""
Generate placeholder viseme images (colored circles with numbers)
Run this script to create 1.png through 15.png
"""
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("PIL not available, creating simple colored placeholders")

import os

# Color scheme for each viseme
COLORS = [
    (239, 68, 68),    # Red - Bilabial
    (245, 158, 11),   # Amber - Open vowels
    (16, 185, 129),   # Green - Front vowels
    (59, 130, 246),   # Blue - Rounded vowels
    (139, 92, 246),   # Purple - Central vowels
    (236, 72, 153),   # Pink - Alveolar
    (20, 184, 166),   # Teal - Velar
    (249, 115, 22),   # Orange - Glottal
    (99, 102, 241),   # Indigo - Diphthongs
    (132, 204, 22),   # Lime - Palatal
    (6, 182, 212),    # Cyan - Transition bilabial
    (168, 85, 247),   # Violet - Transition alveolar
    (244, 63, 94),    # Rose - Transition velar
    (100, 116, 139),  # Slate - Silence
    (120, 113, 108),  # Stone - Neutral
]

LABELS = [
    "ㅂㅍㅁ",
    "ㅏㅐ",
    "ㅣㅔ",
    "ㅗㅜ",
    "ㅓㅡ",
    "ㄷㅌㄴ",
    "ㄱㅋㅇ",
    "ㅎ",
    "ㅘㅝ",
    "ㅈㅊ",
    "→ㅂ",
    "→ㄷ",
    "→ㄱ",
    "휴지",
    "중립"
]

def create_image_with_pil(number, color, label):
    """Create viseme image using PIL"""
    size = 512
    img = Image.new('RGB', (size, size), color)
    draw = ImageDraw.Draw(img)

    # Try to use a nice font, fallback to default
    try:
        font_large = ImageFont.truetype("arial.ttf", 180)
        font_small = ImageFont.truetype("malgun.ttf", 80)  # Korean font
    except:
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 180)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 80)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Draw number
    text = str(number)
    bbox = draw.textbbox((0, 0), text, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((size - text_width) // 2, (size - text_height) // 2 - 50)

    # White text with shadow
    draw.text((position[0] + 4, position[1] + 4), text, fill=(0, 0, 0, 128), font=font_large)
    draw.text(position, text, fill=(255, 255, 255), font=font_large)

    # Draw label
    label_bbox = draw.textbbox((0, 0), label, font=font_small)
    label_width = label_bbox[2] - label_bbox[0]
    label_position = ((size - label_width) // 2, position[1] + text_height + 30)
    draw.text(label_position, label, fill=(255, 255, 255, 200), font=font_small)

    return img

def create_simple_placeholder(number, color):
    """Create simple SVG placeholder"""
    svg_content = f'''<svg width="512" height="512" xmlns="http://www.w3.org/2000/svg">
  <rect width="512" height="512" fill="rgb({color[0]},{color[1]},{color[2]})"/>
  <text x="50%" y="50%" font-size="180" fill="white" text-anchor="middle" dy=".3em" font-family="Arial, sans-serif" font-weight="bold">{number}</text>
</svg>'''
    return svg_content

# Generate images
script_dir = os.path.dirname(os.path.abspath(__file__))

for i in range(1, 16):
    color = COLORS[i - 1]
    label = LABELS[i - 1]
    filename = os.path.join(script_dir, f"{i}.png")

    if HAS_PIL:
        img = create_image_with_pil(i, color, label)
        img.save(filename)
        print(f"Created {filename}")
    else:
        # Save as SVG if PIL not available
        svg_filename = os.path.join(script_dir, f"{i}.svg")
        with open(svg_filename, 'w', encoding='utf-8') as f:
            f.write(create_simple_placeholder(i, color))
        print(f"Created {svg_filename} (install Pillow for PNG generation)")

print("\n✅ Viseme placeholder generation complete!")
print("For production, replace these with actual mouth shape images.")
