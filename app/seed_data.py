"""Initial Material-prefix → plan-model assignments derived from the sample data.

Admins can add, edit and remove these via /admin/mapping after first launch.
"""

INITIAL_MATERIAL_MAP = [
    # (material_prefix, plan_super, plan_model)
    ("DSX896",    "DSX",       "Desert X (896)"),
    ("DVLV4",     "DVL",       "Diavel V4 / Bentley"),
    ("DVLV4RS",   "DVL",       "Diavel V4 RS"),
    ("HYMV2",     "HYM",       "HYM"),
    ("HYMV2SP",   "HYM",       "HYM SP"),
    ("MON896",    "M",         "Monster (896)"),
    ("MON896+",   "M",         "Monster + (896)"),
    ("MS896",     "MTS V2",    "MTS V2"),
    ("MS896S",    "MTS V2",    "MTS V2 S"),
    ("MS896ST",   "MTS V2",    "MTS V2 ST"),
    ("MSV4PP",    "MTS V4",    "MTS V4 PP Radar / PP MTO"),
    ("MSV4S",     "MTS V4",    "MTS V4 S / MTS V4 S MTO"),
    ("MSV4SI",    "MTS V4",    "MTS V4 S Radar"),
    ("MSV4RS",    "MTS V4",    "MTS V4 RS"),
    ("MSV4RI",    "MTS V4",    "MTS V4 Rally Radar / MTO"),
    ("MSV4RTI",   "MTS V4",    "MTS V4 Rally Travel & Radar"),
    ("MSV4RTIP",  "MTS V4",    "MTS V4 Rally Full"),
    ("CR250MX",   "Off Road",  "Cross 250"),
    ("ENDR450",   "Off Road",  "Enduro 450"),
    ("CR450MX",   "Off Road",  "Cross 450"),
    ("CR450R",    "Off Road",  "Cross 450 R"),
    ("PAN896FB",  "Panigale",  "Panigale V2 (896) S FB63"),
    ("PAN896MM",  "Panigale",  "Panigale V2 (896) S MM93"),
    ("PAN896S",   "Panigale",  "Panigale V2 S"),
    ("PANV47G",   "Panigale",  "Panigale V4 7G"),
    ("PAN4MM93",  "Panigale",  "Panigale V4 S Replica MotoGP Winner"),
    ("PANV4R7G",  "Panigale",  "Panigale V4 R 7G"),
    ("PANV4S7G",  "Panigale",  "Panigale V4 S 7G"),
    ("PANV4SLC",  "Panigale",  "Panigale V4 Superleggera Centenario 7G"),
    ("PANV4SLT",  "Panigale",  "Panigale V4 Superleggera Tricolore 7G"),
    ("FOR73",     "Scrambler", "Formula '73"),
    ("SC800FT",   "Scrambler", "SCR Full Throttle 2G"),
    ("SC800DK",   "Scrambler", "SCR Dark 2G"),
    ("SC800NS",   "Scrambler", "SCR Nightshift 2G"),
    ("SF896",     "SF",        "Streetfighter V2 S"),
    ("SFV4COR",   "SF",        "Streetfighter V4 Corse 3G"),
    ("SFV4S3G",   "SF",        "Streetfighter V4 S 3G"),
]


def seed(con):
    for prefix, p_super, p_model in INITIAL_MATERIAL_MAP:
        con.execute(
            "INSERT OR IGNORE INTO material_map(material_prefix, plan_super, plan_model, status) "
            "VALUES(?,?,?, 'active')",
            (prefix, p_super, p_model),
        )
    con.commit()
