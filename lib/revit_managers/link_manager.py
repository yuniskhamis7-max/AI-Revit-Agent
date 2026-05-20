import Autodesk.Revit.DB as DB

class LinkManager:
    """Dedicated class for handling operations with Revit Links."""
    
    def __init__(self, doc: DB.Document):
        self.doc = doc

    def get_link_instance(self, link_name: str) -> DB.RevitLinkInstance:
        links = DB.FilteredElementCollector(self.doc).OfClass(DB.RevitLinkInstance).ToElements()
        return next((L for L in links if link_name.lower() in L.Name.lower()), None)

    def copy_elements(self, link_name: str, db_class, prefix: str = "") -> list:
        """Generic method to copy any class of elements from a link."""
        target_link = self.get_link_instance(link_name)
        if not target_link:
            print(f"❌ Link '{link_name}' not found.")
            return []

        link_doc = target_link.GetLinkDocument()
        linked_elements = DB.FilteredElementCollector(link_doc).OfClass(db_class).WhereElementIsNotElementType().ToElements()
        
        element_ids = [e.Id for e in linked_elements]
        if not element_ids: 
            return []

        transform = target_link.GetTotalTransform()
        options = DB.CopyPasteOptions()
        copied_ids = DB.ElementTransformUtils.CopyElements(
            link_doc, 
            DB.List[DB.ElementId](element_ids), 
            self.doc, 
            transform, 
            options
        )
        
        copied_elements = []
        for c_id in copied_ids:
            element = self.doc.GetElement(c_id)
            if prefix and hasattr(element, "Name"):
                try: 
                    element.Name = f"{prefix}{element.Name}"
                except: 
                    pass
            copied_elements.append(element)
            
        return copied_elements

    def copy_grids(self, link_name: str, prefix: str = "") -> list:
        return self.copy_elements(link_name, DB.Grid, prefix)

    def copy_levels(self, link_name: str, prefix: str = "") -> list:
        return self.copy_elements(link_name, DB.Level, prefix)