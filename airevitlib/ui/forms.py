# airevitlib/ui/forms.py
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

import System.Windows.Forms as WinForms
import System.Drawing as Drawing
import Autodesk.Revit.UI as UI

class BIMConversationalDashboard(WinForms.Form):
    """An interop-safe conversational dashboard with strictly typed .NET Fonts and clean inputs."""
    
    def __init__(self, saved_key: str, saved_model: str, fetch_models_func, on_query_callback):
        super(BIMConversationalDashboard, self).__init__()
        self.fetch_models_func = fetch_models_func
        self.on_query_callback = on_query_callback
        self.saved_model = saved_model
        self.conversation_history = []
        self.validated_payload = None
        
        self._build_interface(saved_key)
        self._initialize_history()

    def _build_interface(self, saved_key: str):
        # 1. Main Form Settings
        self.Text = "Conversational BIM Setup Dashboard"
        self.Size = Drawing.Size(950, 650)
        self.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        self.StartPosition = WinForms.FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.BackColor = Drawing.Color.FromArgb(245, 246, 248)

        # 2. Configuration Top Bar Controls
        self.lbl_api = WinForms.Label()
        self.lbl_api.Text = "API Key:"
        self.lbl_api.Location = Drawing.Point(20, 18)
        self.lbl_api.Size = Drawing.Size(60, 20)
        self.lbl_api.Font = Drawing.Font("Segoe UI", 9.0)
        self.Controls.Add(self.lbl_api)

        self.txt_api = WinForms.TextBox()
        self.txt_api.Location = Drawing.Point(80, 15)
        self.txt_api.Size = Drawing.Size(250, 23)
        self.txt_api.Text = saved_key
        self.txt_api.UseSystemPasswordChar = True
        self.Controls.Add(self.txt_api)

        self.cmb_models = WinForms.ComboBox()
        self.cmb_models.Location = Drawing.Point(350, 15)
        self.cmb_models.Size = Drawing.Size(180, 23)
        self.cmb_models.DropDownStyle = WinForms.ComboBoxStyle.DropDownList
        self.Controls.Add(self.cmb_models)

        self.btn_load_models = WinForms.Button()
        self.btn_load_models.Text = "Fetch Models"
        self.btn_load_models.Location = Drawing.Point(540, 14)
        self.btn_load_models.Size = Drawing.Size(100, 25)
        self.btn_load_models.Click += self._on_fetch_clicked
        self.Controls.Add(self.btn_load_models)

        # 3. Left Panel: Conversational Workspace
        self.panel_chat = WinForms.Panel()
        self.panel_chat.Location = Drawing.Point(20, 55)
        self.panel_chat.Size = Drawing.Size(540, 530)
        self.panel_chat.BackColor = Drawing.Color.White
        self.Controls.Add(self.panel_chat)

        self.txt_chat_history = WinForms.TextBox()
        self.txt_chat_history.Location = Drawing.Point(10, 10)
        self.txt_chat_history.Size = Drawing.Size(520, 360)
        self.txt_chat_history.Multiline = True
        self.txt_chat_history.ReadOnly = True
        self.txt_chat_history.ScrollBars = WinForms.ScrollBars.Vertical
        self.txt_chat_history.Font = Drawing.Font("Segoe UI", 10.0)
        self.txt_chat_history.BackColor = Drawing.Color.FromArgb(250, 250, 250)
        self.panel_chat.Controls.Add(self.txt_chat_history)

        self.txt_user_input = WinForms.TextBox()
        self.txt_user_input.Location = Drawing.Point(10, 385)
        self.txt_user_input.Size = Drawing.Size(520, 95)
        self.txt_user_input.Multiline = True
        self.txt_user_input.ScrollBars = WinForms.ScrollBars.Vertical
        self.txt_user_input.Font = Drawing.Font("Segoe UI", 10.5)
        self.txt_user_input.Text = ""  # Explicitly starts empty with no templates loaded
        self.panel_chat.Controls.Add(self.txt_user_input)

        self.btn_send = WinForms.Button()
        self.btn_send.Text = "Submit Request"
        self.btn_send.Location = Drawing.Point(380, 490)
        self.btn_send.Size = Drawing.Size(150, 30)
        self.btn_send.BackColor = Drawing.Color.FromArgb(50, 120, 220)
        self.btn_send.ForeColor = Drawing.Color.White
        self.btn_send.Font = Drawing.Font("Segoe UI", 9.0, Drawing.FontStyle.Bold)
        self.btn_send.Click += self._on_submit_clicked
        self.panel_chat.Controls.Add(self.btn_send)

        # 4. Right Panel: Building Metrics & Transaction Output
        self.panel_preview = WinForms.Panel()
        self.panel_preview.Location = Drawing.Point(580, 55)
        self.panel_preview.Size = Drawing.Size(330, 530)
        self.panel_preview.BackColor = Drawing.Color.White
        self.Controls.Add(self.panel_preview)

        self.lbl_kpi_title = WinForms.Label()
        self.lbl_kpi_title.Text = "ESTIMATED FOOTPRINT KPIs"
        self.lbl_kpi_title.Location = Drawing.Point(15, 15)
        self.lbl_kpi_title.Size = Drawing.Size(300, 20)
        self.lbl_kpi_title.Font = Drawing.Font("Segoe UI", 10.0, Drawing.FontStyle.Bold)
        self.lbl_kpi_title.ForeColor = Drawing.Color.FromArgb(70, 80, 95)
        self.panel_preview.Controls.Add(self.lbl_kpi_title)

        self.lbl_length = WinForms.Label()
        self.lbl_length.Text = "Building Length (X):  --"
        self.lbl_length.Location = Drawing.Point(15, 45)
        self.lbl_length.Size = Drawing.Size(300, 20)
        self.lbl_length.Font = Drawing.Font("Segoe UI", 9.5)
        self.panel_preview.Controls.Add(self.lbl_length)

        self.lbl_width = WinForms.Label()
        self.lbl_width.Text = "Building Width (Y):   --"
        self.lbl_width.Location = Drawing.Point(15, 70)
        self.lbl_width.Size = Drawing.Size(300, 20)
        self.lbl_width.Font = Drawing.Font("Segoe UI", 9.5)
        self.panel_preview.Controls.Add(self.lbl_width)

        self.lbl_height = WinForms.Label()
        self.lbl_height.Text = "Building Height (Z):  --"
        self.lbl_height.Location = Drawing.Point(15, 95)
        self.lbl_height.Size = Drawing.Size(300, 20)
        self.lbl_height.Font = Drawing.Font("Segoe UI", 9.5)
        self.panel_preview.Controls.Add(self.lbl_height)

        self.lbl_area = WinForms.Label()
        self.lbl_area.Text = "Est. Footprint Area:  --"
        self.lbl_area.Location = Drawing.Point(15, 120)
        self.lbl_area.Size = Drawing.Size(300, 20)
        self.lbl_area.Font = Drawing.Font("Segoe UI", 9.5)
        self.panel_preview.Controls.Add(self.lbl_area)

        self.lbl_actions_title = WinForms.Label()
        self.lbl_actions_title.Text = "PROPOSED TRANSACTION LOG"
        self.lbl_actions_title.Location = Drawing.Point(15, 160)
        self.lbl_actions_title.Size = Drawing.Size(300, 20)
        self.lbl_actions_title.Font = Drawing.Font("Segoe UI", 10.0, Drawing.FontStyle.Bold)
        self.lbl_actions_title.ForeColor = Drawing.Color.FromArgb(70, 80, 95)
        self.panel_preview.Controls.Add(self.lbl_actions_title)

        self.lst_actions = WinForms.ListBox()
        self.lst_actions.Location = Drawing.Point(15, 190)
        self.lst_actions.Size = Drawing.Size(300, 240)
        self.lst_actions.Font = Drawing.Font("Consolas", 8.5)
        self.panel_preview.Controls.Add(self.lst_actions)

        self.btn_execute = WinForms.Button()
        self.btn_execute.Text = "Approve & Apply to Revit"
        self.btn_execute.Location = Drawing.Point(15, 480)
        self.btn_execute.Size = Drawing.Size(300, 38)
        self.btn_execute.BackColor = Drawing.Color.FromArgb(40, 160, 90)
        self.btn_execute.ForeColor = Drawing.Color.White
        self.btn_execute.Font = Drawing.Font("Segoe UI", 10.0, Drawing.FontStyle.Bold)
        self.btn_execute.Enabled = False
        self.btn_execute.DialogResult = WinForms.DialogResult.OK
        self.panel_preview.Controls.Add(self.btn_execute)

        if saved_key:
            self._fetch_models()

    def _initialize_history(self):
        self.txt_chat_history.AppendText("AI Assistant: Send a message to inspect the current Revit layout.\r\n\r\n")

    def _on_fetch_clicked(self, sender, event):
        self._fetch_models()

    def _fetch_models(self):
        key = self.txt_api.Text.strip()
        if not key: return
        try:
            items = self.fetch_models_func(key)
            self.cmb_models.Items.Clear()
            idx = 0
            for i, val in enumerate(items):
                self.cmb_models.Items.Add(val["id"])
                if val["id"] == self.saved_model: idx = i
            if self.cmb_models.Items.Count > 0:
                self.cmb_models.SelectedIndex = idx
        except Exception:
            self.cmb_models.Items.Clear()
            for val in ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-pro"]:
                self.cmb_models.Items.Add(val)
            self.cmb_models.SelectedIndex = 0

    def _on_submit_clicked(self, sender, event):
        user_input = self.txt_user_input.Text.strip()
        if not user_input: return

        self.txt_chat_history.AppendText(f"User: {user_input}\r\n\r\n")
        self.txt_user_input.Clear()
        self.btn_send.Enabled = False
        self.txt_chat_history.AppendText("Processing layout verification...\r\n")
        self.Update()

        api_key = self.txt_api.Text.strip()
        selected_model = str(self.cmb_models.SelectedItem or "gemini-flash-lite-latest")
        
        try:
            response_payload = self.on_query_callback(user_input, api_key, selected_model)
            self._render_ai_response(response_payload)
        except Exception as e:
            self.txt_chat_history.AppendText(f"AI Assistant Error: {e}\r\n\r\n")
        finally:
            self.btn_send.Enabled = True

    def _render_ai_response(self, payload: dict):
        self.txt_chat_history.AppendText(f"AI Assistant: {payload.get('clarification_message')}\r\n\r\n")
        
        # Display dynamic metrics using defensive formatting
        kpis = payload.get("kpis") or {}
        
        def safe_format(val) -> str:
            if val is None:
                return "0.0"
            try:
                return f"{float(val):.1f}"
            except (ValueError, TypeError):
                return "0.0"

        self.lbl_length.Text = f"Building Length (X):  {safe_format(kpis.get('total_length_m'))} m"
        self.lbl_width.Text  = f"Building Width (Y):   {safe_format(kpis.get('total_width_m'))} m"
        self.lbl_height.Text = f"Building Height (Z):  {safe_format(kpis.get('total_height_m'))} m"
        self.lbl_area.Text   = f"Est. Footprint Area:  {safe_format(kpis.get('footprint_area_sqm'))} sqm"

        # Update action logs
        self.lst_actions.Items.Clear()
        delta = payload.get("proposed_delta") or {}

        # Parse Level actions with absolute schema safety
        levels_section = delta.get("levels") or {}
        for l in levels_section.get("create") or []:
            if isinstance(l, dict):
                name = l.get('name', '?')
                elev = l.get('elevation', 0.0)
                self.lst_actions.Items.Add(f"[+] LVL: Create {name} @ {elev}m")
        for l in levels_section.get("update") or []:
            if isinstance(l, dict):
                name = l.get('name', '?')
                elev = l.get('elevation', 0.0)
                self.lst_actions.Items.Add(f"[*] LVL: Update {name} @ {elev}m")
        for l in levels_section.get("delete") or []:
            self.lst_actions.Items.Add(f"[-] LVL: Delete {l}")

        # Parse Grid actions with absolute schema safety (resolves the 'axis' KeyError)
        grids_section = delta.get("grids") or {}
        for g in grids_section.get("create") or []:
            if isinstance(g, dict):
                axis = g.get('axis', '?')
                name = g.get('name', '?')
                pos = g.get('position', 0.0)
                self.lst_actions.Items.Add(f"[+] GRD: Create Axis {axis}-{name} @ {pos}m")
        for g in grids_section.get("update") or []:
            if isinstance(g, dict):
                axis = g.get('axis', '?')
                name = g.get('name', '?')
                pos = g.get('position', 0.0)
                self.lst_actions.Items.Add(f"[*] GRD: Update Axis {axis}-{name} @ {pos}m")
        for g in grids_section.get("delete") or []:
            self.lst_actions.Items.Add(f"[-] GRD: Delete {g}")

        # Enable/disable button based on validation status
        self.btn_execute.Enabled = bool(payload.get("is_valid", False))
        self.validated_payload = payload


class BIMMessageService:
    @staticmethod
    def show_error(message: str):
        dialog = UI.TaskDialog("AI Revit Agent - Setup Blocked")
        dialog.MainInstruction = "Operation Aborted"
        dialog.MainContent = message
        dialog.CommonButtons = UI.TaskDialogCommonButtons.Ok
        dialog.Show()