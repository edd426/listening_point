#!/usr/bin/env python3
"""Astronomy for The Listening Point: the real sun, moon, planets and stars for a place and a minute.

Pure NumPy and vectorised: every function of `jd` takes a scalar or an array of Julian dates (UT).
Conventions: UT1 is taken as UTC (they differ by < 0.9 s) and TT = UT + DELTA_T. Right ascension is
in hours, every other angle in degrees, and azimuth runs from north through east (south 180, west 270).
"Apparent of date" means the true equator and equinox of date, with light time, aberration and nutation.
Positions are geocentric: pass the Moon through topocentric() before altaz() (its parallax reaches 1 deg);
for the Sun (9") and planets (< 35") it can be skipped. altaz() is geometric; add refraction() for display.

Models: the Sun and planets from VSOP87B (Bretagnon & Francou 1988) truncated for 1950-2050; the Moon
from Meeus, Astronomical Algorithms ch. 47 (ELP-2000/82); IAU 2006 precession and sidereal time; IAU 1980
nutation (Meeus table 22.A); magnitudes from Mallama & Hilton (2018). tests/test_astro.py checks all of it
against JPL DE421 (via Skyfield) for Budapest, 2026-2036.
"""
import datetime as _dt
import re
from zoneinfo import ZoneInfo

import numpy as np

DELTA_T = 69.184                  # TT - UT in seconds: TT - UTC since 2017, with UT1 taken as UTC
J2000 = 2451545.0
AU_KM = 149597870.7
C_AU_DAY = 173.1446326846693      # speed of light, au per day
EARTH_A_KM, EARTH_F = 6378.137, 1 / 298.257223563   # WGS84
PLANETS = ("Mercury", "Venus", "Mars", "Jupiter", "Saturn")

# Meeus table 22.A (IAU 1980 nutation): D M M' F Omega, dpsi = (A + B T) sin, deps = (C + D T) cos, 0.0001"
_NUT = np.array("""
0 0 0 0 1 -171996 -174.2 92025 8.9, -2 0 0 2 2 -13187 -1.6 5736 -3.1, 0 0 0 2 2 -2274 -.2 977 -.5
0 0 0 0 2 2062 .2 -895 .5, 0 1 0 0 0 1426 -3.4 54 -.1, 0 0 1 0 0 712 .1 -7 0, -2 1 0 2 2 -517 1.2 224 -.6
0 0 0 2 1 -386 -.4 200 0, 0 0 1 2 2 -301 0 129 -.1, -2 -1 0 2 2 217 -.5 -95 .3, -2 0 1 0 0 -158 0 0 0
-2 0 0 2 1 129 .1 -70 0, 0 0 -1 2 2 123 0 -53 0, 2 0 0 0 0 63 0 0 0, 0 0 1 0 1 63 .1 -33 0
2 0 -1 2 2 -59 0 26 0, 0 0 -1 0 1 -58 -.1 32 0, 0 0 1 2 1 -51 0 27 0, -2 0 2 0 0 48 0 0 0
0 0 -2 2 1 46 0 -24 0, 2 0 0 2 2 -38 0 16 0, 0 0 2 2 2 -31 0 13 0, 0 0 2 0 0 29 0 0 0
-2 0 1 2 2 29 0 -12 0, 0 0 0 2 0 26 0 0 0, -2 0 0 2 0 -22 0 0 0, 0 0 -1 2 1 21 0 -10 0
0 2 0 0 0 17 -.1 0 0, 2 0 -1 0 1 16 0 -8 0, -2 2 0 2 2 -16 .1 7 0, 0 1 0 0 1 -15 0 9 0
-2 0 1 0 1 -13 0 7 0, 0 -1 0 0 1 -12 0 6 0, 0 0 2 -2 0 11 0 0 0, 2 0 -1 2 1 -10 0 5 0
2 0 1 2 2 -8 0 3 0, 0 1 0 2 2 7 0 -3 0, -2 1 1 0 0 -7 0 0 0, 0 -1 0 2 2 -7 0 3 0
2 0 0 2 1 -7 0 3 0, 2 0 1 0 0 6 0 0 0, -2 0 2 2 2 6 0 -3 0, -2 0 1 2 1 6 0 -3 0
2 0 -2 0 1 -6 0 3 0, 2 0 0 0 1 -6 0 3 0, 0 -1 1 0 0 5 0 0 0, -2 -1 0 2 1 -5 0 3 0
-2 0 0 0 1 -5 0 3 0, 0 0 2 2 1 -5 0 3 0, -2 0 2 0 1 4 0 0 0, -2 1 0 2 1 4 0 0 0
0 0 1 -2 0 4 0 0 0, -1 0 1 0 0 -4 0 0 0, -2 1 0 0 0 -4 0 0 0, 1 0 0 0 0 -4 0 0 0
0 0 1 2 0 3 0 0 0, 0 0 -2 2 2 -3 0 0 0, -1 -1 1 0 0 -3 0 0 0, 0 1 1 0 0 -3 0 0 0
0 -1 1 2 2 -3 0 0 0, 2 -1 -1 2 2 -3 0 0 0, 0 0 3 2 2 -3 0 0 0, 2 -1 0 2 2 -3 0 0 0
""".replace(",", " ").split(), float).reshape(-1, 9)

# Meeus table 47.A: D M M' F, longitude (1e-6 deg, sine) and distance (1e-3 km, cosine)
_MOON_LR = np.array("""
0 0 1 0 6288774 -20905355, 2 0 -1 0 1274027 -3699111, 2 0 0 0 658314 -2955968, 0 0 2 0 213618 -569925
0 1 0 0 -185116 48888, 0 0 0 2 -114332 -3149, 2 0 -2 0 58793 246158, 2 -1 -1 0 57066 -152138
2 0 1 0 53322 -170733, 2 -1 0 0 45758 -204586, 0 1 -1 0 -40923 -129620, 1 0 0 0 -34720 108743
0 1 1 0 -30383 104755, 2 0 0 -2 15327 10321, 0 0 1 2 -12528 0, 0 0 1 -2 10980 79661
4 0 -1 0 10675 -34782, 0 0 3 0 10034 -23210, 4 0 -2 0 8548 -21636, 2 1 -1 0 -7888 24208
2 1 0 0 -6766 30824, 1 0 -1 0 -5163 -8379, 1 1 0 0 4987 -16675, 2 -1 1 0 4036 -12831
2 0 2 0 3994 -10445, 4 0 0 0 3861 -11650, 2 0 -3 0 3665 14403, 0 1 -2 0 -2689 -7003
2 0 -1 2 -2602 0, 2 -1 -2 0 2390 10056, 1 0 1 0 -2348 6322, 2 -2 0 0 2236 -9884
0 1 2 0 -2120 5751, 0 2 0 0 -2069 0, 2 -2 -1 0 2048 -4950, 2 0 1 -2 -1773 4130
2 0 0 2 -1595 0, 4 -1 -1 0 1215 -3958, 0 0 2 2 -1110 0, 3 0 -1 0 -892 3258
2 1 1 0 -810 2616, 4 -1 -2 0 759 -1897, 0 2 -1 0 -713 -2117, 2 2 -1 0 -700 2354
2 1 -2 0 691 0, 2 -1 0 -2 596 0, 4 0 1 0 549 -1423, 0 0 4 0 537 -1117
4 -1 0 0 520 -1571, 1 0 -2 0 -487 -1739, 2 1 0 -2 -399 0, 0 0 2 -2 -381 -4421
1 1 1 0 351 0, 3 0 -2 0 -340 0, 4 0 -3 0 330 0, 2 -1 2 0 327 0
0 2 1 0 -323 1165, 1 1 -1 0 299 0, 2 0 3 0 294 0, 2 0 -1 -2 0 8752
""".replace(",", " ").split(), float).reshape(-1, 6)

# Meeus table 47.B: D M M' F, latitude (1e-6 deg, sine)
_MOON_B = np.array("""
0 0 0 1 5128122, 0 0 1 1 280602, 0 0 1 -1 277693, 2 0 0 -1 173237, 2 0 -1 1 55413, 2 0 -1 -1 46271
2 0 0 1 32573, 0 0 2 1 17198, 2 0 1 -1 9266, 0 0 2 -1 8822, 2 -1 0 -1 8216, 2 0 -2 -1 4324
2 0 1 1 4200, 2 1 0 -1 -3359, 2 -1 -1 1 2463, 2 -1 0 1 2211, 2 -1 -1 -1 2065, 0 1 -1 -1 -1870
4 0 -1 -1 1828, 0 1 0 1 -1794, 0 0 0 3 -1749, 0 1 -1 1 -1565, 1 0 0 1 -1491, 0 1 1 1 -1475
0 1 1 -1 -1410, 0 1 0 -1 -1344, 1 0 0 -1 -1335, 0 0 3 1 1107, 4 0 0 -1 1021, 4 0 -1 1 833
0 0 1 -3 777, 4 0 -2 1 671, 2 0 0 -3 607, 2 0 2 -1 596, 2 -1 1 -1 491, 2 0 -2 1 -451
0 0 3 -1 439, 2 0 2 1 422, 2 0 -3 -1 421, 2 1 -1 1 -366, 2 1 0 1 -351, 4 0 0 1 331
2 -1 1 1 315, 2 -2 0 -1 302, 0 0 1 3 -283, 2 1 1 -1 -229, 1 1 0 -1 223, 1 1 0 1 223
0 1 -2 -1 -220, 2 1 -1 -1 -220, 1 0 1 1 -185, 2 -1 -2 -1 181, 0 1 2 1 -177, 4 0 -2 -1 176
4 -1 -1 -1 166, 1 0 1 -1 -164, 4 0 1 -1 132, 1 0 -1 -1 -119, 4 -1 0 -1 115, 2 -2 0 1 107
""".replace(",", " ").split(), float).reshape(-1, 5)

# VSOP87B (CDS catalogue VI/81): heliocentric L, B (rad) and R (au) on the ecliptic and equinox J2000. Each "Xk"
# heads terms A cos(B + C t) multiplied by t**k, t in Julian millennia. Truncated for 1950-2050 to within 1.2" of
# the full series in the Sun's direction and 16" in the planets' (geocentric).
_VSOP87B = {
    "Earth": """
L0 1.753470457 0 0 .033416565 4.6692568 6283.07585 .000348943 4.626102 12566.1517 .000034176 2.82887 3.5231
.000034971 2.74412 5753.3849 .000031359 3.62767 77713.7715 .000026762 4.41808 7860.4194 .000023427 6.13516
3930.2097 .000012732 2.0371 529.691 .000013243 .74246 11506.77 .000009019 2.0451 26.298 .000011992 1.10963
1577.344 .000008572 3.5085 398.149 .000007798 1.1788 5223.694 .000009903 5.2327 5884.927 .000007531 2.5334
5507.553 .000005053 4.5829 18849.228 .000004924 4.2051 775.523 .000003567 2.9195 .067 .000002841 1.8987 796.298
.000002429 .3448 5486.778 .000003171 5.849 11790.629 .000002711 .3149 10977.079 .000002062 4.8065 2544.314
.000002055 1.8695 5573.143 .000002023 2.4577 6069.777 .000001262 1.083 20.78 .000001555 .8331 213.3 .000001151
.6454 .98 .000001029 .636 4694 .000001017 4.2668 7.11 .000000992 6.21 2146.17 .000001322 3.4112 2942.46
.000000976 .681 155.42 .000000851 1.299 6275.96 .000000747 1.755 5088.63 .000001019 .9757 15720.84 .000000847
3.671 71430.7 .000000735 4.679 801.82 .000000739 3.503 3154.69 .000000788 3.037 12036.46 .000000796 1.808
17260.15 .000000858 5.983 161000.69 .00000057 2.784 6286.6 .000000611 1.818 7084.9 .000000696 .833 9437.76
.000000561 4.387 14143.5 .000000624 3.978 8827.39 .000000511 .283 5856.48 .000000556 3.47 6279.55 .000000516
1.333 1748.02 .00000052 .189 12139.55 L1 6283.07584999 0 0 .00206059 2.678235 6283.0758 .00004303 2.6351
12566.152 B0 .000002796 3.1987 84334.662 .000001016 5.4225 5507.55 .000000804 3.88 5223.69 B1 .00227778 3.413766
6283.0758 .00003806 3.3706 12566.15 .0000362 0 0 R0 1.000139888 0 0 .016706996 3.0984635 6283.07585 .00013956
3.055246 12566.1517 .000030837 5.19847 77713.7715 .000016285 1.17388 5753.385 .000015756 2.84685 7860.419
.000009248 5.4529 11506.77 .000005424 4.5641 3930.21 .000004721 3.661 5884.927 .000003288 5.8998 5223.694
.00000346 .9637 5507.553 .000003068 .2987 5573.143 .000001748 3.0119 18849.23 .000002432 4.2735 11790.629
.000002118 5.8471 1577.344 .000001857 5.022 10977.08 .000001098 5.0551 5486.78 .000000983 .887 6069.78
.000000865 5.69 15720.84 .000000858 1.271 161000.69 .000000629 .922 529.69 .000000571 2.014 83996.85 .000000649
.273 17260.15 .000000557 5.242 71430.7 R1 .00103019 1.10749 6283.0758 .00001721 1.064 12566.15""",
    "Mercury": """
L0 4.402507101 0 0 .40989415 1.483020342 26087.9031416 .050462942 4.4778549 52175.806283 .008553468 1.1652032
78263.709425 .001655904 4.119692 104351.61257 .000345619 .779308 130439.5157 .000075835 3.71348 156527.4188
.000035597 1.51203 1109.379 .00001726 .3583 182615.322 .000018035 4.1033 5661.332 .000013647 4.5992 27197.282
.000015899 2.9951 25028.521 L1 26087.90313686 0 0 .011312 6.218742 26087.90314 .00292242 3.04449 52175.8063
.00075775 6.08569 78263.709 B0 .11737529 1.98357499 26087.9031416 .02388077 5.0373896 52175.806283 .012228395
3.1415927 0 .005432518 1.7964436 78263.709425 .001297788 4.832325 104351.61257 .000318669 1.580885 130439.5157
.000079633 4.60972 156527.4188 .000020142 1.3532 182615.322 B1 .00274646 3.95008 26087.9031 .00099738 3.14159 0
R0 .395282717 0 0 .078341318 6.19233723 26087.9031416 .007955256 2.9598969 52175.806283 .001212818 6.0106415
78263.70942 .00021922 2.778201 104351.61257 .000043541 5.82895 130439.5157 .000009182 2.5965 156527.419 R1
.00217348 4.656172 26087.9031 .00044142 1.42386 52175.8063 .00010094 4.4747 78263.709""",
    "Venus": """
L0 3.176146668 0 0 .013539684 5.5931332 10213.285546 .000898916 5.3065 20426.57109 .000054772 4.41631 7860.4194
.000034557 2.69964 11790.6291 .000023721 2.99378 3930.21 .000013172 5.1867 26.298 .000016641 4.25019 1577.344
.000014384 4.15745 9683.595 .000012005 6.1536 30639.857 .000007614 1.9501 529.691 .000007077 1.0647 775.523
.000007693 .8163 9437.763 L1 10213.28554622 0 0 .00095618 2.46407 10213.2855 B0 .059236385 .26702776
10213.2855462 .00040108 1.147372 20426.57109 .000328149 3.141593 0 .000010114 1.0895 30639.857 B1 .00287821
1.88965 10213.2855 R0 .723348209 0 0 .004898242 4.0215183 10213.285546 .000016581 4.90207 20426.571 .000016321
2.84549 7860.419 .00001378 1.12847 11790.629 R1 .00034551 .89199 10213.286""",
    "Mars": """
L0 6.2034771158 0 0 .1865636809 5.050371003 3340.6124267 .0110821682 5.40099836 6681.224853 .0009179841
5.7547874 10021.83728 .0002774499 5.970495 3.52312 .0001061024 2.939586 2281.2305 .000123159 .849561 2810.9215
.0000892678 4.156978 .0173 .0000871569 6.110052 13362.4497 .0000679756 .364622 398.149 .0000777487 3.339688
5621.8429 .0000357508 1.66187 2544.3144 .0000416111 .22815 2942.4634 .0000307525 .85697 191.4483 .0000262812
.64806 3337.0893 .0000293755 6.07894 .0673 .0000238941 5.03896 796.298 .0000257984 .02997 3344.1355 .0000152814
1.14979 6151.5339 .0000179881 .65634 529.691 .0000126436 3.62275 5092.152 .0000128623 3.06796 2146.165
.000015464 2.9158 1751.5395 .000010249 3.69334 8962.455 .0000089157 .18294 16703.062 .0000085876 2.40094
2914.014 .0000083272 2.46419 3340.595 .0000083272 4.49496 3340.63 .000007129 3.66335 1059.382 .0000074872
3.82249 155.42 .0000072386 .67497 3738.761 .0000063555 2.9218 8432.764 .0000065516 .4886 3127.313 .0000055047
3.81 .98 .0000055275 4.4748 1748.016 .0000042597 .5536 6283.076 .0000041513 .4966 213.299 .0000047217 3.6255
1194.447 L1 3340.61242701 0 0 .01457555 3.6043373 3340.61243 .00168415 3.923186 6681.2249 .00020623 4.26109
10021.837 B0 .0319713499 3.76832042 3340.6124267 .0029803323 4.10617 6681.224853 .0028910474 0 0 .0003136554
4.446511 10021.83728 .000034841 4.78813 13362.4497 .00000443 5.6523 3337.089 .000004434 5.0264 3344.136
.0000039911 5.1306 16703.062 B1 .00217311 6.044722 3340.6124 .00020977 3.14159 0 .00012835 1.6081 6681.225 R0
1.530334883 0 0 .141849532 3.479712835 3340.6124267 .006607764 3.8178344 6681.224853 .000461791 4.155953
10021.83728 .000081097 5.55958 2810.9215 .000074853 1.77239 5621.8429 .000055232 1.36436 2281.2305 .000038252
4.49407 13362.4497 .000023065 .09082 2544.3144 .000019994 5.3606 3337.089 .000024844 4.92546 2942.4634
.000019602 4.74249 3344.136 .000011671 2.11261 5092.152 .000011028 5.00908 398.149 .000008991 4.4079 529.691
.000009923 5.8386 6151.534 .000008074 2.1022 1059.382 .000007979 3.4484 796.298 .00000741 1.4991 2146.165
.000006923 2.1338 8962.455 .000006331 .8935 3340.595 .000007256 1.2452 8432.764 .000006331 2.9243 3340.63
.000005744 .829 2914.014 .000005262 5.3829 3738.761 .0000063 1.2874 1751.54 R1 .01107433 2.032505 3340.61243
.00103176 2.37072 6681.2249 .00012877 0 0 .00010816 2.7089 10021.837""",
    "Jupiter": """
L0 .5995469149 0 0 .0969589872 5.061917932 529.69096509 .0057361014 1.44406206 7.113547 .0030638921 5.4173473
1059.38193 .000971783 4.1426473 632.783739 .0007290308 3.6404292 522.577418 .0006426398 3.4114517 103.092774
.0003980606 2.2937674 419.484644 .0003885777 1.2723176 316.39187 .0002796463 1.7845459 536.80451 .0001358973
5.77481 1589.0729 .0000824635 3.582279 206.18555 .000087687 3.630003 949.17561 .0000736804 5.081012 735.87651
.0000626315 .024976 213.2991 .0000611406 4.5132 1162.4747 .000049054 1.320845 110.20632 .0000530528 1.306712
14.22709 .0000530544 4.186256 1052.26838 .0000464725 4.699581 3.93215 .0000304502 4.316764 426.5982 .0000261
1.566674 846.0828 .0000202819 1.063765 3.1814 .0000176476 2.14149 1066.4955 .0000172297 3.88036 1265.5675
.0000192094 .97168 639.8973 .0000163322 3.58202 515.4639 .00001432 4.29686 625.6702 .0000097327 4.09765 95.9792
L1 529.690965088 0 0 .004895032 4.2208294 529.69097 .002289172 6.026469 7.11355 .000300995 4.54541 1059.3819
.000207209 5.45943 522.5774 B0 .022686157 3.558526067 529.6909651 .0010997163 3.9080935 1059.38193 .0011009036 0
0 .0000810143 3.605096 522.57742 .00006044 4.258831 1589.0729 .0000643778 .306271 536.80451 .0000110688 2.98534
1162.4747 B1 .000782034 1.523779 529.69097 R0 5.208874293 0 0 .252093271 3.491086399 529.69096509 .006106
3.8411537 1059.38193 .002820295 2.5741988 632.783739 .001876473 2.0759038 522.57742 .000867929 .710011 419.48464
.00072063 .214657 536.80451 .000655172 5.979959 316.39187 .000291345 1.677594 103.09277 .000301353 2.16132
949.17561 .000234533 3.540235 735.87651 .000222837 4.193626 1589.0729 .000239473 .27458 7.11355 .000130326
2.96043 1162.4747 .000097034 1.9067 206.1855 .00012749 2.715503 1052.2684 .000091614 4.41353 213.2991 .000078945
2.47908 426.5982 .000070579 2.18185 1265.5675 .000061377 6.26418 846.0828 .00005477 5.6573 639.8973 R1 .01271802
2.649375 529.69097""",
    "Saturn": """
L0 .8740135402 0 0 .1110765976 3.9620509016 213.29909544 .0141415096 4.585815169 7.113547 .0039837939 .52112033
206.1855484 .0035076924 3.30329908 426.5981909 .002068163 .24658372 103.092774 .000792713 3.8400706 220.412642
.0002399035 4.6697692 110.206321 .0001657359 .4371923 419.48464 .0001490699 5.7690318 316.39187 .0001582029
.9380916 632.78374 .0001460956 1.5651847 3.93215 .000131603 4.4489129 14.22709 .0001505354 2.7166992 639.89729
.000130053 5.9811902 11.0457 .0001072507 3.1293952 202.2534 .0000586321 .236569 529.69097 .0000522776 4.207834
3.18139 .0000612632 1.763287 277.03499 .0000501969 3.177877 433.71174 .0000459255 .619777 199.072 .0000400587
2.244797 63.7359 .000029538 .982804 95.97923 .0000387367 3.222832 138.5175 .0000246119 2.031639 735.87651
.0000326948 .774926 949.17561 .0000175815 3.265801 522.5774 .0000164017 5.505045 846.0828 .0000139133 4.023332
323.5054 .0000158065 4.372653 309.2783 .000011235 2.837268 415.5525 .0000108723 4.183433 2.4477 L1 213.299095217
0 0 .012973709 1.8283492 213.299095 .005643454 2.8849972 7.113547 .000937344 1.063118 426.59819 .00107675
2.277691 206.18555 .000402445 2.041081 220.4126 B0 .0433067804 3.602844284 213.29909544 .002403483 2.85238489
426.5981909 .0008474594 0 0 .0003086336 3.484415 220.412642 .0003411606 .5729731 206.185548 .0001473407 2.118466
639.89729 .0000991667 5.790032 419.48464 .0000699356 4.736047 7.11355 .0000480759 5.433053 316.39187 .0000478839
4.965129 110.20632 .0000343213 2.732557 433.71174 .0000150613 6.013045 103.0928 .000010603 5.630993 529.691 B1
.00198928 4.93901 213.2991 .000369479 3.141593 0 R0 9.557581355 0 0 .529213829 2.392262196 213.29909544
.018736799 5.23549605 206.185548 .014646639 1.64763043 426.598191 .008218911 5.9352004 316.39187 .005475069
5.0153262 103.092774 .003716846 2.2711482 220.412642 .003617788 3.139043 7.113547 .001406175 5.7040661 632.78374
.001089748 3.2931339 110.20632 .00069007 5.940995 419.48464 .000610534 .940377 639.89729 .000489133 1.557336
202.2534 .000341438 .195191 277.03499 .000324018 5.470846 949.17561 .000209366 .463493 735.87651 .000208393
1.521025 433.71174 .000207468 5.332555 199.072 .000152984 3.059438 529.691 .000142965 2.604335 323.5054
.000119933 5.98051 846.0828 .000113803 1.731054 522.5774 .000128846 1.648907 138.5175 R1 .06182981 .2584351
213.299095 .00506577 .711146 206.18555 .00341394 5.796357 426.5982""",
}


def _parse_vsop(text):
    parts = re.split(r"([LBR]\d)", text)[1:]
    rows = {v: [] for v in "LBR"}
    for key, nums in zip(parts[::2], parts[1::2]):
        abc = np.array(nums.split(), float).reshape(-1, 3)
        rows[key[0]].append(np.column_stack([np.full(len(abc), float(key[1])), abc]))
    return [np.concatenate(rows[v]).T for v in "LBR"]


_SERIES = {k: _parse_vsop(v) for k, v in _VSOP87B.items()}
# VSOP87 ecliptic J2000 -> FK5 equator J2000 (Bretagnon & Francou)
_ECL2EQ = np.array([[1.0, 4.40360e-7, -1.90919e-7], [-4.79966e-7, 0.917482137087, -0.397776982902],
                    [0.0, 0.397776982902, 0.917482137087]])
_EVENTS = (("astronomical_dawn", -18.0, True), ("nautical_dawn", -12.0, True), ("civil_dawn", -6.0, True),
           ("sunrise", -0.8333, True), ("solar_noon", None, True), ("sunset", -0.8333, False),
           ("civil_dusk", -6.0, False), ("nautical_dusk", -12.0, False), ("astronomical_dusk", -18.0, False))


# ------------------------------------------------------------------ helpers ---
def _arr(x):
    return np.asarray(x, float)


def _tt(jd):
    """Julian centuries of TT since J2000."""
    return (_arr(jd) + DELTA_T / 86400.0 - J2000) / 36525.0


def _rot(axis, ang):
    """Frame rotations about x/y/z (0/1/2) by `ang` radians, shape ang.shape + (3, 3)."""
    c, s = np.cos(ang), np.sin(ang)
    o, z = np.ones_like(c), np.zeros_like(c)
    m = ([[o, z, z], [z, c, s], [z, -s, c]], [[c, z, -s], [z, o, z], [s, z, c]],
         [[c, s, z], [-s, c, z], [z, z, o]])[axis]
    return np.moveaxis(np.array(m), (0, 1), (-2, -1))


def _mv(m, v):
    return (m @ v[..., None])[..., 0]


def _vec(ra_h, dec_deg):
    a, d = np.broadcast_arrays(np.radians(_arr(ra_h) * 15.0), np.radians(_arr(dec_deg)))
    return np.stack([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)], -1)


def _radec(v):
    x, y, z = np.moveaxis(v, -1, 0)
    rxy = np.hypot(x, y)
    return np.degrees(np.arctan2(y, x)) / 15.0 % 24.0, np.degrees(np.arctan2(z, rxy)), np.hypot(rxy, z)


def _obliquity(t):
    """Mean obliquity of the ecliptic (IAU 2006), radians."""
    return np.radians((84381.406 + t * (-46.836769 + t * (-0.0001831 + t * (0.0020034 + t * -5.76e-7)))) / 3600)


def _nutation(t):
    """Nutation in longitude and obliquity (radians), IAU 1980 series as in Meeus table 22.A."""
    t = _arr(t)
    D = 297.85036 + t * (445267.111480 + t * (-0.0019142 + t / 189474))
    M = 357.52772 + t * (35999.050340 + t * (-0.0001603 - t / 300000))
    Mp = 134.96298 + t * (477198.867398 + t * (0.0086972 + t / 56250))
    F = 93.27191 + t * (483202.017538 + t * (-0.0036825 + t / 327270))
    Om = 125.04452 + t * (-1934.136261 + t * (0.0020708 + t / 450000))
    arg = np.radians(np.stack([D, M, Mp, F, Om], -1)) @ _NUT[:, :5].T
    tt = t[..., None]
    dpsi = np.sum((_NUT[:, 5] + _NUT[:, 6] * tt) * np.sin(arg), -1)
    deps = np.sum((_NUT[:, 7] + _NUT[:, 8] * tt) * np.cos(arg), -1)
    return np.radians(dpsi / 3.6e7), np.radians(deps / 3.6e7)


def _of_date(jd):
    """Rotation from J2000 mean equatorial to the true equator and equinox of date (nutation @ precession)."""
    t = _tt(jd)
    dpsi, deps = _nutation(t)
    eps = _obliquity(t)
    return _rot(0, -(eps + deps)) @ _rot(2, -dpsi) @ _rot(0, eps) @ precession_matrix(jd)


def _helio(body, tm):
    """Heliocentric ecliptic-J2000 position (au) from the truncated VSOP87B; tm in Julian millennia TT."""
    tm = _arr(tm)[..., None]
    L, B, R = (np.sum(a * tm ** p * np.cos(b + c * tm), -1) for p, a, b, c in _SERIES[body])
    return np.stack([R * np.cos(B) * np.cos(L), R * np.cos(B) * np.sin(L), R * np.sin(B)], -1)


# --------------------------------------------------------------------- time ---
def julian_day(dt):
    """Julian date (UT) of a timezone-aware datetime, a sequence of them, or numpy datetime64 values (UTC)."""
    if isinstance(dt, _dt.datetime):
        if dt.utcoffset() is None:
            raise ValueError("julian_day needs a timezone-aware datetime")
        return dt.timestamp() / 86400.0 + 2440587.5
    a = np.asarray(dt)
    if np.issubdtype(a.dtype, np.datetime64):
        return jd_from_unix((a - np.datetime64(0, "s")) / np.timedelta64(1, "s"))
    return np.vectorize(julian_day, otypes=[float])(a)


def jd_from_unix(seconds):
    """Julian date (UT) from Unix seconds."""
    return _arr(seconds) / 86400.0 + 2440587.5


def gmst_hours(jd):
    """Greenwich mean sidereal time, hours [0, 24) (IAU 2006, from the Earth rotation angle)."""
    du = _arr(jd) - J2000
    t = _tt(jd)
    era = 0.7790572732640 + 0.00273781191135448 * du + du % 1.0
    poly = 0.014506 + t * (4612.156534 + t * (1.3915817 + t * (-4.4e-7 + t * (-2.9956e-5 - 3.68e-8 * t))))
    return (era * 24.0 + poly / 54000.0) % 24.0


def lst_hours(jd, lon_deg):
    """Local apparent sidereal time, hours [0, 24): GMST + equation of the equinoxes + east longitude."""
    t = _tt(jd)
    dpsi, _ = _nutation(t)
    return (gmst_hours(jd) + np.degrees(dpsi * np.cos(_obliquity(t))) / 15.0 + _arr(lon_deg) / 15.0) % 24.0


# ----------------------------------------------------------------- frames ---
def precession_matrix(jd):
    """Rotation, shape (..., 3, 3), from J2000 mean equatorial vectors to the mean equator/equinox of date.

    IAU 2006 (Capitaine et al. 2003) angles zeta, z, theta.
    """
    t = _tt(jd)
    zeta = 2.650545 + t * (2306.083227 + t * (0.2988499 + t * (0.01801828 + t * (-5.971e-6 - 3.173e-7 * t))))
    z = -2.650545 + t * (2306.077181 + t * (1.0927348 + t * (0.01826837 + t * (-2.8596e-5 - 2.904e-7 * t))))
    theta = t * (2004.191903 + t * (-0.4294934 + t * (-0.04182264 + t * (-7.089e-6 - 1.274e-7 * t))))
    zeta, z, theta = np.radians(np.array([zeta, z, theta]) / 3600)
    return _rot(2, -z) @ _rot(1, theta) @ _rot(2, -zeta)


def precess(ra_h, dec_deg, jd):
    """J2000 mean RA (h) and Dec (deg) to the mean equator and equinox of date (precession only)."""
    ra, dec, _ = _radec(_mv(precession_matrix(jd), _vec(ra_h, dec_deg)))
    return ra, dec


def altaz(ra_h, dec_deg, jd, lat_deg, lon_deg):
    """Geometric altitude and azimuth (deg, azimuth from north through east) of an apparent RA/Dec of date."""
    H = np.radians((lst_hours(jd, lon_deg) - _arr(ra_h)) * 15.0)
    d, p = np.radians(_arr(dec_deg)), np.radians(_arr(lat_deg))
    e = -np.cos(d) * np.sin(H)
    n = np.sin(d) * np.cos(p) - np.cos(d) * np.cos(H) * np.sin(p)
    u = np.sin(d) * np.sin(p) + np.cos(d) * np.cos(H) * np.cos(p)
    return np.degrees(np.arctan2(u, np.hypot(e, n))), np.degrees(np.arctan2(e, n)) % 360.0


def topocentric(ra_h, dec_deg, dist_km, jd, lat_deg, lon_deg, height_m=0.0):
    """Geocentric to topocentric RA (h) and Dec (deg): parallax for an observer on the WGS84 ellipsoid."""
    p = np.radians(_arr(lat_deg))
    u = np.arctan((1 - EARTH_F) * np.tan(p))
    h = _arr(height_m) / 1000.0 / EARTH_A_KM
    rs, rc = (1 - EARTH_F) * np.sin(u) + h * np.sin(p), np.cos(u) + h * np.cos(p)   # rho sin/cos phi'
    th = np.radians(lst_hours(jd, lon_deg) * 15.0)
    obs = EARTH_A_KM * np.stack(np.broadcast_arrays(rc * np.cos(th), rc * np.sin(th), rs), -1)
    ra, dec, _ = _radec(_vec(ra_h, dec_deg) * _arr(dist_km)[..., None] - obs)
    return ra, dec


def refraction(alt_deg, pressure_hpa=1010.0, temp_c=10.0):
    """Degrees to add to a geometric altitude (Saemundsson 1986); tapers to 0 between -2 and -3 deg."""
    a = _arr(alt_deg)
    h = np.maximum(a, -1.9)
    r = (1.02 / np.tan(np.radians(h + 10.3 / (h + 5.11))) + 0.0019279) / 60.0
    return np.maximum(r, 0.0) * np.clip(a + 3.0, 0.0, 1.0) * (pressure_hpa / 1010.0) * (283.0 / (273.0 + temp_c))


# ------------------------------------------------------------- sun & moon ---
def _sun_true(jd):
    """Apparent geocentric vector of the Sun (au), true equator and equinox of date."""
    tm = _tt(jd) / 10.0
    r = np.linalg.norm(_helio("Earth", tm), axis=-1)
    g = -_helio("Earth", tm - r / C_AU_DAY / 365250.0)      # the Sun r/c ago: light time + aberration
    return _mv(_of_date(jd) @ _ECL2EQ, g) / np.linalg.norm(g, axis=-1)[..., None] * r[..., None]


def sun_radec(jd):
    """Apparent geocentric RA (h), Dec (deg) of date and distance (au) of the Sun."""
    return _radec(_sun_true(jd))


def _moon_ecliptic(jd):
    """Geocentric longitude, latitude (deg; mean ecliptic and equinox of date) and distance (km): Meeus ch. 47."""
    t = _tt(jd)
    Lp = 218.3164477 + t * (481267.88123421 + t * (-0.0015786 + t * (1 / 538841 - t / 65194000)))
    D = 297.8501921 + t * (445267.1114034 + t * (-0.0018819 + t * (1 / 545868 - t / 113065000)))
    M = 357.5291092 + t * (35999.0502909 + t * (-0.0001536 + t / 24490000))
    Mp = 134.9633964 + t * (477198.8675055 + t * (0.0087414 + t * (1 / 69699 - t / 14712000)))
    F = 93.2720950 + t * (483202.0175233 + t * (-0.0036539 + t * (-1 / 3526000 + t / 863310000)))
    E = (1 - t * (0.002516 + 0.0000074 * t))[..., None]
    a = np.radians(np.stack([D, M, Mp, F], -1))
    x = a @ _MOON_LR[:, :4].T
    k = E ** np.abs(_MOON_LR[:, 1])
    sl = np.sum(_MOON_LR[:, 4] * k * np.sin(x), -1)
    sr = np.sum(_MOON_LR[:, 5] * k * np.cos(x), -1)
    sb = np.sum(_MOON_B[:, 4] * E ** np.abs(_MOON_B[:, 1]) * np.sin(a @ _MOON_B[:, :4].T), -1)
    a1, a2, a3, lp, mp, f = np.radians([119.75 + 131.849 * t, 53.09 + 479264.290 * t,
                                        313.45 + 481266.484 * t, Lp, Mp, F])
    sl = sl + 3958 * np.sin(a1) + 1962 * np.sin(lp - f) + 318 * np.sin(a2)
    sb = sb - 2235 * np.sin(lp) + 382 * np.sin(a3) + 175 * np.sin(a1 - f) + 175 * np.sin(a1 + f) \
        + 127 * np.sin(lp - mp) - 115 * np.sin(lp + mp)
    return Lp + sl / 1e6, sb / 1e6, 385000.56 + sr / 1000.0


def _moon_true(jd):
    """Apparent geocentric vector of the Moon (km), true equator and equinox of date."""
    lam, bet, dist = _moon_ecliptic(jd)
    t = _tt(jd)
    dpsi, deps = _nutation(t)
    l, b = np.radians(lam) + dpsi, np.radians(bet)
    v = np.stack([np.cos(b) * np.cos(l), np.cos(b) * np.sin(l), np.sin(b)], -1) * dist[..., None]
    return _mv(_rot(0, -(_obliquity(t) + deps)), v)


def moon_radec(jd):
    """Apparent geocentric RA (h), Dec (deg) of date and distance (km) of the Moon."""
    return _radec(_moon_true(jd))


def _phase_lon(jd):
    """Moon minus Sun apparent ecliptic longitude, deg [0, 360): 0 new, 180 full."""
    t = _tt(jd)
    eps = _obliquity(t) + _nutation(t)[1]
    lon = [np.arctan2(v[..., 1] * np.cos(eps) + v[..., 2] * np.sin(eps), v[..., 0])
           for v in (_moon_true(jd), _sun_true(jd))]
    return np.degrees(lon[0] - lon[1]) % 360.0


def moon_illumination(jd):
    """Geocentric Moon phase: dict of fraction (lit, 0..1), phase_angle_deg, elongation_deg (from the Sun),
    waxing (bool) and age_days (since the previous new moon).
    """
    jd = _arr(jd)
    m, s = _moon_true(jd), _sun_true(jd) * AU_KM
    dm, ds = np.linalg.norm(m, axis=-1), np.linalg.norm(s, axis=-1)
    elong = np.arccos(np.clip(np.sum(m * s, -1) / (dm * ds), -1.0, 1.0))
    phase = np.arctan2(ds * np.sin(elong), dm - ds * np.cos(elong))
    dl = _phase_lon(jd)
    age = dl / 12.190749
    for _ in range(4):        # walk back to the moment of new moon
        age = age + ((_phase_lon(jd - age) + 180.0) % 360.0 - 180.0) / 12.190749
    return dict(fraction=(1 + np.cos(phase)) / 2, phase_angle_deg=np.degrees(phase),
                elongation_deg=np.degrees(elong), waxing=dl < 180.0, age_days=age)


# ---------------------------------------------------------------- planets ---
_SATURN_POLE = _ECL2EQ.T @ _vec(40.589 / 15.0, 83.537)    # IAU pole, ecliptic J2000


def _magnitude(name, p, e):
    """V magnitude (Mallama & Hilton 2018) from heliocentric planet `p` and Earth `e` (au)."""
    g = p - e
    r, d = np.linalg.norm(p, axis=-1), np.linalg.norm(g, axis=-1)
    a = np.degrees(np.arccos(np.clip(np.sum(p * g, -1) / (r * d), -1.0, 1.0)))     # phase angle
    m = 5 * np.log10(r * d)
    if name == "Mercury":
        return m - 0.613 + a * (6.328e-2 + a * (-1.6336e-3 + a * (3.3644e-5 + a * (-3.4265e-7 + a * (
            1.6893e-9 - 3.0334e-12 * a)))))
    if name == "Venus":
        return m - 4.384 + np.where(a < 163.7, a * (-1.044e-3 + a * (3.687e-4 + a * (-2.814e-6 + 8.938e-9 * a))),
                                    240.44228 + a * (-2.81914 + 8.39034e-3 * a))
    if name == "Mars":
        return m - 1.601 + a * (2.267e-2 - 1.302e-4 * a)
    if name == "Jupiter":
        return m - 9.395 + a * (-3.7e-4 + 6.16e-4 * a)
    # Saturn with its rings: geometric mean of the Sun's and Earth's saturnicentric latitudes
    b = np.degrees(np.arcsin(-p @ _SATURN_POLE / r)) * np.degrees(np.arcsin(-g @ _SATURN_POLE / d))
    sb = np.sin(np.radians(np.sqrt(np.maximum(b, 0.0))))
    return m - 8.914 - 1.825 * sb + 0.026 * a - 0.378 * sb * np.exp(-2.25 * a)


def planets_radec(jd):
    """{name: (ra_h, dec_deg, dist_au, mag)} for Mercury..Saturn: apparent geocentric RA/Dec of date, distance
    from Earth and visual magnitude (Mallama & Hilton 2018; Saturn includes its rings).
    """
    jd = _arr(jd)
    tm = _tt(jd) / 10.0
    rot = _of_date(jd) @ _ECL2EQ
    e = _helio("Earth", tm)
    out = {}
    for name in PLANETS:
        lt = np.linalg.norm(_helio(name, tm) - e, axis=-1) / C_AU_DAY / 365250.0
        p = _helio(name, tm - lt)
        ra, dec, _ = _radec(_mv(rot, p - _helio("Earth", tm - lt)))   # both at t - lt: aberration included
        out[name] = (ra, dec, np.linalg.norm(p - e, axis=-1), _magnitude(name, p, e))
    return out


# ------------------------------------------------------------------ stars ---
def star_vectors_to_altaz(ra_h, dec_deg, jd, lat_deg, lon_deg):
    """Geometric alt/az (deg) of J2000 catalogue stars: aberration, precession and nutation, then the horizon.

    Built for ~10,000 stars at one instant; an array `jd` broadcasts against the stars (e.g. jd[:, None]).
    Proper motion is ignored (Sirius drifts 44" from its J2000 place by 2036).
    """
    jd = _arr(jd)
    tm, h = _tt(jd) / 10.0, 1e-6
    v = (_helio("Earth", tm + h) - _helio("Earth", tm - h)) / (2 * h * 365250.0)    # au/day
    u = _vec(ra_h, dec_deg) + _mv(_ECL2EQ, v) / C_AU_DAY
    th, p = np.radians(lst_hours(jd, lon_deg) * 15.0), np.radians(_arr(lat_deg))
    o, z = np.ones_like(th), np.zeros_like(th)
    sp, cp = np.sin(p) * o, np.cos(p) * o
    hor = np.moveaxis(np.array([[z, o, z], [-sp, z, cp], [cp, z, sp]]), (0, 1), (-2, -1))   # -> east, north, up
    e, n, up = np.moveaxis(_mv(hor @ _rot(2, th) @ _of_date(jd), u), -1, 0)
    return np.degrees(np.arctan2(up, np.hypot(e, n))), np.degrees(np.arctan2(e, n)) % 360.0


# ----------------------------------------------------------------- events ---
def sun_events(date, tz_name, lat_deg, lon_deg):
    """Local times (aware datetimes, None if the event doesn't happen) of the Sun's events on a local date.

    Topocentric geometric altitude crossings: -0.8333 deg for sunrise/sunset (upper limb, 34' refraction),
    -6/-12/-18 deg for civil/nautical/astronomical dawn and dusk; solar_noon is the upper meridian transit.
    """
    tz = ZoneInfo(tz_name)
    if isinstance(date, _dt.datetime):
        date = date.date()
    j0, j1 = (julian_day(_dt.datetime.combine(date + _dt.timedelta(days=k), _dt.time(0), tz)) for k in (0, 1))

    def f(jd):
        ra, dec, r = sun_radec(jd)
        alt, _ = altaz(ra, dec, jd, lat_deg, lon_deg)
        ha = (lst_hours(jd, lon_deg) - ra + 12.0) % 24.0 - 12.0
        return alt - 0.0024428 / r * np.cos(np.radians(alt)), ha     # topocentric (solar parallax)

    jd = np.linspace(j0, j1, int(round((j1 - j0) * 288)) + 1)          # every 5 minutes
    alt, ha = f(jd)
    found, lo, thr, up = [], [], [], []
    for name, h, rising in _EVENTS:
        y = ha if h is None else alt - h
        i = np.flatnonzero((y[:-1] < 0) & (y[1:] >= 0) if rising else (y[:-1] >= 0) & (y[1:] < 0))
        if len(i):
            found.append(name)
            lo.append(i[0] if rising else i[-1])
            thr.append(np.nan if h is None else h)
            up.append(rising)
    out = dict.fromkeys(n for n, _, _ in _EVENTS)
    if not found:
        return out
    a, b, thr, up = jd[lo], jd[np.array(lo) + 1], np.array(thr), np.array(up)
    for _ in range(22):                                                # bisect to well under a second
        m = 0.5 * (a + b)
        alt, ha = f(m)
        right = (np.where(np.isnan(thr), ha, alt - np.nan_to_num(thr)) >= 0) != up
        a, b = np.where(right, m, a), np.where(right, b, m)
    for name, j in zip(found, 0.5 * (a + b)):
        out[name] = _dt.datetime.fromtimestamp(round((j - 2440587.5) * 86400.0), tz)
    return out
