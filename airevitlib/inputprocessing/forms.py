# -*- coding: utf-8 -*-
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

import System.Windows.Forms as WinForms
import System.Drawing as Drawing

class BIMDoubleApprovalForm(WinForms.Form):
    def __init__(self, existing_elements, on_submit_callback, on_plan_approved_callback):
        super(BIMDoubleApprovalForm, self).__init__()
        self.existing_elements = existing_elements
        self.on_submit_callback = on_submit_callback
        self.on_plan_approved_callback = on_plan_approved_callback
        
        self.chat_history = []
        self.current_plan_data = None
        self.formatted_commands = None
        self.approved_commands = None
        
        self._build_layout()

    def _build_layout(self):
        self.Text = "Universal AI BIM Agent - Workspace Panel"
        self.Size = Drawing.Size(1200, 800)
        self.FormBorderStyle = WinForms.FormBorderStyle.FixedDialog
        self.StartPosition = WinForms.FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.BackColor = Drawing.Color.FromArgb(240, 242, 245)

        # 1. Left Conversation Pane
        self.panel_chat = WinForms.Panel()
        self.panel_chat.Location = Drawing.Point(20, 20)
        self.panel_chat.Size = Drawing.Size(550, 720)
        self.panel_chat.BackColor = Drawing.Color.White
        self.Controls.Add(self.panel_chat)

        self.lbl_chat = WinForms.Label()
        self.lbl_chat.Text = "CONVERSATIONAL CHAT LOG"
        self.lbl_chat.Font = Drawing.Font("Segoe UI", 9.5, Drawing.FontStyle.Bold)
        self.lbl_chat.Location = Drawing.Point(15, 15)
        self.lbl_chat.Size = Drawing.Size(300, 20)
        self.panel_chat.Controls.Add(self.lbl_chat)

        self.txt_chat_history = WinForms.TextBox()
        self.txt_chat_history.Multiline = True
        self.txt_chat_history.ReadOnly = True
        self.txt_chat_history.TabStop = False # Prevents automatic keyboard focus highlighting
        self.txt_chat_history.ScrollBars = WinForms.ScrollBars.Vertical
        self.txt_chat_history.Location = Drawing.Point(15, 45)
        self.txt_chat_history.Size = Drawing.Size(520, 500)
        self.txt_chat_history.Font = Drawing.Font("Segoe UI", 10.0)
        self.txt_chat_history.Text = "System: Live elements loaded. Awaiting structural instructions...\r\n\r\n"
        self.panel_chat.Controls.Add(self.txt_chat_history)

        self.txt_input = WinForms.TextBox()
        self.txt_input.Multiline = True
        self.txt_input.Location = Drawing.Point(15, 560)
        self.txt_input.Size = Drawing.Size(520, 85)
        self.txt_input.Font = Drawing.Font("Segoe UI", 10.5)
        self.panel_chat.Controls.Add(self.txt_input)

        self.btn_submit = WinForms.Button()
        self.btn_submit.Text = "Interpret Request"
        self.btn_submit.Location = Drawing.Point(355, 660)
        self.btn_submit.Size = Drawing.Size(180, 35)
        self.btn_submit.BackColor = Drawing.Color.FromArgb(50, 115, 220)
        self.btn_submit.ForeColor = Drawing.Color.White
        self.btn_submit.Font = Drawing.Font("Segoe UI", 9.5, Drawing.FontStyle.Bold)
        self.btn_submit.Click += self._on_submit_clicked
        self.panel_chat.Controls.Add(self.btn_submit)

        # 2. Right Double-Approval Workspace Pane
        self.panel_approval = WinForms.Panel()
        self.panel_approval.Location = Drawing.Point(595, 20)
        self.panel_approval.Size = Drawing.Size(570, 720)
        self.panel_approval.BackColor = Drawing.Color.White
        self.Controls.Add(self.panel_approval)

        self.lbl_gate1 = WinForms.Label()
        self.lbl_gate1.Text = "GATE 1: DETAILED DRAFTING PLAN"
        self.lbl_gate1.Font = Drawing.Font("Segoe UI", 9.5, Drawing.FontStyle.Bold)
        self.lbl_gate1.Location = Drawing.Point(20, 15)
        self.lbl_gate1.Size = Drawing.Size(350, 20)
        self.panel_approval.Controls.Add(self.lbl_gate1)

        self.txt_plan_display = WinForms.TextBox()
        self.txt_plan_display.Multiline = True
        self.txt_plan_display.ReadOnly = True
        self.txt_plan_display.TabStop = False # Prevents automatic keyboard focus highlighting
        self.txt_plan_display.ScrollBars = WinForms.ScrollBars.Vertical
        self.txt_plan_display.Location = Drawing.Point(20, 45)
        self.txt_plan_display.Size = Drawing.Size(530, 260)
        self.txt_plan_display.Font = Drawing.Font("Consolas", 9.5)
        self.panel_approval.Controls.Add(self.txt_plan_display)

        self.btn_approve_plan = WinForms.Button()
        self.btn_approve_plan.Text = "Approve Drafting Plan (Gate 1)"
        self.btn_approve_plan.Location = Drawing.Point(20, 315)
        self.btn_approve_plan.Size = Drawing.Size(530, 35)
        self.btn_approve_plan.BackColor = Drawing.Color.FromArgb(235, 150, 40)
        self.btn_approve_plan.ForeColor = Drawing.Color.White
        self.btn_approve_plan.Font = Drawing.Font("Segoe UI", 9.5, Drawing.FontStyle.Bold)
        self.btn_approve_plan.Enabled = False
        self.btn_approve_plan.Click += self._on_approve_plan_clicked
        self.panel_approval.Controls.Add(self.btn_approve_plan)

        self.lbl_gate2 = WinForms.Label()
        self.lbl_gate2.Text = "GATE 2: DIRECT TRANSACTION INSTRUCTIONS"
        self.lbl_gate2.Font = Drawing.Font("Segoe UI", 9.5, Drawing.FontStyle.Bold)
        self.lbl_gate2.Location = Drawing.Point(20, 375)
        self.lbl_gate2.Size = Drawing.Size(350, 20)
        self.panel_approval.Controls.Add(self.lbl_gate2)

        self.txt_commands_display = WinForms.TextBox()
        self.txt_commands_display.Multiline = True
        self.txt_commands_display.ReadOnly = True
        self.txt_commands_display.TabStop = False # Prevents automatic keyboard focus highlighting
        self.txt_commands_display.ScrollBars = WinForms.ScrollBars.Vertical
        self.txt_commands_display.Location = Drawing.Point(20, 405)
        self.txt_commands_display.Size = Drawing.Size(530, 235)
        self.txt_commands_display.Font = Drawing.Font("Consolas", 9.0)
        self.panel_approval.Controls.Add(self.txt_commands_display)

        self.btn_execute = WinForms.Button()
        self.btn_execute.Text = "Confirm & Apply to Revit (Gate 2)"
        self.btn_execute.Location = Drawing.Point(20, 655)
        self.btn_execute.Size = Drawing.Size(530, 45)
        self.btn_execute.BackColor = Drawing.Color.FromArgb(40, 160, 80)
        self.btn_execute.ForeColor = Drawing.Color.White
        self.btn_execute.Font = Drawing.Font("Segoe UI", 10.5, Drawing.FontStyle.Bold)
        self.btn_execute.Enabled = False
        self.btn_execute.Click += self._on_execute_clicked
        self.panel_approval.Controls.Add(self.btn_execute)

        # FORCE initial keyboard focus directly to user input box
        self.ActiveControl = self.txt_input

    def _on_submit_clicked(self, sender, event):
        user_input = self.txt_input.Text.strip()
        if not user_input:
            return

        self.txt_chat_history.AppendText("User: {}\r\n\r\n".format(user_input))
        self.txt_input.Clear()
        self.btn_submit.Enabled = False
        self.txt_chat_history.AppendText("Agent: Processing drafting logic...\r\n")
        self.Update()

        self.chat_history.append({"role": "user", "text": user_input})

        try:
            response = self.on_submit_callback(user_input, self.chat_history)
            self._process_organizer_response(response)
        except Exception as ex:
            self.txt_chat_history.AppendText("System Error: {}\r\n\r\n".format(ex))
        finally:
            self.btn_submit.Enabled = True
            self.ActiveControl = self.txt_input # Keep input focus active after submit

    def _process_organizer_response(self, response):
        if response.get("status") == "missing_details_query" and response.get("missing_details_query"):
            query_msg = response["missing_details_query"]
            self.txt_chat_history.AppendText("Agent: {}\r\n\r\n".format(query_msg))
            self.btn_approve_plan.Enabled = False
            self.txt_plan_display.Clear()
            self.chat_history.append({"role": "model", "text": query_msg})
        else:
            plan = response.get("detailed_drafting_plan", {})
            self.current_plan_data = plan
            summary = plan.get("summary", "No summary provided.")
            self.chat_history.append({"role": "model", "text": summary})
            
            plan_text = "SUMMARY:\r\n{}\r\n\r\n".format(summary)
            plan_text += "========================================\r\n"
            plan_text += "PROPOSED DRAFTING STEPS:\r\n"
            plan_text += "========================================\r\n\r\n"
            
            for step in plan.get("steps", []):
                plan_text += "STEP {}: [{}] Category: {}\r\n".format(
                    step.get("step_number"), 
                    str(step.get("action")).upper(),
                    str(step.get("category")).upper()
                )
                plan_text += "  • Target Element: {}\r\n".format(step.get("target", "Unspecified"))
                plan_text += "  • Drafting Logic: {}\r\n".format(step.get("reasoning", ""))
                plan_text += "----------------------------------------\r\n\r\n"
                
            self.txt_plan_display.Text = plan_text
            self.txt_chat_history.AppendText("Agent: Plan formulated successfully. See Workspace Panel.\r\n\r\n")
            self.btn_approve_plan.Enabled = True

    def _on_approve_plan_clicked(self, sender, event):
        self.btn_approve_plan.Enabled = False
        self.txt_chat_history.AppendText("System: Plan approved. Compiling strict coordinates...\r\n")
        self.Update()

        try:
            formatted = self.on_plan_approved_callback(self.current_plan_data)
            self.formatted_commands = formatted.get("instructions", [])
            
            import json
            raw_json = json.dumps(formatted, indent=4)
            self.txt_commands_display.Text = raw_json.replace("\n", "\r\n")
            
            self.btn_execute.Enabled = len(self.formatted_commands) > 0
            self.txt_chat_history.AppendText("System: API Commands generated. Please perform final verify check.\r\n\r\n")
        except Exception as ex:
            self.txt_chat_history.AppendText("System Compilation Error: {}\r\n\r\n".format(ex))
            self.btn_approve_plan.Enabled = True
        finally:
            self.ActiveControl = self.txt_input

    def _on_execute_clicked(self, sender, event):
        self.approved_commands = self.formatted_commands
        self.DialogResult = WinForms.DialogResult.OK
        self.Close()