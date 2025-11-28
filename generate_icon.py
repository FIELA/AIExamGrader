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
    
    # Save as ICO for Windows
    # ICO files can contain multiple sizes
    img.save("assets/icon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Icon generated at assets/icon.ico")

def create_refresh_icon():
    size = (64, 64) # Standard icon size
    # Icon color: White (since buttons have colored background)

    icon_color = (255, 255, 255, 255)
    
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw two arrows forming a circle
    center_x, center_y = 32, 32
    radius = 20
    width = 6
    
    import math
    
    # Arrow 1 (Top-Right to Bottom-Left)
    start_angle = -30
    end_angle = 150
    
    # Draw arc
    draw.arc([center_x-radius, center_y-radius, center_x+radius, center_y+radius], start=start_angle, end=end_angle, fill=icon_color, width=width)
    
    # Arrowhead 1
    # End point of arc
    end_rad = math.radians(end_angle)
    end_x = center_x + radius * math.cos(end_rad)
    end_y = center_y + radius * math.sin(end_rad)
    
    # Arrowhead points
    # Simple triangle
    draw.polygon([(end_x, end_y-8), (end_x, end_y+8), (end_x-10, end_y)], fill=icon_color)
    
    # Arrow 2 (Bottom-Left to Top-Right)
    start_angle2 = 150
    end_angle2 = 330
    
    draw.arc([center_x-radius, center_y-radius, center_x+radius, center_y+radius], start=start_angle2, end=end_angle2, fill=icon_color, width=width)
    
    # Arrowhead 2
    end_rad2 = math.radians(end_angle2)
    end_x2 = center_x + radius * math.cos(end_rad2)
    end_y2 = center_y + radius * math.sin(end_rad2)
    
    draw.polygon([(end_x2, end_y2-8), (end_x2, end_y2+8), (end_x2+10, end_y2)], fill=icon_color)

    # Ensure directory exists
    import os
    if not os.path.exists("assets/icons"):
        os.makedirs("assets/icons")
        
    img.save("assets/icons/refresh.png")
    print("Refresh icon generated at assets/icons/refresh.png")

if __name__ == "__main__":
    create_icon()
    create_refresh_icon()
