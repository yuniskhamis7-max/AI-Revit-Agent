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


