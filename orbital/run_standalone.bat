@echo off
title PROJECT HANNIBAL - ORBITAL DIRECTORATE
chcp 65001 >nul
color 0C
REM Standalone Orbital Directorate: menu with fleet telemetry, re-entry watch, close approaches,
REM box score, sky tonight, NASA/JPL lookups, the 3D dashboard and the optional ADS-B feeder.
REM Extra switches:  python hannibal_orbital.py --help
python hannibal_orbital.py %*
pause
