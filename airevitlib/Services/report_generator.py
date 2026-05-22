# airevitlib/services/report_generator.py
from payload_manager import PayloadManager

class DryRunReportService:
    """Generates human-readable transaction summaries comparing payload to existing model state."""

    @staticmethod
    def generate_report(project_data, level_manager, grid_manager) -> str:
        levels_to_create = []
        levels_to_update = []
        grids_to_create = []
        grids_to_update = []

        l_unit = project_data.settings.levels_unit
        g_unit = project_data.settings.grids_unit
        l_mult = PayloadManager.UNIT_MULTIPLIERS.get(l_unit.lower(), 1.0)

        # Audit Levels
        for l_data in project_data.levels:
            display_elev = round(l_data.elevation / l_mult, 1)
            existing = level_manager._level_cache.get(l_data.id) or level_manager._level_cache.get(l_data.name)
            if existing:
                existing_val = round(existing.Elevation / l_mult, 1)
                levels_to_update.append("• {} [ID: {}] ({} -> {} {})".format(
                    l_data.name, l_data.id, existing_val, display_elev, l_unit
                ))
            else:
                levels_to_create.append("• {} [ID: {}] ({} {})".format(
                    l_data.name, l_data.id, display_elev, l_unit
                ))

        # Audit Grids
        for g_data in project_data.grids:
            existing = grid_manager._grid_cache.get(g_data.id) or grid_manager._grid_cache.get(g_data.name)
            if existing:
                grids_to_update.append("• Grid {} [ID: {}]".format(g_data.name, g_data.id))
            else:
                grids_to_create.append("• Grid {} [ID: {}]".format(g_data.name, g_data.id))

        # Build output string
        report = "AI AGENT TRANSACTION PREVIEW\n"
        report += "==================================\n\n"
        report += "Coordinate Origin: {}\n".format(project_data.settings.coordinate_system.upper())
        report += "Unit Profiles:     Levels: {} | Grids: {}\n\n".format(l_unit.upper(), g_unit.upper())
        
        report += "LEVEL CHANGES ({} New, {} Update):\n".format(len(levels_to_create), len(levels_to_update))
        for item in levels_to_create: 
            report += "  [+] Create {}\n".format(item)
        for item in levels_to_update: 
            report += "  [*] Update {}\n".format(item)
        
        report += "\nGRID CHANGES ({} New, {} Update):\n".format(len(grids_to_create), len(grids_to_update))
        for item in grids_to_create: 
            report += "  [+] Create {}\n".format(item)
        for item in grids_to_update: 
            report += "  [*] Update {}\n".format(item)
        
        return report