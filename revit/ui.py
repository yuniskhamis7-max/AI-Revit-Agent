"""Direct pyRevit UI interactions."""

from pyrevit import forms


def show_loaded_message():
    """Show the phase-one startup validation message in Revit."""
    forms.alert("AI Revit Agent Loaded")
