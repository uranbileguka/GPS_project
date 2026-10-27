"""Label-based classification rules for trackers and zones.

These regex rules were copy-pasted near-verbatim across get_GPS_trackpoint.ipynb,
GPS_trackpoint_analysis.ipynb, GPS_zone_analysis.ipynb, and
GPS_trackpoint_route_analysis.ipynb (which had its own copy three separate times).
Centralized here so the classification rule is defined exactly once.
"""
import pandas as pd

# Units the label rule gets wrong, checked against the register and the GPS records on
# 2026-10-26. The rule "label contains HDU or BN" classifies 89 units as haul trucks; with
# the three corrections below the set is 88 (41 HDU + 47 BN), every one a truck by label.
#   46076  "#ВN-148 83-64УКА"      a BN haul truck whose label is written with a Cyrillic В,
#                                   so the Latin "BN" pattern misses it. It makes 93-171 BN
#                                   cycles a month (3.5-6.9% of the flow) and is a different
#                                   vehicle from #BN149 (4-8 km apart at matched times).
#   39377  "Засварын машин BN02"   repair vehicle; it formed 1-15 stockyard cycles a month.
#   53448  "Кран-BN06"             crane; it never formed a cycle.
# Both pipelines (fleet_agent/preprocessing.py and fleet_agent/agent_v2.build_cycles) select
# trucks through these two functions, so the correction lives here and nowhere else.
FORCE_DUMP = {46076}
NOT_DUMP = {39377, 53448}
FORCE_BN = {46076}


def classify_technic_type(tracker_list_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each tracker as dump / loader / other from its label, then apply the exceptions."""
    df = tracker_list_df.copy()
    df["technic_type"] = "other"
    df.loc[df["label"].str.contains("HDU|BN", case=False, na=False), "technic_type"] = "dump"
    df.loc[df["label"].str.contains("HLW|ачигч", case=False, na=False), "technic_type"] = "loader"
    df.loc[df["id"].isin(FORCE_DUMP), "technic_type"] = "dump"
    df.loc[df["id"].isin(NOT_DUMP), "technic_type"] = "other"
    return df


def classify_technic_material_type(tracker_list_df: pd.DataFrame) -> pd.DataFrame:
    """Tag each tracker with a secondary material-area code (e.g. 'bn') from its label."""
    df = tracker_list_df.copy()
    df["technic_m_type"] = "other"
    df.loc[df["label"].str.contains("BN", case=False, na=False), "technic_m_type"] = "bn"
    df.loc[df["id"].isin(FORCE_BN), "technic_m_type"] = "bn"
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
