HANNIBAL V10 PORTABLE HOTFIX
- 0-9 are market tabs.
- Country keys expose the same market categories when instruments/info exist.
- x restores Usage/Health.
- m uses an ASCII-safe map for old terminals.
- q requires confirmation and performs SQLite checkpoint/maintenance; no forced process kill.
- hannibal_intel.sqlite3 is created in data/ with migrations, WAL fallback, indexes, usage, errors, predictions, quotes, integrity checks and retention.
- The supplied hannibal_three_way_arbitration.py is included under core/ to resolve the missing-file report.
- No live quotes are invented. Instrument rows display NO LIVE QUOTE until a collector writes real quotes.
Start with START_HANNIBAL_V10.bat on Windows or start_hannibal_v10.sh on Linux/macOS.
