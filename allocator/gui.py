import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.font as tkfont
from tkinter import ttk
from typing import List, Optional, cast
from allocator.logic import load_blocks, assign_containers
import os

# Settings for selection window
class GUI_SELECTION_settings:
    WINDOW_TITLE: str = "Geoinvest Block Allocator"
    WINDOW_GEOMETRY: str = "600x500"
    FONT_FAMILY: str = "Arial"
    FONT_SIZE: int = 14
    DATA_ENTRY_FONT_SIZE: int = 12
    CONTAINER_COUNT_TEXT: str = "Number of containers:"
    CONTAINER_PAYLOAD_TEXT: str = "Max weight per container:"
    MAX_BLOCKS_PER_CONTAINER_TEXT: str = "Max blocks per container:"
    BACKGROUND_COLOR: str = "#f5f0e1"  # Light brown/cream background

# Settings for results window
class GUI_RESULTS_settings:
    WINDOW_TITLE: str = "Block Allocations"
    WINDOW_GEOMETRY: str = "600x600"
    FONT_FAMILY: str = "Arial"
    FONT_SIZE: int = 14
    HEADER_COLOR: str = "#3a7ca5"      # Blue header
    CONTAINER_BG: str = "#f5f5f5"      # Light gray background
    CONTAINER_BORDER: str = "#dcdcdc"  # Border color
    BLOCKS_BG: str = "#ffffff"         # White background for blocks text
    WEIGHT_COLOR: str = "#2c666e"      # Teal for weight information
    BACKGROUND_COLOR: str = "#f5f0e1"  # Light brown/cream background matching selection window


class BlockAllocatorGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(GUI_SELECTION_settings.WINDOW_TITLE)
        self.geometry(GUI_SELECTION_settings.WINDOW_GEOMETRY)
        self.configure(background=GUI_SELECTION_settings.BACKGROUND_COLOR)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            style.theme_use(style.theme_names()[0])
        style.configure('.', font=(GUI_SELECTION_settings.FONT_FAMILY, GUI_SELECTION_settings.FONT_SIZE), padding=6)
        # Configure ttk frame background
        style.configure('TFrame', background=GUI_SELECTION_settings.BACKGROUND_COLOR)
        style.configure('TLabel', background=GUI_SELECTION_settings.BACKGROUND_COLOR)
        style.configure('TButton', background=GUI_SELECTION_settings.BACKGROUND_COLOR)
        entry_font = tkfont.Font(family=GUI_SELECTION_settings.FONT_FAMILY, size=GUI_SELECTION_settings.DATA_ENTRY_FONT_SIZE)

        # Create scrollable frame for main content
        outer_frame = ttk.Frame(self)
        outer_frame.pack(fill=tk.BOTH, expand=True)
        
        # Add canvas for scrolling with background color
        canvas = tk.Canvas(outer_frame, highlightthickness=0, background=GUI_SELECTION_settings.BACKGROUND_COLOR)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(outer_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Add mousewheel scrolling
        def _on_mousewheel(event):
            if event.num == 5 or event.delta < 0:  # Scroll down
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:  # Scroll up
                # Only scroll up if not at the top
                if canvas.yview()[0] > 0:
                    canvas.yview_scroll(-1, "units")
        
        # Bind mousewheel for different platforms
        if self.tk.call('tk', 'windowingsystem') == 'win32':
            # Windows binding
            canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1*(event.delta/120)) if (event.delta < 0 or canvas.yview()[0] > 0) else 0, "units"))
        else:
            # Linux binding
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)
            # macOS binding with Shift+MouseWheel if using X11
            canvas.bind_all("<Shift-MouseWheel>", _on_mousewheel)

        # Main frame inside canvas
        main_frame = ttk.Frame(canvas, padding=(20, 20))
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        # Make frame expand to canvas width
        def configure_frame_width(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', lambda event: [canvas.configure(scrollregion=canvas.bbox("all")), 
                                                 configure_frame_width(event)])

        # Number of containers
        ttk.Label(main_frame, text=GUI_SELECTION_settings.CONTAINER_COUNT_TEXT).grid(row=0, column=0, sticky="e", padx=5, pady=10)
        self.container_count_var = tk.IntVar(value=2)
        container_count_entry = ttk.Entry(main_frame, textvariable=self.container_count_var, width=10, font=entry_font)
        container_count_entry.grid(row=0, column=1, sticky="w", padx=5)

        # Max weight per container
        ttk.Label(main_frame, text=GUI_SELECTION_settings.CONTAINER_PAYLOAD_TEXT).grid(row=1, column=0, sticky="e", padx=5, pady=10)
        self.capacity_var = tk.DoubleVar(value=0.0)
        capacity_entry = ttk.Entry(main_frame, textvariable=self.capacity_var, width=10, font=entry_font)
        capacity_entry.grid(row=1, column=1, sticky="w", padx=5)
        
        # Max blocks per container
        ttk.Label(main_frame, text=GUI_SELECTION_settings.MAX_BLOCKS_PER_CONTAINER_TEXT).grid(row=2, column=0, sticky="e", padx=5, pady=10)
        self.max_blocks_options = ["No limit", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]
        self.max_blocks_var = tk.StringVar(value=self.max_blocks_options[0])
        
        # Style the combobox to match other inputs
        max_blocks_dropdown = ttk.Combobox(
            main_frame, 
            textvariable=self.max_blocks_var, 
            values=self.max_blocks_options, 
            width=10, 
            font=entry_font, 
            state="readonly",
            height=10  # Show all options without scrolling
        )
        
        # Configure the combobox dropdown appearance
        self.option_add('*TCombobox*Listbox.font', entry_font)
        self.option_add('*TCombobox*Listbox.background', '#ffffff')
        self.option_add('*TCombobox*Listbox.selectBackground', '#0078d7')
        self.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        
        # Fix the dropdown color issue - prevent it from turning blue after selection
        style.map('TCombobox',
                  fieldbackground=[('readonly', 'white')],
                  selectbackground=[('readonly', 'white')],
                  selectforeground=[('readonly', 'black')])
        
        # Position the dropdown
        max_blocks_dropdown.grid(row=2, column=1, sticky="w", padx=5)

        # File selection
        self.csv_path: Optional[str] = None
        ttk.Button(main_frame, text="Select CSV File...", command=self.browse_csv, width=20).grid(row=3, column=0, columnspan=2, pady=10)
        self.file_label = ttk.Label(main_frame, text="No file selected", wraplength=300)
        self.file_label.grid(row=4, column=0, columnspan=2)

        ttk.Label(
            main_frame,
            text="Make sure your CSV has columns named 'BlockNo' and 'Weight'",
            wraplength=400,
            foreground="blue",
        ).grid(row=5, column=0, columnspan=2, pady=(0, 15))

        # Run button
        ttk.Button(main_frame, text="Run allocation", command=self.run_allocation, width=20).grid(row=6, column=0, columnspan=2, pady=20)

        for col in range(2):
            main_frame.columnconfigure(col, weight=1)

        # Set scrollbar to top initially and prevent scrolling above this point
        def _prevent_scroll_above_top(event=None):
            # Set initial position at top
            canvas.yview_moveto(0)
            # Configure scrollregion to prevent scrolling above the top
            bbox = canvas.bbox("all")
            if bbox:
                # Set top of scrollregion to 0 to prevent scrolling above the top
                canvas.configure(scrollregion=(bbox[0], 0, bbox[2], bbox[3]))
        
        # Call after all widgets are created and sized
        self.after(100, _prevent_scroll_above_top)

    def browse_csv(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")], title="Select block data CSV")
        if path:
            self.csv_path = path
            # Extract just the filename from the path
            filename = os.path.basename(path)
            self.file_label.config(text=filename)

    def run_allocation(self) -> None:
        if not self.csv_path:
            messagebox.showerror("Error", "Please select a CSV file before running.")
            return

        try:
            count = self.container_count_var.get()
            capacity = self.capacity_var.get()
            
            # Get max blocks per container value
            max_blocks_str = self.max_blocks_var.get()
            max_blocks = None  # None means no limit
            if max_blocks_str != "No limit":
                max_blocks = int(max_blocks_str)
                
            blocks = load_blocks(self.csv_path)
            assignments = assign_containers(blocks, capacity, count, max_blocks)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to process data: {e}")
            return

        # Display results in new window
        result_win = tk.Toplevel(self)
        result_win.title(GUI_RESULTS_settings.WINDOW_TITLE)
        result_win.geometry(GUI_RESULTS_settings.WINDOW_GEOMETRY)
        result_win.configure(background=GUI_RESULTS_settings.BACKGROUND_COLOR)

        # Apply same ttk style to results window
        style = ttk.Style(result_win)
        try:
            style.theme_use('clam')
        except tk.TclError:
            style.theme_use(style.theme_names()[0])
        style.configure('.', font=(GUI_RESULTS_settings.FONT_FAMILY, GUI_RESULTS_settings.FONT_SIZE), padding=4)
        style.configure('TFrame', background=GUI_RESULTS_settings.BACKGROUND_COLOR)
        style.configure('TLabel', background=GUI_RESULTS_settings.BACKGROUND_COLOR)
        
        # Create a canvas with scrollbar for scrolling through containers
        outer_frame = ttk.Frame(result_win)
        outer_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Add a canvas (for scrolling)
        canvas = tk.Canvas(outer_frame, highlightthickness=0, background=GUI_RESULTS_settings.BACKGROUND_COLOR)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(outer_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Configure the canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # Helper function for mousewheel scrolling - create a reusable function
        def bind_mousewheel_to_canvas(canvas_widget, root_widget):
            def _on_mousewheel(event):
                if event.num == 5 or event.delta < 0:  # Scroll down
                    canvas_widget.yview_scroll(1, "units")
                elif event.num == 4 or event.delta > 0:  # Scroll up
                    canvas_widget.yview_scroll(-1, "units")
            
            # Bind mousewheel for different platforms
            if root_widget.tk.call('tk', 'windowingsystem') == 'win32':
                # Windows binding
                canvas_widget.bind_all("<MouseWheel>", lambda event: canvas_widget.yview_scroll(int(-1*(event.delta/120)), "units"))
            else:
                # Linux binding
                canvas_widget.bind_all("<Button-4>", _on_mousewheel)
                canvas_widget.bind_all("<Button-5>", _on_mousewheel)
                # macOS binding with Shift+MouseWheel if using X11
                canvas_widget.bind_all("<Shift-MouseWheel>", _on_mousewheel)
        
        # Bind mousewheel for this canvas
        bind_mousewheel_to_canvas(canvas, result_win)
        
        # Create the frame that will contain all the containers
        result_frame = ttk.Frame(canvas)
        
        # Add the frame to the canvas
        canvas_window = canvas.create_window((0, 0), window=result_frame, anchor="nw")
        
        # Make sure the frame expands to the canvas width
        def configure_frame_width(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', lambda event: [canvas.configure(scrollregion=canvas.bbox("all")), 
                                                 configure_frame_width(event)])

        cols = 2
        max_rows = (len(assignments) + cols - 1) // cols  # Calculate number of rows needed
        
        for row in range(max_rows):
            result_frame.rowconfigure(row, weight=1)
            
        for col in range(cols):
            result_frame.columnconfigure(col, weight=1)
            
        for idx, (cid, info) in enumerate(assignments.items()):
            row, col = divmod(idx, cols)
            blocks_list = cast(List[int], info['blocks'])
            total_wt = cast(float, info['total_weight'])
            
            # Create a frame for this container with improved styling
            container_frame = ttk.Frame(result_frame, relief=tk.RIDGE, padding=10)
            container_frame.grid(row=row, column=col, sticky="nsew", padx=8, pady=8)
            
            # Styled header with container number
            header = ttk.Label(
                container_frame, 
                text=f"Container {cid}", 
                anchor="w",
                font=(GUI_RESULTS_settings.FONT_FAMILY, GUI_RESULTS_settings.FONT_SIZE, "bold"),
                foreground=GUI_RESULTS_settings.HEADER_COLOR
            )
            header.pack(fill="x", pady=(0, 5))
            
            # Separator for visual distinction
            ttk.Separator(container_frame, orient="horizontal").pack(fill="x", pady=3)
            
            # Create a frame for the blocks with border and padding
            blocks_frame = ttk.Frame(container_frame, padding=(5, 5))
            blocks_frame.pack(fill="both", expand=True, pady=5)
            
            # Blocks title
            ttk.Label(
                blocks_frame,
                text="Blocks:",
                anchor="w",
                font=(GUI_RESULTS_settings.FONT_FAMILY, GUI_RESULTS_settings.FONT_SIZE - 1, "italic")
            ).pack(fill="x", anchor="w")
            
            # Create a bordered frame for the text widget
            text_container = ttk.Frame(blocks_frame, relief=tk.GROOVE, borderwidth=1)
            text_container.pack(fill="both", expand=True, pady=3)
            
            # Use Text widget with improved styling for block numbers
            blocks_text = tk.Text(
                text_container, 
                height=5, 
                width=30, 
                wrap="word",
                font=(GUI_RESULTS_settings.FONT_FAMILY, GUI_RESULTS_settings.FONT_SIZE - 1),
                background=GUI_RESULTS_settings.BLOCKS_BG,
                relief=tk.FLAT,
                padx=5,
                pady=5
            )
            
            # Format block numbers more attractively
            if len(blocks_list) > 0:
                formatted_blocks = ""
                for i, block_no in enumerate(blocks_list):
                    formatted_blocks += f"{block_no}"
                    # Add commas between blocks except for the last one in a row
                    if i < len(blocks_list) - 1:
                        formatted_blocks += ", "
                    # Add line break after every 4 blocks
                    if (i + 1) % 4 == 0 and i < len(blocks_list) - 1:
                        formatted_blocks += "\n"
                blocks_text.insert("1.0", formatted_blocks)
            else:
                blocks_text.insert("1.0", "No blocks")
                
            blocks_text.config(state="disabled")  # Make it read-only
            blocks_text.pack(fill="both", expand=True)
            
            # Separator before weight
            ttk.Separator(container_frame, orient="horizontal").pack(fill="x", pady=3)
            
            # Weight information with distinct styling
            weight_frame = ttk.Frame(container_frame)
            weight_frame.pack(fill="x", pady=(5, 0))
            
            ttk.Label(
                weight_frame, 
                text=f"Total Weight:", 
                anchor="w",
                font=(GUI_RESULTS_settings.FONT_FAMILY, GUI_RESULTS_settings.FONT_SIZE - 1)
            ).pack(side=tk.LEFT)
            
            ttk.Label(
                weight_frame, 
                text=f"{total_wt:.2f}", 
                anchor="e",
                font=(GUI_RESULTS_settings.FONT_FAMILY, GUI_RESULTS_settings.FONT_SIZE - 1, "bold"),
                foreground=GUI_RESULTS_settings.WEIGHT_COLOR
            ).pack(side=tk.RIGHT, padx=(5, 0))
            
            result_frame.columnconfigure(col, weight=1)

if __name__ == '__main__':
    app = BlockAllocatorGUI()
    app.mainloop()
