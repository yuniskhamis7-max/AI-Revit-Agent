"""Direct pyRevit UI interactions.

The UI asks for instructions, previews structured payloads, and asks for user
approval. It never creates elements or changes transactions.
"""

from pyrevit import forms, revit


def get_active_document():
    """Return the active Revit document for the current pyRevit command."""
    return revit.doc


def ask_for_instruction():
    """Open a simple editor for natural-language BIM drafting instructions."""
    window = TextEditorWindow(
        "Enter BIM Instruction",
        "Describe the levels, grids, or columns to draft.",
        "Create two levels named Level 1 and Level 2 spaced 4000 mm apart",
        "Generate Payload",
    )
    window.ShowDialog()
    return window.result_text


def preview_payload_text(text):
    """Show the AI-generated payload before deterministic execution."""
    forms.alert(
        "Review the structured payload before execution.",
        title="AI BIM Payload Preview",
        expanded=text,
    )


def confirm_payload_execution(category):
    """Require explicit approval before the selected category executes."""
    return forms.alert(
        "Execute only the {} section of this payload?".format(category),
        title="AI BIM Drafting",
        ok=True,
        cancel=True,
    )


def show_validation_errors(results):
    """Display validation failures before execution."""
    forms.alert(
        "Payload validation failed.",
        title="AI BIM Drafting",
        expanded=_format_results(results),
    )


def show_execution_result(result):
    """Display structured execution results."""
    forms.alert(
        result["message"],
        title="AI BIM Drafting Results",
        expanded=_format_results(result.get("results", [])),
    )


def _format_results(results):
    """Format validation and execution results for pyRevit alerts."""
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


class TextEditorWindow(forms.WPFWindow):
    """Large pyRevit WPF editor for instruction text."""

    def __init__(self, title, prompt, text, accept_label):
        forms.WPFWindow.__init__(self, TEXT_EDITOR_XAML, literal_string=True)
        self.result_text = None
        self.Title = title
        self.prompt_text.Text = prompt
        self.text_input.Text = text
        self.accept_button.Content = accept_label
        self.text_input.Focus()

    def save_clicked(self, sender, args):
        """Return entered text."""
        self.result_text = self.text_input.Text
        self.Close()

    def cancel_clicked(self, sender, args):
        """Cancel without returning text."""
        self.result_text = None
        self.Close()


TEXT_EDITOR_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Width="900"
        Height="520"
        MinWidth="700"
        MinHeight="360"
        WindowStartupLocation="CenterScreen"
        ResizeMode="CanResize">
    <Grid Margin="12">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <TextBlock Grid.Row="0"
                   x:Name="prompt_text"
                   Margin="0,0,0,8"/>

        <TextBox Grid.Row="1"
                 x:Name="text_input"
                 AcceptsReturn="True"
                 AcceptsTab="True"
                 VerticalScrollBarVisibility="Auto"
                 HorizontalScrollBarVisibility="Auto"
                 TextWrapping="Wrap"
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
            <Button x:Name="accept_button"
                    Width="140"
                    Height="30"
                    Click="save_clicked"/>
        </StackPanel>
    </Grid>
</Window>
"""
