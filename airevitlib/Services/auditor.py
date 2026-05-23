# airevitlib/services/auditor.py
from core.models import CompiledProjectData
from revit.elements import StructuralManager
from services.compiler import DirectUnitCompiler

class ChangeAuditor:
    """Compares incoming compiled data against existing model elements to generate a report."""

    def __init__(self, data: CompiledProjectData, manager: StructuralManager):
        self.data = data
        self.manager = manager

    def compile_preview_report(self) -> str:
        lvl_new, lvl_upd = [], []
        grd_new, grd_upd = [], []

        src_unit = self.data.settings.source_units
        unit_label = src_unit.upper()
        scale_factor = DirectUnitCompiler.TO_FEET.get(src_unit, 1.0)

        for l in self.data.levels:
            target_h = round(l.elevation / scale_factor, 1)
            if self.manager.element_exists(l.id, l.name, "level"):
                current_ft = self.manager.get_existing_elevation(l.id, l.name)
                current_h = round(current_ft / scale_factor, 1) if current_ft is not None else 0.0
                lvl_upd.append(f" • {l.name} [{l.id}] ({current_h} -> {target_h} {unit_label})")
            else:
                lvl_new.append(f" • {l.name} [{l.id}] ({target_h} {unit_label})")

        for g in self.data.grids:
            if self.manager.element_exists(g.id, g.name, "grid"):
                grd_upd.append(f" • Grid {g.name} [{g.id}]")
            else:
                grd_new.append(f" • Grid {g.name} [{g.id}]")

        report = "AI BIM AGENT TRANSACTION PREVIEW\n"
        report += "==================================\n\n"
        report += f"Coordinate Origin: {self.data.settings.coordinate_system.upper()}\n"
        report += f"Target Units:      {unit_label}\n\n"

        report += f"LEVEL CHANGES ({len(lvl_new)} New, {len(lvl_upd)} Updates):\n"
        for item in lvl_new: 
            report += f"  [+] {item}\n"
        for item in lvl_upd: 
            report += f"  [*] {item}\n"

        report += f"\nGRID CHANGES ({len(grd_new)} New, {len(grd_upd)} Updates):\n"
        for item in grd_new: 
            report += f"  [+] {item}\n"
        for item in grd_upd: 
            report += f"  [*] {item}\n"

        return report