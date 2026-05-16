"""Direct pyRevit UI interactions.

The UI layer gives users visibility and approval before structured payloads are
executed. It never performs Revit API write operations.
"""

import os

from pyrevit import forms


def show_loaded_message():
    """Show the phase-one startup validation message in Revit."""
    forms.alert("AI Revit Agent Loaded")


def confirm_demo_workflow():
    """Ask the user before creating deterministic demo BIM elements."""
    return forms.alert(
        "Create one test level and one test grid?",
        title="AI Revit Agent",
        ok=True,
        cancel=True,
    )


def select_payload_file(paths):
    """Let the user select a payload JSON file."""
    if not paths:
        forms.alert("No payload JSON files were found.", title="AI Revit Agent")
        return None

    names = [os.path.basename(path) for path in paths]
    selected = forms.SelectFromList.show(names, title="Select Payload File")
    if not selected:
        return None

    return paths[names.index(selected)]


def preview_payload_text(text):
    """Show the payload before execution."""
    forms.alert(
        "Review the payload before execution.",
        title="AI Revit Agent Payload Preview",
        expanded=text,
    )


def confirm_payload_edit():
    """Ask whether the user wants to edit the payload JSON text."""
    return forms.alert(
        "Edit payload JSON before validation?",
        title="AI Revit Agent",
        yes=True,
        no=True,
    )


def edit_payload_text(text):
    """Open a large multiline editor for payload JSON."""
    window = PayloadEditorWindow(text)
    window.ShowDialog()
    return window.result_text


def confirm_payload_execution():
    """Require explicit approval before runtime execution."""
    return forms.alert(
        "Execute the validated payload workflow?",
        title="AI Revit Agent",
        ok=True,
        cancel=True,
    )


def show_validation_errors(results):
    """Display validation failures before execution."""
    forms.alert(
        "Payload validation failed.",
        title="AI Revit Agent",
        expanded=_format_results(results),
    )


def show_execution_result(result):
    """Display structured execution results after workflow execution."""
    forms.alert(
        result["message"],
        title="AI Revit Agent Results",
        expanded=_format_results(result.get("results", [])),
    )


def _format_results(results):
    """Format structured results for pyRevit alert expansion text."""
    if not results:
        return "No results."

    lines = []
    for index, result in enumerate(results, start=1):
        lines.append("{}. {}".format(index, result.get("action") or "payload"))
        lines.append("   success: {}".format(result.get("success")))
        lines.append("   message: {}".format(result.get("message")))
        lines.append("   error: {}".format(result.get("error")))
        lines.append("   element_ids: {}".format(result.get("element_ids")))
    return "\n".join(lines)


class PayloadEditorWindow(forms.WPFWindow):
    """Large pyRevit WPF editor for reviewing and editing JSON payload text."""

    def __init__(self, text):
        forms.WPFWindow.__init__(self, PAYLOAD_EDITOR_XAML, literal_string=True)
        self.result_text = None
        self.payload_text.Text = text
        self.payload_text.Focus()

    def save_clicked(self, sender, args):
        """Return edited text to the runtime layer."""
        self.result_text = self.payload_text.Text
        self.Close()

    def cancel_clicked(self, sender, args):
        """Cancel editing without returning payload text."""
        self.result_text = None
        self.Close()


PAYLOAD_EDITOR_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Edit Payload JSON"
        Width="900"
        Height="650"
        MinWidth="700"
        MinHeight="450"
        WindowStartupLocation="CenterScreen"
        ResizeMode="CanResize">
    <Grid Margin="12">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <TextBlock Grid.Row="0"
                   Text="Review or edit the JSON payload before validation."
                   Margin="0,0,0,8"/>

        <TextBox Grid.Row="1"
                 x:Name="payload_text"
                 AcceptsReturn="True"
                 AcceptsTab="True"
                 VerticalScrollBarVisibility="Auto"
                 HorizontalScrollBarVisibility="Auto"
                 TextWrapping="NoWrap"
                 FontFamily="Consolas"
                 FontSize="13"
                 Padding="8"/>

        <StackPanel Grid.Row="2"
                    Orientation="Horizontal"
                    HorizontalAlignment="Right"
                    Margin="0,10,0,0">
            <Button Content="Cancel"
                    Width="90"
                    Height="30"
                    Margin="0,0,8,0"
                    Click="cancel_clicked"/>
            <Button Content="Use Payload"
                    Width="110"
                    Height="30"
                    Click="save_clicked"/>
        </StackPanel>
    </Grid>
</Window>
"""
