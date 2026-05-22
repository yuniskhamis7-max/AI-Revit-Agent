{
  "project_name": "Multi-Use Tower",
  "units": "mm",
  "coordinate_system": "project_base_point",
  "levels": [
    { "name": "B2 - Foundation Slab", "height_from_previous": -3600.0, "create_floor_plan": false },
    { "name": "B1 - Parking Garage", "height_from_previous": 3600.0, "create_floor_plan": true },
    { "name": "L0 - Entrance Lobby", "height_from_previous": 3600.0, "create_floor_plan": true },
    { "name": "L1 - Retail Mezzanine", "height_from_previous": 4800.0, "create_floor_plan": true }
  ],
  "grids": {
    "x_axis": {
      "prefix": "",
      "bays": [
        { "label": "1", "spacing_to_next": 6000.0 },
        { "label": "2", "spacing_to_next": 8000.0 },
        { "label": "3", "spacing_to_next": 8000.0 },
        { "label": "4", "spacing_to_next": 6000.0 },
        { "label": "5", "spacing_to_next": 9000.0 },
        { "label": "6", "spacing_to_next": 0.0 }
      ]
    },
    "y_axis": {
      "prefix": "Letter",
      "bays": [
        { "label": "A", "spacing_to_next": 7500.0 },
        { "label": "B", "spacing_to_next": 7500.0 },
        { "label": "C", "spacing_to_next": 6000.0 },
        { "label": "D", "spacing_to_next": 8500.0 },
        { "label": "E", "spacing_to_next": 8500.0 },
        { "label": "F", "spacing_to_next": 0.0 }
      ]
    }
  }
}