# coding: utf-8
# ============================================================
# POPULATE LOCATION WITH DIRECTION
# Description: Uses Generate Near Table twice --
#   1) nearest EG_MAD address  -> address + direction (NEAR_ANGLE)
#   2) nearest EG_STREETS line -> the street the feature sits on
# Then populates LOCATION as "street, direction address"
# e.g. "Bond RD, N/O 9201 OPAL CREST CT"
# No joins -- no field name corruption.
# ============================================================

import arcpy
import tkinter as tk
from tkinter import ttk, messagebox

# -- Settings ------------------------------------------------
ADDRESS_SEARCH_RADIUS = "300 Feet"   # how far to look for an EG_MAD address
STREET_SEARCH_RADIUS  = "300 Feet"   # how far to look for an EG_STREETS line
ADDRESS_FIELD = "FULLADDRES"         # field on EG_MAD
STREET_FIELD  = "FULLSTREET"         # field on EG_STREETS

aprx = arcpy.mp.ArcGISProject("CURRENT")
map_obj = aprx.activeMap

def get_layer_path(map_obj):
    paths = {}
    for l in map_obj.listLayers():
        if l.isFeatureLayer:
            paths[l.longName] = l.longName
    return paths

layer_list = list(get_layer_path(map_obj).keys())

def find_layer(map_obj, wanted):
    """Find a feature layer by name, ignoring case and any DB prefix
    (so 'EG_STREETS' also matches 'GIS.EG_STREETS')."""
    wanted_l = wanted.lower()
    layers = [l for l in map_obj.listLayers() if l.isFeatureLayer]
    for l in layers:                                   # exact name
        if l.name.lower() == wanted_l:
            return l
    for l in layers:                                   # prefixed name
        short = l.name.lower().split(".")[-1]
        if short == wanted_l.split(".")[-1]:
            return l
    return None

def default_layer_name(wanted):
    lyr = find_layer(map_obj, wanted)
    return lyr.longName if lyr else ""

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

def normalize(text):
    """Loose compare helper: upper case, strip punctuation/extra spaces."""
    if not text:
        return ""
    cleaned = "".join(c if c.isalnum() else " " for c in str(text).upper())
    return " ".join(cleaned.split())

# -- Build the Popup UI --------------------------------------
root = tk.Tk()
root.title("Populate LOCATION with Direction")
root.geometry("560x300")

tk.Label(root, text="-- Select Target Layer --", font=("Arial", 9, "bold")).pack(pady=(10, 2))

selected_layer = tk.StringVar()
layer_dropdown = ttk.Combobox(root, textvariable=selected_layer, values=layer_list, width=68)
layer_dropdown.pack(pady=2)

tk.Label(root, text="-- Address Layer (EG_MAD) --", font=("Arial", 9, "bold")).pack(pady=(10, 2))

selected_address_layer = tk.StringVar(value=default_layer_name("EG_MAD"))
address_dropdown = ttk.Combobox(root, textvariable=selected_address_layer, values=layer_list, width=68)
address_dropdown.pack(pady=2)

tk.Label(root, text="-- Street Layer (GIS.EG_STREETS) --", font=("Arial", 9, "bold")).pack(pady=(10, 2))

selected_street_layer = tk.StringVar(value=default_layer_name("EG_STREETS"))
street_dropdown = ttk.Combobox(root, textvariable=selected_street_layer, values=layer_list, width=68)
street_dropdown.pack(pady=2)

skip_same_street = tk.BooleanVar(value=True)
tk.Checkbutton(
    root,
    text="Skip street prefix when the address is already on that street",
    variable=skip_same_street
).pack(pady=(8, 0))

tk.Label(
    root,
    text="Nearest street FULLSTREET + nearest EG_MAD direction/FULLADDRES -> LOCATION",
    font=("Arial", 8), fg="gray"
).pack(pady=2)

def near_lookup(target_layer, near_layer, radius, label):
    """Run Generate Near Table and return {target_OID: (near_fid, near_angle)}."""
    near_table = "memory/near_table_" + label
    if arcpy.Exists(near_table):
        arcpy.management.Delete(near_table)

    print(f"Generating Near Table ({label})...")
    arcpy.analysis.GenerateNearTable(
        in_features=target_layer,
        near_features=near_layer,
        out_table=near_table,
        search_radius=radius,
        location="NO_LOCATION",
        angle="ANGLE",
        closest="CLOSEST",
        method="PLANAR"
    )

    result = {}
    with arcpy.da.SearchCursor(near_table, ["IN_FID", "NEAR_FID", "NEAR_ANGLE"]) as cursor:
        for row in cursor:
            result[row[0]] = (row[1], row[2])

    if arcpy.Exists(near_table):
        arcpy.management.Delete(near_table)

    print(f"  Loaded {len(result)} near matches ({label})")
    return result

def value_lookup(layer, field, wanted_oids, label):
    """Return {OID: field value} for the OIDs we actually matched."""
    values = {}
    with arcpy.da.SearchCursor(layer, ["OID@", field]) as cursor:
        for row in cursor:
            if row[0] in wanted_oids:
                values[row[0]] = row[1]
    print(f"  Loaded {len(values)} {label} values")
    return values

def run():
    target = selected_layer.get()
    address_target = selected_address_layer.get()
    street_target = selected_street_layer.get()

    if not target:
        messagebox.showwarning("Missing", "Please select a target layer.")
        return
    if not address_target:
        messagebox.showwarning("Missing", "Please select the address layer (EG_MAD).")
        return
    if not street_target:
        messagebox.showwarning("Missing", "Please select the street layer (EG_STREETS).")
        return

    skip_dupe = skip_same_street.get()
    root.destroy()

    editor = None

    try:
        # -- Resolve layer objects ----------------------------
        layer_name = target.split("\\")[-1]
        target_layer = map_obj.listLayers(layer_name)[0]
        eg_mad = map_obj.listLayers(address_target.split("\\")[-1])[0]
        eg_streets = map_obj.listLayers(street_target.split("\\")[-1])[0]

        # -- Field sanity check -------------------------------
        mad_fields = [f.name.upper() for f in arcpy.ListFields(eg_mad)]
        if ADDRESS_FIELD.upper() not in mad_fields:
            raise ValueError(f"{ADDRESS_FIELD} not found on {eg_mad.name}")

        street_fields = [f.name.upper() for f in arcpy.ListFields(eg_streets)]
        if STREET_FIELD.upper() not in street_fields:
            raise ValueError(f"{STREET_FIELD} not found on {eg_streets.name}")

        # -- STEP 1: Near tables ------------------------------
        # NEAR_FID -> which feature; NEAR_ANGLE -> direction (addresses only)
        addr_near = near_lookup(target_layer, eg_mad, ADDRESS_SEARCH_RADIUS, "address")
        street_near = near_lookup(target_layer, eg_streets, STREET_SEARCH_RADIUS, "street")

        # -- STEP 2: Read the text values ---------------------
        address_dict = value_lookup(
            eg_mad, ADDRESS_FIELD, {v[0] for v in addr_near.values()}, "address"
        )
        street_dict = value_lookup(
            eg_streets, STREET_FIELD, {v[0] for v in street_near.values()}, "street"
        )

        # -- STEP 3: Open edit session ------------------------
        desc = arcpy.Describe(target_layer)
        workspace = desc.path
        if arcpy.Describe(workspace).dataType == "FeatureDataset":
            workspace = arcpy.Describe(workspace).path
        print(f"  Workspace: {workspace}")

        editor = arcpy.da.Editor(workspace)
        editor.startEditing(False, True)
        editor.startOperation()

        # -- STEP 4: LOCATION = "street, direction address" ---
        updated = 0
        skipped = 0
        no_street = 0

        with arcpy.da.UpdateCursor(target_layer, ["OID@", "LOCATION"]) as cursor:
            for row in cursor:
                oid = row[0]
                match = addr_near.get(oid)

                if not match:
                    skipped += 1
                    continue

                near_fid, angle = match
                address = address_dict.get(near_fid)

                if not address:
                    skipped += 1
                    continue

                direction = angle_to_direction(angle)
                location = f"{direction} {address}"

                street_match = street_near.get(oid)
                street = street_dict.get(street_match[0]) if street_match else None

                if street:
                    # Don't repeat the street when the address is already on it
                    if skip_dupe and normalize(street) in normalize(address):
                        pass
                    else:
                        location = f"{street}, {location}"
                else:
                    no_street += 1

                row[1] = location
                cursor.updateRow(row)
                updated += 1

        # -- STEP 5: Save edits -------------------------------
        editor.stopOperation()
        editor.stopEditing(True)
        editor = None
        print(f"  Done! {updated} updated, {skipped} skipped, {no_street} without a street match")

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
