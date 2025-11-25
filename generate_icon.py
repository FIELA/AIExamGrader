from PIL import Image, ImageDraw

def create_icon():
    size = (512, 512)
    # Background color: Blue #2563EB
    bg_color = (37, 99, 235)
    # Icon color: White
    icon_color = (255, 255, 255)
    
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Rounded Square Background
    rect_coords = [20, 20, 492, 492]
    radius = 100
    draw.rounded_rectangle(rect_coords, radius=radius, fill=bg_color)
    
    # Centered White Square
    # Size 260x260
    center_x, center_y = 256, 256
    half_size = 130
    square_coords = [center_x - half_size, center_y - half_size, center_x + half_size, center_y + half_size]
    draw.rectangle(square_coords, fill=icon_color)
    
    # Checkmark (Blue) inside the white square
    # Points relative to center
    # Start: left-ish
    # Middle: bottom-center
    # End: top-right
    check_points = [
        (center_x - 70, center_y + 10),  # Start
        (center_x - 10, center_y + 70),  # Bottom point
        (center_x + 80, center_y - 60)   # End point
    ]
    draw.line(check_points, fill=bg_color, width=45, joint='curve')
    
    # AI Sparkle (Top right of the white square)
    # Let's move it slightly outside or on the corner
    cx, cy = center_x + half_size, center_y - half_size
    r_out = 35
    r_in = 12
    points = []
    import math
    for i in range(8):
        angle = i * math.pi / 4
        r = r_out if i % 2 == 0 else r_in
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        points.append((x, y))
    
    draw.polygon(points, fill=(255, 215, 0)) # Gold sparkle
    
    img.save("assets/icon.png")
    print("Icon generated at assets/icon.png")

if __name__ == "__main__":
    create_icon()
