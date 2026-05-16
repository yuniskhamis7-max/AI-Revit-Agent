"""Direct Revit transaction helpers.

Transactions are centralized here so Revit API write operations share the same
commit and rollback behavior without leaking orchestration into Revit modules.
"""

from Autodesk.Revit.DB import Transaction, TransactionStatus


def run_in_transaction(document, name, action):
    """Run a small Revit write action inside a transaction."""
    transaction = Transaction(document, name)

    try:
        transaction.Start()
        result = action()
        transaction.Commit()
        return result
    except Exception as error:
        if transaction.GetStatus() == TransactionStatus.Started:
            transaction.RollBack()
        return {
            "success": False,
            "message": str(error),
            "element_id": None,
        }
