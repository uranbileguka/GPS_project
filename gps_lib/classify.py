"""Label-based classification rules for trackers and zones.

These regex rules were copy-pasted near-verbatim across get_GPS_trackpoint.ipynb,
GPS_trackpoint_analysis.ipynb, GPS_zone_analysis.ipynb, and
GPS_trackpoint_route_analysis.ipynb (which had its own copy three separate times).
Centralized here so the classification rule is defined exactly once.
"""
import pandas as pd


def classify_technic_type(tracker_list_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each tracker as dump / loader / other from its label."""
    df = tracker_list_df.copy()
    df["technic_type"] = "other"
    df.loc[df["label"].str.contains("HDU|BN", case=False, na=False), "technic_type"] = "dump"
    df.loc[df["label"].str.contains("HLW|ачигч", case=False, na=False), "technic_type"] = "loader"
    return df


def classify_technic_material_type(tracker_list_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each tracker with a secondary material-area code (e.g. 'bn') from its label."""
    df = tracker_list_df.copy()
    df["technic_m_type"] = "other"
    df.loc[df["label"].str.contains("BN", case=False, na=False), "technic_m_type"] = "bn"
    return df


def classify_zone_material_type(zone_list_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each zone with a material type (reject / bn / middling / other) from its label."""
    df = zone_list_df.copy()
    df["zone_material_type"] = "other"
    df.loc[
        df["label"].str.contains("Reject овоолго|Reject ачилтын бүс", case=False, na=False),
        "zone_material_type",
    ] = "reject"
    df.loc[
        df["label"].str.contains(
            "Баруун наран ачилтын бүс  /Зүүн/|Баруун наран овоолго|Баруун наран ачилтын бүс /Баруун/",
            case=False, na=False,
        ),
        "zone_material_type",
    ] = "bn"
    df.loc[
        df["label"].str.contains("Middling ачилтын бүс|SP7|SP4|Sp5", case=False, na=False),
        "zone_material_type",
    ] = "middling"
    return df


def classify_zone_load_type(zone_list_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each zone as load / unload from its label. Expects zone_material_type already set."""
    df = zone_list_df.copy()
    df["zone_load_type"] = "unload"
    df.loc[
        df["label"].str.contains(
            "Reject ачилтын бүс|Баруун наран ачилтын бүс|Middling ачилтын бүс",
            case=False, na=False,
        ),
        "zone_load_type",
    ] = "load"
    return df


def classify_zones(zone_list_df: pd.DataFrame, drop_other: bool = False) -> pd.DataFrame:
    """Apply material + load classification to a zone list in one call.

    drop_other=True mirrors the `filtered_df` pattern used throughout the
    original notebooks: keep only zones with a recognized material type.
    """
    df = classify_zone_material_type(zone_list_df)
    df = classify_zone_load_type(df)
    if drop_other:
        df = df[df["zone_material_type"] != "other"].copy()
    return df
