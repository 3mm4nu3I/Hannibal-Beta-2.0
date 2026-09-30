#!/usr/bin/env python3
"""OGC-inspired spatial calculations for Project Hannibal.
Implements transparent 2D geometry primitives used by the subsea node layer.
"""
from __future__ import annotations
import math

EARTH_RADIUS_M = 6371008.8

def euclidean_distance(a, b):
    return math.hypot(float(b[0])-float(a[0]), float(b[1])-float(a[1]))

def haversine_m(a, b):
    lat1, lon1 = map(math.radians, (float(a[0]), float(a[1])))
    lat2, lon2 = map(math.radians, (float(b[0]), float(b[1])))
    dlat, dlon = lat2-lat1, lon2-lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))

def interpolate_segment(p0, p1, t):
    t = max(0.0, min(1.0, float(t)))
    return tuple(t*float(a) + (1.0-t)*float(b) for a,b in zip(p0,p1))

def barycentric_point(p0, p1, p2, a, b, c):
    weights = [float(a),float(b),float(c)]
    if any(w < 0 for w in weights) or not math.isclose(sum(weights),1.0,rel_tol=1e-9,abs_tol=1e-9):
        raise ValueError('barycentric weights must be non-negative and sum to 1')
    return tuple(weights[0]*p0[i]+weights[1]*p1[i]+weights[2]*p2[i] for i in range(len(p0)))

def polygon_area(points):
    pts=list(points)
    if len(pts)<3:return 0.0
    return abs(sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts))))/2.0

def polygon_centroid(points):
    pts=list(points)
    if len(pts)<3:raise ValueError('at least 3 points required')
    cross=[pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1] for i in range(len(pts))]
    twice_area=sum(cross)
    if math.isclose(twice_area,0.0):
        return (sum(p[0] for p in pts)/len(pts),sum(p[1] for p in pts)/len(pts))
    return (sum((pts[i][0]+pts[(i+1)%len(pts)][0])*cross[i] for i in range(len(pts)))/(3*twice_area),
            sum((pts[i][1]+pts[(i+1)%len(pts)][1])*cross[i] for i in range(len(pts)))/(3*twice_area))

def zscore_latest(values):
    vals=[float(v) for v in values]
    if len(vals)<3:return 0.0
    baseline=vals[1:]
    mean=sum(baseline)/len(baseline)
    var=sum((x-mean)**2 for x in baseline)/len(baseline)
    return 0.0 if var<=0 else (vals[0]-mean)/math.sqrt(var)
