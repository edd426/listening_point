"""The star catalogue: bright named stars, constellation figures, and a random faint field."""
import numpy as np

# ------------------------------------------------------------------- stars ---
W_, BW, YW, OR, RD = (1, 1, 1), (.85, .93, 1.1), (1.05, 1, .9), (1.15, .92, .72), (1.2, .8, .62)
STARS = [
    ("Sirius", 6.752, -16.72, -1.46, BW), ("Betelgeuse", 5.919, 7.41, 0.50, OR),
    ("Rigel", 5.242, -8.20, 0.13, BW), ("Bellatrix", 5.419, 6.35, 1.64, BW),
    ("Mintaka", 5.533, -0.30, 2.23, BW), ("Alnilam", 5.604, -1.20, 1.69, BW),
    ("Alnitak", 5.679, -1.94, 1.77, BW), ("Saiph", 5.796, -9.67, 2.07, BW),
    ("Meissa", 5.585, 9.93, 3.39, BW), ("Mirzam", 6.378, -17.96, 1.98, BW),
    ("Adhara", 6.977, -28.97, 1.50, BW), ("Wezen", 7.140, -26.39, 1.83, YW),
    ("Aludra", 7.402, -29.30, 2.45, BW), ("Procyon", 7.655, 5.22, 0.34, YW),
    ("Gomeisa", 7.453, 8.29, 2.89, BW), ("Castor", 7.577, 31.89, 1.58, W_),
    ("Pollux", 7.755, 28.03, 1.14, OR), ("Alhena", 6.629, 16.40, 1.93, W_),
    ("Mebsuta", 6.732, 25.13, 3.06, YW), ("Aldebaran", 4.599, 16.51, 0.86, OR),
    ("Elnath", 5.438, 28.61, 1.65, BW), ("Ain", 4.477, 19.18, 3.53, OR),
    ("HyadumI", 4.330, 15.63, 3.65, OR), ("HyadumII", 4.382, 17.54, 3.76, OR),
    ("Chamukuy", 4.477, 15.87, 3.40, W_), ("Tianguan", 5.627, 21.14, 3.00, BW),
    ("Alcyone", 3.791, 24.105, 2.87, BW), ("Atlas", 3.819, 24.053, 3.62, BW),
    ("Electra", 3.747, 24.113, 3.70, BW), ("Maia", 3.763, 24.368, 3.87, BW),
    ("Merope", 3.772, 23.948, 4.18, BW), ("Taygeta", 3.753, 24.467, 4.30, BW),
    ("Pleione", 3.819, 24.137, 5.05, BW), ("Capella", 5.278, 46.00, 0.08, YW),
    ("Menkalinan", 5.992, 44.95, 1.90, W_), ("Mirfak", 3.405, 49.86, 1.79, YW),
    ("Algol", 3.136, 40.96, 2.12, BW), ("Hamal", 2.120, 23.46, 2.00, OR),
    ("Sheratan", 1.911, 20.81, 2.64, W_), ("Alpheratz", 0.140, 29.09, 2.06, BW),
    ("Mirach", 1.162, 35.62, 2.05, OR), ("Almach", 2.065, 42.33, 2.10, OR),
    ("DeltaAnd", 0.656, 30.86, 3.27, OR), ("Markab", 23.079, 15.21, 2.48, BW),
    ("Scheat", 23.063, 28.08, 2.42, OR), ("Algenib", 0.221, 15.18, 2.83, BW),
    ("Enif", 21.736, 9.88, 2.39, OR), ("Homam", 22.691, 10.83, 3.40, BW),
    ("Matar", 22.717, 30.22, 2.94, YW), ("Diphda", 0.727, -17.99, 2.02, OR),
    ("Menkar", 3.038, 4.09, 2.54, OR), ("Fomalhaut", 22.961, -29.62, 1.16, W_),
    ("Sadalsuud", 21.526, -5.57, 2.87, YW), ("Sadalmelik", 22.096, -0.32, 2.95, YW),
    ("DenebAlgedi", 21.784, -16.13, 2.85, W_), ("Dabih", 20.350, -14.78, 3.05, YW),
    ("Altair", 19.846, 8.87, 0.77, W_), ("Tarazed", 19.771, 10.61, 2.72, OR),
    ("Alshain", 19.922, 6.41, 3.71, YW), ("Vega", 18.616, 38.78, 0.03, BW),
    ("Sheliak", 18.835, 33.36, 3.52, BW), ("Sulafat", 18.982, 32.69, 3.25, BW),
    ("Deneb", 20.690, 45.28, 1.25, BW), ("Sadr", 20.370, 40.26, 2.23, YW),
    ("Gienah", 20.770, 33.97, 2.48, OR), ("Fawaris", 19.750, 45.13, 2.87, BW),
    ("Albireo", 19.512, 27.96, 3.08, OR), ("KausAustralis", 18.403, -34.38, 1.85, BW),
    ("Nunki", 18.921, -26.30, 2.05, BW), ("KausMedia", 18.350, -29.83, 2.70, OR),
    ("KausBorealis", 18.466, -25.42, 2.81, OR), ("Ascella", 19.044, -29.88, 2.60, W_),
    ("Alnasl", 18.097, -30.42, 2.99, OR), ("PhiSgr", 18.761, -26.99, 3.17, BW),
    ("TauSgr", 19.116, -27.67, 3.32, OR), ("Antares", 16.490, -26.43, 1.06, RD),
    ("Rasalhague", 17.582, 12.56, 2.08, W_), ("Arcturus", 14.261, 19.18, -0.05, OR),
    ("Spica", 13.420, -11.16, 0.97, BW), ("Regulus", 10.140, 11.97, 1.35, BW),
    ("Denebola", 11.818, 14.57, 2.13, W_), ("Algieba", 10.333, 19.84, 2.08, OR),
    ("Alphard", 9.460, -8.66, 1.98, OR), ("Alphecca", 15.578, 26.71, 2.22, W_),
]
LINES = [
    ("Betelgeuse", "Meissa"), ("Meissa", "Bellatrix"), ("Betelgeuse", "Alnitak"), ("Bellatrix", "Mintaka"),
    ("Mintaka", "Alnilam"), ("Alnilam", "Alnitak"), ("Alnitak", "Saiph"), ("Mintaka", "Rigel"),
    ("Mirzam", "Sirius"), ("Sirius", "Wezen"), ("Wezen", "Adhara"), ("Wezen", "Aludra"),
    ("Procyon", "Gomeisa"), ("Castor", "Pollux"), ("Castor", "Mebsuta"), ("Pollux", "Alhena"),
    ("HyadumI", "HyadumII"), ("HyadumII", "Ain"), ("Ain", "Elnath"), ("HyadumI", "Chamukuy"),
    ("Chamukuy", "Aldebaran"), ("Aldebaran", "Tianguan"), ("Capella", "Menkalinan"), ("Mirfak", "Algol"),
    ("Hamal", "Sheratan"), ("Alpheratz", "DeltaAnd"), ("DeltaAnd", "Mirach"), ("Mirach", "Almach"),
    ("Alpheratz", "Scheat"), ("Scheat", "Markab"), ("Markab", "Algenib"), ("Algenib", "Alpheratz"),
    ("Markab", "Homam"), ("Homam", "Enif"), ("Scheat", "Matar"), ("Tarazed", "Altair"),
    ("Altair", "Alshain"), ("Vega", "Sheliak"), ("Sheliak", "Sulafat"), ("Sulafat", "Vega"),
    ("Deneb", "Sadr"), ("Sadr", "Albireo"), ("Gienah", "Sadr"), ("Sadr", "Fawaris"),
    ("Vega", "Altair"), ("Altair", "Deneb"), ("Deneb", "Vega"),
    ("KausMedia", "KausBorealis"), ("KausBorealis", "PhiSgr"), ("PhiSgr", "KausMedia"),
    ("KausMedia", "KausAustralis"), ("KausAustralis", "Ascella"), ("Ascella", "PhiSgr"),
    ("PhiSgr", "Nunki"), ("Nunki", "TauSgr"), ("TauSgr", "Ascella"), ("Alnasl", "KausMedia"),
    ("Alnasl", "KausAustralis"), ("Regulus", "Algieba"), ("Algieba", "Denebola"),
    ("Denebola", "Regulus"), ("Dabih", "DenebAlgedi"), ("Sadalsuud", "Sadalmelik"),
]
GAL = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
                [0.4941094279, -0.4448296300, 0.7469822445],
                [-0.8676661490, -0.1980763734, 0.4559837762]])


def _catalog():
    rng = np.random.default_rng(2024)
    n = 7000
    ra = rng.uniform(0, 24, n)
    dec = np.degrees(np.arcsin(rng.uniform(-1, 1, n)))
    mag = 6.6 - 3.2 * rng.random(n) ** 2.6
    # a second population hugging the galactic plane, so the Milky Way reads as stars
    m = 2600
    l = np.radians(rng.uniform(-180, 180, m))
    b = np.radians(rng.normal(0, 7, m))
    g = np.stack([np.cos(b) * np.cos(l), np.cos(b) * np.sin(l), np.sin(b)])
    eq = GAL.T @ g
    ra = np.concatenate([ra, (np.degrees(np.arctan2(eq[1], eq[0])) / 15) % 24])
    dec = np.concatenate([dec, np.degrees(np.arcsin(eq[2]))])
    mag = np.concatenate([mag, rng.uniform(5.2, 6.9, m)])
    t = rng.random(n + m)
    tint = np.where(t[:, None] < .25, BW, np.where(t[:, None] < .85, W_, np.where(t[:, None] < .97, YW, OR)))
    ra = np.concatenate([[s[1] for s in STARS], ra])
    dec = np.concatenate([[s[2] for s in STARS], dec])
    mag = np.concatenate([[s[3] for s in STARS], mag])
    tint = np.concatenate([np.array([s[4] for s in STARS], float), tint])
    return ra, dec, mag, tint.astype(np.float32)


STAR_RA, STAR_DEC, STAR_MAG, STAR_TINT = _catalog()
STAR_IDX = {s[0]: i for i, s in enumerate(STARS)}

