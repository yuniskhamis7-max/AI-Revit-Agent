# -*- coding: utf-8 -*-
"""
Shared utilities and warning preprocessors for Revit Agent Bridge pushbutton.
"""

import clr
from Autodesk.Revit.DB import IFailuresPreprocessor, FailureProcessingResult, FailureSeverity

class WarningSwallower(IFailuresPreprocessor):
    """
    Failure preprocessor that automatically deletes Warning-level failures
    and rolls back transaction on Error-level failures to prevent modal popup dialogs
    from blocking the Revit UI thread.
    """
    last_error = None

    def PreprocessFailures(self, failuresAccessor):
        try:
            fail_list = failuresAccessor.GetFailureMessages()
            has_error = False
            error_msgs = []
            for failure in fail_list:
                severity = failure.GetSeverity()
                desc = failure.GetDescriptionText()
                if severity == FailureSeverity.Warning:
                    failuresAccessor.DeleteWarning(failure)
                elif severity == FailureSeverity.Error:
                    has_error = True
                    error_msgs.append(desc)
            
            if has_error:
                WarningSwallower.last_error = "; ".join(error_msgs)
                try:
                    opts = failuresAccessor.GetFailureHandlingOptions()
                    opts.SetClearAfterRollback(True)
                    failuresAccessor.SetFailureHandlingOptions(opts)
                except Exception:
                    pass
                return FailureProcessingResult.ProceedWithRollBack
        except Exception as ex:
            WarningSwallower.last_error = "Exception in FailurePreprocessor: " + str(ex)
        return FailureProcessingResult.Continue

def commit_transaction(trans):
    """
    Commits a transaction and checks its status.
    If the transaction was rolled back or is not committed, raises an Exception.
    Also appends the detailed failures preprocessor messages if available.
    """
    from Autodesk.Revit.DB import TransactionStatus
    status = trans.Commit()
    if status != TransactionStatus.Committed:
        err_msg = "Transaction failed with status: {}.".format(status)
        if WarningSwallower.last_error:
            err_msg = "{} Details: {}".format(err_msg, WarningSwallower.last_error)
            WarningSwallower.last_error = None
        raise Exception(err_msg)

def rollback_transaction(trans):
    """
    Safely rolls back a transaction, ignoring any exception if it's already ended or inactive.
    """
    try:
        if trans.HasStarted() and not trans.HasEnded():
            trans.RollBack()
    except Exception:
        try:
            trans.RollBack()
        except Exception:
            pass


# =====================================================================
# DETERMINISTIC UNIT CONVERSION
# =====================================================================

# Conversion factors to feet (Revit internal unit).
# All measurement tool inputs are normalised to feet before reaching the
# Revit API so that conversion is deterministic and never relies on the
# LLM performing arithmetic.
_TO_FEET = {
    "feet":       1.0,
    "ft":         1.0,
    "meters":     3.28084,
    "m":          3.28084,
    "millimeters": 0.00328084,
    "mm":         0.00328084,
    "centimeters": 0.0328084,
    "cm":         0.0328084,
    "inches":     0.0833333,
    "in":         0.0833333,
}

def convert_to_feet(value, unit):
    """
    Converts a numeric measurement to feet deterministically.

    Args:
        value (float or str): The numeric value to convert.
        unit  (str): The source unit — one of: feet, ft, meters, m,
                      millimeters, mm, centimeters, cm, inches, in.

    Returns:
        float: The value converted to feet, rounded to 6 decimal places.

    Raises:
        ValueError: If the unit string is not recognised.
    """
    v = float(value)
    u = str(unit).strip().lower()
    factor = _TO_FEET.get(u)
    if factor is None:
        raise ValueError(
            "Unknown unit '{}'. Supported: {}".format(unit, ", ".join(sorted(_TO_FEET.keys())))
        )
    return round(v * factor, 6)

def convert_dict_to_feet(d, keys, unit):
    """
    Converts multiple numeric keys in a dictionary from *unit* to feet.
    Missing or None keys are silently skipped.  Returns a new dict with
    the converted values (original dict is not mutated).

    Args:
        d    (dict):  Source dictionary.
        keys (list):  Key names whose values should be converted.
        unit (str):   The source unit string.

    Returns:
        dict: A shallow copy of *d* with the specified keys converted to feet.
    """
    out = dict(d)
    for k in keys:
        if k in out and out[k] is not None:
            out[k] = convert_to_feet(out[k], unit)
    return out

def convert_from_feet(value, unit):
    """
    Converts a numeric measurement from feet to target unit deterministically.

    Args:
        value (float or str): The value in feet to convert.
        unit  (str): The target unit — one of: feet, ft, meters, m,
                      millimeters, mm, centimeters, cm, inches, in.

    Returns:
        float: The value converted from feet, rounded to 6 decimal places.

    Raises:
        ValueError: If the unit string is not recognised.
    """
    v = float(value)
    u = str(unit).strip().lower()
    factor = _TO_FEET.get(u)
    if factor is None:
        raise ValueError(
            "Unknown unit '{}'. Supported: {}".format(unit, ", ".join(sorted(_TO_FEET.keys())))
        )
    return round(v / factor, 6)
