# -*- coding: utf-8 -*-
import requests, json
r = requests.post('http://127.0.0.1:8080/execute/', json={'tool':'fetch_grids','input':{}}, timeout=120)
data = r.json()
grids = data.get('grids', [])
print("Total grids in Revit:", len(grids))
for g in grids:
    print("  - {}: ({:.1f},{:.1f}) -> ({:.1f},{:.1f})".format(
        g["name"], g["start_x"], g["start_y"], g["end_x"], g["end_y"]))
