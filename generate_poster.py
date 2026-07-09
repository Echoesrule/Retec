from PIL import Image, ImageDraw, ImageFont
import qrcode

W, H = 1080, 1350
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (160, 160, 160)
DARK = (40, 40, 40)

img = Image.new('RGB', (W, H), WHITE)
draw = ImageDraw.Draw(img)

F = 'C:/Windows/Fonts'
f_brand = ImageFont.truetype(f'{F}/georgiab.ttf', 100)   # Georgia Bold
f_heading = ImageFont.truetype(f'{F}/georgiai.ttf', 40)  # Georgia Italic
f_body = ImageFont.truetype(f'{F}/calibri.ttf', 28)
f_nav = ImageFont.truetype(f'{F}/calibri.ttf', 22)
f_url = ImageFont.truetype(f'{F}/cambriab.ttf', 58)
f_wa = ImageFont.truetype(f'{F}/calibri.ttf', 34)
f_tag = ImageFont.truetype(f'{F}/calibrii.ttf', 24)
f_small = ImageFont.truetype(f'{F}/calibri.ttf', 20)

# === NAV BAR ===
nav_y = 36
draw.rectangle([0, nav_y, W, nav_y + 56], fill=BLACK)

nav_items = ["Home", "Services I Offer", "Blog", "CV", "Contact", "Book Now"]
spacing = 145
total_w = len(nav_items) * spacing - (spacing - 100)
start_x = (W - total_w) // 2
for i, item in enumerate(nav_items):
    x = start_x + i * spacing + (spacing // 2)
    draw.text((x, nav_y + 28), item, fill=WHITE, font=f_nav, anchor="mm")

# Thin line
draw.rectangle([80, nav_y + 66, W - 80, nav_y + 68], fill=BLACK)

# === BRAND ===
draw.text((W//2, 270), "RETEC", fill=BLACK, font=f_brand, anchor="mm")
draw.text((W//2, 350), "Retro Spirit. Modern Solutions.", fill=GRAY, font=f_heading, anchor="mm")

# === WEBSITE ===
draw.text((W//2, 450), "retec.dev", fill=BLACK, font=f_url, anchor="mm")

# Divider
draw.rectangle([W//2 - 70, 500, W//2 + 70, 502], fill=BLACK)

# Tagline
draw.text((W//2, 560), "Flask-Powered Portfolio & Web Apps", fill=GRAY, font=f_body, anchor="mm")

# === Decorative line across ===
draw.rectangle([100, 700, W - 100, 702], fill=BLACK)

# === BOTTOM SECTION ===

# Left: WhatsApp
wa_x = 140
wa_y = 1050
draw.text((wa_x, wa_y - 30), "Let's Connect", fill=BLACK, font=f_body, anchor="mm")
draw.text((wa_x, wa_y + 20), "+254 114 581 500", fill=BLACK, font=f_wa, anchor="mm")
draw.text((wa_x, wa_y + 65), "WhatsApp", fill=GRAY, font=f_tag, anchor="mm")

# Vertical separator
draw.rectangle([W//2 - 1, 920, W//2 + 1, 1150], fill=BLACK)

# Right: QR
github_url = "https://github.com/echoesrule"
qr = qrcode.make(github_url, box_size=10, border=2)
qr = qr.convert("RGB").resize((200, 200))
qr_x = W - 140 - 200
qr_y = wa_y - 55
img.paste(qr, (qr_x, qr_y))
draw.rectangle([qr_x - 3, qr_y - 3, qr_x + 203, qr_y + 203], outline=BLACK, width=2)
draw.text((qr_x + 100, qr_y + 220), "GitHub", fill=BLACK, font=f_tag, anchor="mt")

# === BOTTOM BAR ===
draw.rectangle([0, H - 10, W, H], fill=BLACK)

img.save("poster.png")
print("poster.png generated")
