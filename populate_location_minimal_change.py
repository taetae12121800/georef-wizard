# coding: utf-8
# ============================================================
# POPULATE LOCATION WITH DIRECTION
# Description: Uses Generate Near Table to find the closest
# EG_MAD address within 300 ft, then populates LOCATION as
# "street, direction + address"
# (e.g. "Bond RD, W/O 8765 Elk Grove Blvd") using NEAR_FID for
# the address, NEAR_ANGLE for direction, and a second near
# table against GIS.EG_STREETS for the street name.
# No joins - no field name corruption.
# ============================================================

import arcpy
import tkinter as tk
from tkinter import ttk, messagebox

aprx = arcpy.mp.ArcGISProject("CURRENT")
map_obj = aprx.activeMap

def get_layer_path(map_obj):
    paths = {}
    for l in map_obj.listLayers():
        if l.isFeatureLayer:
            paths[l.longName] = l.longName
    return paths

layer_list = list(get_layer_path(map_obj).keys())

def angle_to_direction(angle):
    if angle is None:
        return "Unknown"
    if 45 <= angle <= 135:
        return "S/O"
    elif -45 <= angle < 45:
        return "W/O"
    elif -135 <= angle < -45:
        return "N/O"
    else:
        return "E/O"

# -- Build the Popup UI --------------------------------------
root = tk.Tk()
root.title("Populate LOCATION with Direction")
root.geometry("500x150")

tk.Label(root, text="-- Select Target Layer --", font=("Arial", 9, "bold")).pack(pady=(10, 2))

selected_layer = tk.StringVar()
layer_dropdown = ttk.Combobox(root, textvariable=selected_layer, values=layer_list, width=60)
layer_dropdown.pack(pady=2)

tk.Label(root, text="Nearest street + nearest EG_MAD address -> LOCATION", font=("Arial", 8), fg="gray").pack(pady=2)

def run():
    target = selected_layer.get()

    if not target:
        messagebox.showwarning("Missing", "Please select a target layer.")
        return

    root.destroy()

    editor = None

    try:
        # -- Resolve layer objects ----------------------------
        layer_name = target.split("\\")[-1]
        target_layer = map_obj.listLayers(layer_name)[0]
        eg_mad = map_obj.listLayers("EG_MAD")[0]
        eg_streets = map_obj.listLayers("*EG_STREETS")[0]

        # -- STEP 1: Generate Near Table ----------------------
        # Gets both NEAR_FID (to look up address) and NEAR_ANGLE (for direction)
        near_table = "memory/near_table"
        if arcpy.Exists(near_table):
            arcpy.management.Delete(near_table)

        print("Generating Near Table...")
        arcpy.analysis.GenerateNearTable(
            in_features=target_layer,
            near_features=eg_mad,
            out_table=near_table,
            search_radius="300 Feet",
            location="NO_LOCATION",
            angle="ANGLE",
            closest="CLOSEST",
            method="PLANAR"
        )
        print("  Near Table generated")

        # -- STEP 1b: Second Near Table for the street --------
        street_table = "memory/street_table"
        if arcpy.Exists(street_table):
            arcpy.management.Delete(street_table)

        print("Generating Street Near Table...")
        arcpy.analysis.GenerateNearTable(
            in_features=target_layer,
            near_features=eg_streets,
            out_table=street_table,
            search_radius="300 Feet",
            location="NO_LOCATION",
            angle="NO_ANGLE",
            closest="CLOSEST",
            method="PLANAR"
        )
        print("  Street Near Table generated")

        # -- STEP 2: Read near tables into dictionaries -------
        # {target_OID: (near_fid, angle)}
        near_dict = {}
        with arcpy.da.SearchCursor(near_table, ["IN_FID", "NEAR_FID", "NEAR_ANGLE"]) as cursor:
            for row in cursor:
                near_dict[row[0]] = (row[1], row[2])

        print(f"  Loaded {len(near_dict)} near matches")

        # {target_OID: street_fid}
        street_near_dict = {}
        with arcpy.da.SearchCursor(street_table, ["IN_FID", "NEAR_FID"]) as cursor:
            for row in cursor:
                street_near_dict[row[0]] = row[1]

        print(f"  Loaded {len(street_near_dict)} street matches")

        # -- STEP 3: Read FULLADDRES from EG_MAD -------------
        # {EG_MAD_OID: address}
        address_dict = {}
        near_fids = {v[0] for v in near_dict.values()}

        with arcpy.da.SearchCursor(eg_mad, ["OID@", "FULLADDRES"]) as cursor:
            for row in cursor:
                if row[0] in near_fids:
                    address_dict[row[0]] = row[1]

        print(f"  Loaded {len(address_dict)} addresses from EG_MAD")

        # -- STEP 3b: Read FULLSTREET from EG_STREETS --------
        # {EG_STREETS_OID: street name}
        street_dict = {}
        street_fids = set(street_near_dict.values())

        with arcpy.da.SearchCursor(eg_streets, ["OID@", "FULLSTREET"]) as cursor:
            for row in cursor:
                if row[0] in street_fids:
                    street_dict[row[0]] = row[1]

        print(f"  Loaded {len(street_dict)} streets from EG_STREETS")

        # -- STEP 4: Open edit session ------------------------
        desc = arcpy.Describe(target_layer)
        workspace = desc.path
        if arcpy.Describe(workspace).dataType == "FeatureDataset":
            workspace = arcpy.Describe(workspace).path
        print(f"  Workspace: {workspace}")

        editor = arcpy.da.Editor(workspace)
        editor.startEditing(False, True)
        editor.startOperation()

        # -- STEP 5: LOCATION = "street, direction + address" -
        updated = 0
        skipped = 0

        with arcpy.da.UpdateCursor(target_layer, ["OID@", "LOCATION"]) as cursor:
            for row in cursor:
                oid = row[0]
                match = near_dict.get(oid)

                if match:
                    near_fid, angle = match
                    address = address_dict.get(near_fid)

                    if address:
                        direction = angle_to_direction(angle)
                        street = street_dict.get(street_near_dict.get(oid))

                        if street:
                            row[1] = f"{street}, {direction} {address}"
                        else:
                            row[1] = f"{direction} {address}"

                        cursor.updateRow(row)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

        # -- STEP 6: Save edits -------------------------------
        editor.stopOperation()
        editor.stopEditing(True)
        editor = None
        print(f"  Done! {updated} updated, {skipped} skipped")

        # -- STEP 7: Cleanup ----------------------------------
        if arcpy.Exists(near_table):
            arcpy.management.Delete(near_table)
        if arcpy.Exists(street_table):
            arcpy.management.Delete(street_table)
        print("  Near tables deleted")

        print(f"\nComplete - LOCATION set on {layer_name}")

    except Exception as e:
        if editor is not None:
            try:
                editor.stopOperation()
                editor.stopEditing(False)
            except Exception:
                pass
        print(f"ERROR: {e}")

tk.Button(root, text="Run", command=run).pack(pady=10)
root.mainloop()
