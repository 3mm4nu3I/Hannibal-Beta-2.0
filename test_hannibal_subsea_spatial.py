#!/usr/bin/env python3
from hannibal_spatial_calculations import euclidean_distance,barycentric_point,polygon_area,polygon_centroid,zscore_latest
from hannibal_subsea_nodes import parse_dart
assert euclidean_distance((0,0),(3,4))==5
assert barycentric_point((0,0),(1,0),(0,1),0.5,0.25,0.25)==(0.25,0.25)
assert polygon_area([(0,0),(2,0),(2,2),(0,2)])==4
assert polygon_centroid([(0,0),(2,0),(2,2),(0,2)])==(1.0,1.0)
assert isinstance(zscore_latest([10,1,1.2,0.8]),float)
sample='#YY MM DD hh mm T HEIGHT\n2026 09 28 01 30 1 5100.123\n2026 09 28 01 15 1 5100.120\n'
rows=parse_dart(sample)
assert len(rows)==2 and rows[0]['value']==5100.123
print('PASS: spatial calculations')
print('PASS: DART parser')
