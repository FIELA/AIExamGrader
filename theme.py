# Copyright (c) 2025 JASim. Licensed under NCEL-Strict License v2.0.
# STRICT NON-COMMERCIAL USE ONLY. No AI/ML training, fine-tuning, or public distribution of Derivative Works.
# Modifications may only be shared as Patch Files.
# Public forks allowed solely for PRs (delete within 14 days after PR merged, rejected, or closed).
# Commercial licensing inquiries: nicofiela@outlook.com. See LICENSE file for full terms.


class Theme:
    # Colors
    PRIMARY = "#1D4ED8"       # Darker Blue
    PRIMARY_HOVER = "#1E40AF"
    
    SECONDARY = "#059669"     # Darker Green
    SECONDARY_HOVER = "#047857"
    
    DANGER = "#DC2626"        # Darker Red
    DANGER_HOVER = "#B91C1C"
    
    WARNING = "#D97706"       # Darker Amber/Orange
    WARNING_HOVER = "#B45309"
    
    INFO = "#2563EB"          # Blue
    
    # Backgrounds
    BG_LIGHT = "#F3F4F6"      # Light Gray
    BG_DARK = "#111827"       # Dark Gray/Black
    
    SURFACE_LIGHT = "#FFFFFF"
    SURFACE_DARK = "#1F2937"
    
    # Text
    TEXT_LIGHT = "#111827"
    TEXT_DARK = "#F9FAFB"
    TEXT_MUTED_LIGHT = "#6B7280"
    TEXT_MUTED_DARK = "#9CA3AF"
    
    # Borders
    BORDER_LIGHT = "#E5E7EB"
    BORDER_DARK = "#374151"

    # Fonts
    FONT_FAMILY = "Inter"  # Or system default
    FONT_SIZE_NORMAL = 13
    FONT_SIZE_LARGE = 16
    FONT_SIZE_XLARGE = 20
    
    @staticmethod
    def get_font(size=None, weight="normal"):
        s = size if size else Theme.FONT_SIZE_NORMAL
        return (Theme.FONT_FAMILY, s, weight)
