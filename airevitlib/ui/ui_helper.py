# lib/ui_helper.py
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Windows.Forms import (
    Form, TextBox, Button, Label, DialogResult, 
    FormBorderStyle, FormStartPosition, ScrollBars
)
from System.Drawing import Point, Size, Font, SystemColors
import Autodesk.Revit.UI as UI

class BIMInputDialog(Form):
    """Stable .NET Windows Form for entering structural brief information within CPython."""
    
    def __init__(self, default_text: str):
        super(BIMInputDialog, self).__init__()
        self._setup_ui(default_text)

    def _setup_ui(self, default_text: str):
        self.Text = "AI Revit Agent - Design Brief Input"
        self.Size = Size(650, 480)
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.BackColor = SystemColors.Window
        
        # Label instruction
        self.label = Label()
        self.label.Text = "Describe your building level heights and grid spacing layout below:"
        self.label.Location = Point(15, 15)
        self.label.Size = Size(600, 20)
        self.label.Font = Font("Segoe UI", 10)
        self.Controls.Add(self.label)
        
        # TextBox (Multiline)
        self.textbox = TextBox()
        self.textbox.Multiline = True
        self.textbox.WordWrap = True
        self.textbox.ScrollBars = ScrollBars.Vertical
        self.textbox.Size = Size(600, 320)
        self.textbox.Location = Point(15, 45)
        self.textbox.Text = default_text
        self.textbox.Font = Font("Consolas", 9.5)
        self.Controls.Add(self.textbox)
        
        # Build Button
        self.btn_build = Button()
        self.btn_build.Text = "Generate Structure"
        self.btn_build.Size = Size(140, 35)
        self.btn_build.Location = Point(330, 385)
        self.btn_build.DialogResult = DialogResult.OK
        self.btn_build.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.btn_build)
        
        # Cancel Button
        self.btn_cancel = Button()
        self.btn_cancel.Text = "Cancel"
        self.btn_cancel.Size = Size(120, 35)
        self.btn_cancel.Location = Point(485, 385)
        self.btn_cancel.DialogResult = DialogResult.Cancel
        self.btn_cancel.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.btn_cancel)
        
        self.AcceptButton = self.btn_build
        self.CancelButton = self.btn_cancel


class BIMMessageService:
    """Encapsulates all standard Revit task dialog operations."""

    @staticmethod
    def show_preview(report_text: str) -> bool:
        """Prompts the user with a formatted modeling change summary before writing to database."""
        dialog = UI.TaskDialog("AI Revit Agent Preview")
        dialog.MainInstruction = "Do you want to apply these model changes?"
        dialog.MainContent = report_text
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
        dialog.DefaultButton = UI.TaskDialogResult.Yes
        return dialog.Show() == UI.TaskDialogResult.Yes

    @staticmethod
    def show_error(message: str):
        """Displays error details to the user inside a Revit message box."""
        dialog = UI.TaskDialog("AI Revit Agent - Operational Error")
        dialog.MainInstruction = "Process Aborted"
        dialog.MainContent = message
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Ok
        dialog.Show()