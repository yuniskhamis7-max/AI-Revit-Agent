# airevitlib/ui/ui_helper.py
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Windows.Forms import (
    Form, TextBox, Button, Label, ComboBox, ComboBoxStyle, DialogResult, 
    FormBorderStyle, FormStartPosition, ScrollBars
)
from System.Drawing import Point, Size, Font, SystemColors
import Autodesk.Revit.UI as UI

class BIMInputDialog(Form):
    """Unified Dashboard Form containing API setups, model selectors, and design brief inputs."""
    
    def __init__(self, default_text: str, saved_key: str, saved_model: str, fetch_models_func):
        """
        Args:
            default_text: Initial brief template.
            saved_key: Saved API key (if any).
            saved_model: Saved model name.
            fetch_models_func: Callback function in services that takes an API key and returns list of models.
        """
        super(BIMInputDialog, self).__init__()
        self.fetch_models_func = fetch_models_func
        self.saved_model = saved_model
        self._setup_ui(default_text, saved_key)
        
        # Auto-fetch models on load if an API key exists
        if saved_key:
            self._load_models_to_dropdown()

    def _setup_ui(self, default_text: str, saved_key: str):
        self.Text = "AI Revit Agent - Structural Setup Dashboard"
        self.Size = Size(700, 600)
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.BackColor = SystemColors.Window

        # Row 1: API Key Setup
        self.lbl_api = Label()
        self.lbl_api.Text = "Gemini API Key:"
        self.lbl_api.Location = Point(15, 18)
        self.lbl_api.Size = Size(100, 20)
        self.lbl_api.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.lbl_api)

        self.txt_api = TextBox()
        self.txt_api.Size = Size(340, 25)
        self.txt_api.Location = Point(115, 15)
        self.txt_api.Text = saved_key
        self.txt_api.UseSystemPasswordChar = True  # Mask API Key input
        self.txt_api.Font = Font("Consolas", 9.5)
        self.Controls.Add(self.txt_api)

        self.btn_load_models = Button()
        self.btn_load_models.Text = "Load Models"
        self.btn_load_models.Size = Size(110, 28)
        self.btn_load_models.Location = Point(465, 13)
        self.btn_load_models.Font = Font("Segoe UI", 8.5)
        self.btn_load_models.Click += self._on_load_models_clicked
        self.Controls.Add(self.btn_load_models)

        # Row 2: Model Selection
        self.lbl_model = Label()
        self.lbl_model.Text = "Select Model:"
        self.lbl_model.Location = Point(15, 53)
        self.lbl_model.Size = Size(100, 20)
        self.lbl_model.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.lbl_model)

        self.cmb_models = ComboBox()
        self.cmb_models.Size = Size(460, 25)
        self.cmb_models.Location = Point(115, 50)
        # Fix: Explicitly assign .NET Enum ComboBoxStyle object to comply with Python.NET 3.0+
        self.cmb_models.DropDownStyle = ComboBoxStyle.DropDownList
        self.cmb_models.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.cmb_models)

        # Row 3: Design Brief multiline textbox
        self.lbl_brief = Label()
        self.lbl_brief.Text = "Describe your building level heights and grid spacing layout below:"
        self.lbl_brief.Location = Point(15, 95)
        self.lbl_brief.Size = Size(650, 20)
        self.lbl_brief.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.lbl_brief)

        self.txt_brief = TextBox()
        self.txt_brief.Multiline = True
        self.txt_brief.WordWrap = True
        self.txt_brief.ScrollBars = ScrollBars.Vertical
        self.txt_brief.Size = Size(655, 370)
        self.txt_brief.Location = Point(15, 120)
        self.txt_brief.Text = default_text
        self.txt_brief.Font = Font("Consolas", 9.5)
        self.Controls.Add(self.txt_brief)

        # Bottom Row Controls
        self.btn_build = Button()
        self.btn_build.Text = "Generate Structure"
        self.btn_build.Size = Size(140, 35)
        self.btn_build.Location = Point(380, 510)
        self.btn_build.DialogResult = DialogResult.OK
        self.btn_build.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.btn_build)

        self.btn_cancel = Button()
        self.btn_cancel.Text = "Cancel"
        self.btn_cancel.Size = Size(130, 35)
        self.btn_cancel.Location = Point(540, 510)
        self.btn_cancel.DialogResult = DialogResult.Cancel
        self.btn_cancel.Font = Font("Segoe UI", 9)
        self.Controls.Add(self.btn_cancel)

        self.AcceptButton = self.btn_build
        self.CancelButton = self.btn_cancel

    def _on_load_models_clicked(self, sender, event):
        self._load_models_to_dropdown()

    def _load_models_to_dropdown(self):
        api_key = self.txt_api.Text.strip()
        if not api_key:
            return

        self.cmb_models.Items.Clear()
        self.cmb_models.Items.Add("Connecting to API...")
        self.cmb_models.SelectedIndex = 0
        self.cmb_models.Update()

        try:
            # Query models from the API client callback
            models_list = self.fetch_models_func(api_key)
            self.cmb_models.Items.Clear()

            selected_idx = 0
            for idx, model in enumerate(models_list):
                self.cmb_models.Items.Add(model["id"])
                # Pre-select matching model
                if model["id"] == self.saved_model:
                    selected_idx = idx

            if self.cmb_models.Items.Count > 0:
                self.cmb_models.SelectedIndex = selected_idx
                
        except Exception as err:
            self.cmb_models.Items.Clear()
            # Setup static standard fallbacks if connection fails
            fallbacks = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash"]
            for f in fallbacks:
                self.cmb_models.Items.Add(f)
            self.cmb_models.SelectedIndex = 0
            print("Failed to dynamically fetch Gemini models, using fallbacks: {}".format(err))


class BIMMessageService:
    """Encapsulates all standard Revit task dialog operations."""

    @staticmethod
    def show_preview(report_text: str) -> bool:
        dialog = UI.TaskDialog("AI Revit Agent Preview")
        dialog.MainInstruction = "Do you want to apply these model changes?"
        dialog.MainContent = report_text
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
        dialog.DefaultButton = UI.TaskDialogResult.Yes
        return dialog.Show() == UI.TaskDialogResult.Yes

    @staticmethod
    def show_error(message: str):
        dialog = UI.TaskDialog("AI Revit Agent - Operational Error")
        dialog.MainInstruction = "Process Aborted"
        dialog.MainContent = message
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Ok
        dialog.Show()