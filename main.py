import sys


def _enable_dpi_awareness() -> None:
    """Ask Windows for sharp text on high-DPI screens instead of blurry scaling.

    Must run before the first Tk window is created."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware (Windows 8.1+)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()  # Windows Vista+
    except Exception:
        pass  # Never stop the app from starting over this.


def main() -> None:
    _enable_dpi_awareness()
    from allocator.gui import BlockAllocatorGUI

    app = BlockAllocatorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
