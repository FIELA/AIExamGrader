import customtkinter as ctk
from theme import Theme
import os
import sys
from PIL import Image


class SplashScreen(ctk.CTkToplevel):
    """
    Splash screen displayed during application initialization.
    Shows loading progress and current status to reduce user anxiety.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Hide initially to prevent flicker/jumping
        self.withdraw()

        # Window configuration
        self.title("")  # No title
        
        # Remove window decorations
        self.overrideredirect(True)
        
        # Calculate center position
        # We don't need update_idletasks() if we hardcode the size we want
        width = 500
        height = 300
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
            
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        
        # Set geometry with position immediately
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # Now show the window
        self.deiconify()
        self.update_idletasks() # Ensure layout is applied


        
        # Set appearance
        ctk.set_appearance_mode("System")
        
        # Make window stay on top
        self.attributes('-topmost', True)
        
        # Configure background
        self.configure(fg_color=(Theme.BG_LIGHT, Theme.BG_DARK))
        
        # Main container with padding
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=40, pady=40)
        
        # Logo/Icon (if available)
        self.logo_image = None
        try:
            icon_path = self.resource_path(os.path.join("assets", "icon.png"))
            if os.path.exists(icon_path):
                pil_img = Image.open(icon_path)
                # Resize to 80x80
                pil_img = pil_img.resize((80, 80), Image.Resampling.LANCZOS)
                self.logo_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(80, 80))
                logo_label = ctk.CTkLabel(self.main_frame, image=self.logo_image, text="")
                logo_label.pack(pady=(20, 10))
            else:
                # No icon, show emoji or text placeholder
                placeholder = ctk.CTkLabel(
                    self.main_frame,
                    text="📝",
                    font=ctk.CTkFont(size=60)
                )
                placeholder.pack(pady=(20, 10))
        except Exception as e:
            print(f"Could not load splash icon: {e}")
            # Show placeholder on error
            placeholder = ctk.CTkLabel(
                self.main_frame,
                text="AI",
                font=ctk.CTkFont(size=48, weight="bold")
            )
            placeholder.pack(pady=(20, 10))

        
        # App title
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="AI Exam Grader",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.title_label.pack(pady=(10, 5))
        
        # Subtitle
        self.subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text="智能试卷批改系统",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray60")
        )
        self.subtitle_label.pack(pady=(0, 30))
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.main_frame,
            width=400,
            height=8,
            corner_radius=4,
            progress_color=Theme.PRIMARY
        )
        self.progress_bar.pack(pady=(0, 15))
        self.progress_bar.set(0)
        
        # Status label
        self.status_label = ctk.CTkLabel(
            self.main_frame,
            text="Initializing...",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray50")
        )
        self.status_label.pack()
        
        # Version info
        self.version_label = ctk.CTkLabel(
            self.main_frame,
            text="v1.0",
            font=ctk.CTkFont(size=10),
            text_color=("gray60", "gray40")
        )
        self.version_label.pack(side="bottom", pady=(20, 0))
        
        # Force window to appear
        self.update()
    
    def resource_path(self, relative_path):
        """Get absolute path to resource, works for dev and for PyInstaller"""
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            if getattr(sys, 'frozen', False):
                exe_dir = os.path.dirname(sys.executable)
                internal_dir = os.path.join(exe_dir, '_internal')
                if os.path.exists(os.path.join(internal_dir, relative_path)):
                    base_path = internal_dir
                elif os.path.exists(os.path.join(exe_dir, relative_path)):
                    base_path = exe_dir
                else:
                    base_path = exe_dir
            else:
                base_path = os.path.abspath(".")
        
        return os.path.join(base_path, relative_path)
    
    def update_progress(self, percentage, message):
        """
        Update the progress bar and status message.
        
        Args:
            percentage: Progress value from 0 to 100
            message: Status message to display
        """
        # Clamp percentage to valid range
        percentage = max(0, min(100, percentage))
        
        # Update progress bar (0.0 to 1.0)
        self.progress_bar.set(percentage / 100.0)
        
        # Update status message
        self.status_label.configure(text=message)
        
        # Force UI update
        self.update_idletasks()
        self.update()
    
    def close(self):
        """Close the splash screen gracefully"""
        self.destroy()



